"""Model provisioning: tier selection, Ollama probing, pull progress, honest failures.

Exercised against a mock Ollama so the real path is tested without downloading
multi-gigabyte weights.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.services import model_manager as mm


# --------------------------------------------------------------- mock ollama
class MockOllama:
    """Minimal Ollama HTTP surface: /api/tags and a streaming /api/pull."""

    def __init__(self, installed=(), pull_error=None, pull_status=200):
        self.installed = list(installed)
        self.pull_error = pull_error
        self.pull_status = pull_status
        self.pulled: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path != "/api/tags":
                    self.send_error(404)
                    return
                body = json.dumps(
                    {"models": [{"name": n, "size": 1000, "details": {}} for n in outer.installed]}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                if self.path != "/api/pull":
                    self.send_error(404)
                    return
                length = int(self.headers.get("Content-Length", 0))
                model = json.loads(self.rfile.read(length) or "{}").get("model", "")
                if outer.pull_status != 200:
                    self.send_error(outer.pull_status)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                if outer.pull_error:
                    self.wfile.write(json.dumps({"error": outer.pull_error}).encode() + b"\n")
                    return
                for completed in (0, 500, 1000):
                    event = {"status": "downloading", "total": 1000, "completed": completed}
                    self.wfile.write(json.dumps(event).encode() + b"\n")
                    self.wfile.flush()
                self.wfile.write(json.dumps({"status": "success"}).encode() + b"\n")
                outer.pulled.append(model)
                outer.installed.append(model)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture()
def ollama(monkeypatch):
    with MockOllama() as server:
        monkeypatch.setattr(mm, "ollama_host", lambda: server.url)
        yield server


# ------------------------------------------------------------ tier selection
@pytest.mark.parametrize(
    "ram_gb,expected",
    [
        (64.0, "qwen3.5:9b"),
        (16.0, "qwen3.5:9b"),
        (8.0, "qwen3.5:4b"),
        # 6GB cannot fit qwen3.5:4b, and gemma3:4b has no tool calling, so the
        # agent falls back to the smaller model that can still drive tools.
        (6.0, "qwen3:1.7b"),
        (3.0, "qwen3:1.7b"),
    ],
)
def test_recommend_tier_by_ram(ram_gb, expected):
    assert mm.recommend_tier(ram_gb).model == expected


def test_tiers_are_ordered_by_ram_requirement():
    requirements = [tier.min_ram_gb for tier in mm.MODEL_TIERS]
    assert requirements == sorted(requirements, reverse=True)


def test_every_tier_is_well_formed():
    for tier in mm.MODEL_TIERS:
        assert tier.model and tier.download_gb > 0
        assert tier.min_ram_gb > 0 and tier.note
        # Capabilities must be declared honestly -- gemma3, for example, is
        # vision-capable but has no native tool calling in Ollama.
        assert isinstance(tier.tools, bool)
        assert isinstance(tier.multimodal, bool)


def test_vision_tier_available_when_tools_not_required():
    """gemma3 is still reachable for image-first users who opt out of tools."""
    assert mm.recommend_tier(6.0, require_tools=False).model == "gemma3:4b"


def test_primary_tiers_support_tool_calling():
    """The agent loop needs tools, so every auto-recommended tier must have them."""
    for ram in (64.0, 16.0, 8.0, 3.0):
        assert mm.recommend_tier(ram).tools is True


def test_default_recommendation_is_multimodal_at_8gb():
    assert mm.recommend_tier(8.0).multimodal is True


def test_hardware_report_shape():
    report = mm.hardware_report()
    assert report["total_ram_gb"] > 0
    assert report["cpu_count"] >= 1
    assert "recommended" in report
    assert isinstance(report["tiers"], list)
    assert all("fits" in tier for tier in report["tiers"])


def test_hardware_report_marks_oversized_tiers_as_not_fitting():
    report = mm.hardware_report()
    ram = report["total_ram_gb"]
    for tier in report["tiers"]:
        if tier["min_ram_gb"] > ram:
            assert tier["fits"] is False


# ----------------------------------------------------------------- probing
async def test_ollama_running_true_against_mock(ollama):
    assert await mm.ollama_running() is True


async def test_ollama_running_false_when_absent(monkeypatch):
    monkeypatch.setattr(mm, "ollama_host", lambda: "http://127.0.0.1:1")
    assert await mm.ollama_running(timeout=1.0) is False


async def test_installed_models_lists_tags(ollama):
    ollama.installed.extend(["qwen3:4b", "nomic-embed-text:latest"])
    names = [m["name"] for m in await mm.installed_models()]
    assert "qwen3:4b" in names


async def test_model_present_matches_by_base_name(ollama):
    ollama.installed.append("qwen3:4b")
    assert await mm.model_present("qwen3:4b") is True
    assert await mm.model_present("llama3:8b") is False


async def test_installed_models_empty_when_unreachable(monkeypatch):
    monkeypatch.setattr(mm, "ollama_host", lambda: "http://127.0.0.1:1")
    assert await mm.installed_models() == []


# -------------------------------------------------------------------- pulls
async def test_pull_reports_completion(ollama):
    tracker = mm.PullTracker()
    state = await tracker.pull("qwen3:1.7b")
    assert state["status"] == "ready"
    assert state["percent"] == 100.0
    assert "qwen3:1.7b" in ollama.pulled


async def test_pull_surfaces_stream_error(monkeypatch):
    with MockOllama(pull_error="no space left on device") as server:
        monkeypatch.setattr(mm, "ollama_host", lambda: server.url)
        state = await mm.PullTracker().pull("qwen3.5:4b")
    assert state["status"] == "failed"
    assert "no space" in state["error"]


async def test_pull_surfaces_http_error(monkeypatch):
    with MockOllama(pull_status=500) as server:
        monkeypatch.setattr(mm, "ollama_host", lambda: server.url)
        state = await mm.PullTracker().pull("qwen3.5:4b")
    assert state["status"] == "failed"


async def test_pull_failure_when_ollama_unreachable(monkeypatch):
    monkeypatch.setattr(mm, "ollama_host", lambda: "http://127.0.0.1:1")
    state = await mm.PullTracker().pull("qwen3.5:4b")
    assert state["status"] == "failed"
    assert state["error"]


async def test_tracker_snapshot_exposes_progress(ollama):
    tracker = mm.PullTracker()
    await tracker.pull("qwen3:1.7b")
    snapshot = tracker.snapshot()
    assert snapshot["qwen3:1.7b"]["status"] == "ready"


# --------------------------------------------------------------- provision
async def test_provision_pulls_model_and_embedder(ollama):
    result = await mm.provision("qwen3:1.7b")
    assert result["ok"] is True
    assert set(ollama.pulled) == {"qwen3:1.7b", mm.EMBED_MODEL}


async def test_provision_skips_already_present_models(ollama):
    ollama.installed.extend(["qwen3:1.7b", mm.EMBED_MODEL])
    result = await mm.provision("qwen3:1.7b")
    assert result["ok"] is True
    assert all(r["status"] == "already_present" for r in result["results"].values())
    assert ollama.pulled == []


async def test_provision_without_ollama_explains_how_to_install(monkeypatch):
    monkeypatch.setattr(mm, "ollama_host", lambda: "http://127.0.0.1:1")
    monkeypatch.setattr(mm, "ollama_installed", lambda: False)
    result = await mm.provision("qwen3.5:4b")
    assert result["ok"] is False
    assert result["stage"] == "ollama_missing"
    assert "setup-local-model.sh" in result["message"]


async def test_provision_defaults_to_recommended_tier(ollama):
    result = await mm.provision()
    assert result["model"] == mm.recommend_tier().model


# ------------------------------------------------------------------ status
async def test_status_reports_offline_stack(monkeypatch):
    monkeypatch.setattr(mm, "ollama_host", lambda: "http://127.0.0.1:1")
    state = await mm.status()
    assert state["ollama_running"] is False
    assert state["installed_models"] == []
    assert "hardware" in state


async def test_status_reports_installed_model(ollama, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ollama_model", "qwen3:4b")
    ollama.installed.extend(["qwen3:4b", mm.EMBED_MODEL])
    state = await mm.status()
    assert state["ollama_running"] is True
    assert state["active_model_present"] is True
    assert state["embed_model_present"] is True


async def test_status_flags_vision_capability(ollama, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ollama_model", "qwen3.5:4b")
    assert (await mm.status())["vision_capable"] is True
    monkeypatch.setattr(settings, "ollama_model", "phi4-mini")
    assert (await mm.status())["vision_capable"] is False


# --------------------------------------------------------------- endpoints
def test_models_status_endpoint(client):
    body = client.get("/v1/models/status").json()
    assert "hardware" in body
    assert "active_model" in body


def test_models_hardware_endpoint(client):
    body = client.get("/v1/models/hardware").json()
    assert body["total_ram_gb"] > 0
    assert body["recommended"]["model"]


def test_models_catalog_endpoint(client):
    body = client.get("/v1/models/catalog").json()
    assert len(body["tiers"]) == len(mm.MODEL_TIERS)
    assert body["recommended"]["model"]


def test_provision_endpoint_503s_without_ollama(client, monkeypatch):
    monkeypatch.setattr(mm, "ollama_host", lambda: "http://127.0.0.1:1")
    monkeypatch.setattr(mm, "ollama_installed", lambda: False)
    response = client.post("/v1/models/provision", json={"model": "qwen3.5:4b"})
    assert response.status_code == 503
    assert response.json()["stage"] == "ollama_missing"
