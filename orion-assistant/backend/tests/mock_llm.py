"""A minimal OpenAI-compatible server used to exercise the real agent loop.

Without this, the tool-calling path can only be tested against a live model,
which is non-deterministic and unavailable in CI. This speaks just enough of the
protocol for `openai.AsyncOpenAI` to drive `run_agent` end to end.

Scripted behaviour is controlled by `MockLLM.script`: a list of turns, each
either {"content": "..."} or {"tool_calls": [{"name":..., "arguments": {...}}]}.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class MockLLM:
    def __init__(self) -> None:
        self.script: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.embed_calls: list[dict[str, Any]] = []
        self._turn = 0
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port = 0
        self.fail_times = 0  # simulate provider outages

    # ---------------------------------------------------------------- server
    def start(self) -> str:
        mock = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):  # silence test output
                pass

            def _send(self, code: int, payload: dict) -> None:
                body = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # /v1/models -- used by the health probe
                self._send(200, {"object": "list", "data": [{"id": "mock-model", "object": "model"}]})

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                request = json.loads(self.rfile.read(length) or "{}")

                # Embeddings share the host; keep them out of the chat call log.
                if self.path.rstrip("/").endswith("/api/embed"):
                    mock.embed_calls.append(request)
                    self._send(200, {"embeddings": [[0.01] * 768]})
                    return

                mock.calls.append(request)

                if mock.fail_times > 0:
                    mock.fail_times -= 1
                    self._send(503, {"error": {"message": "simulated provider outage"}})
                    return

                turn = mock.script[mock._turn] if mock._turn < len(mock.script) else {"content": "Done."}
                mock._turn += 1

                if request.get("stream"):
                    self._send_stream(turn, request)
                    return

                message: dict[str, Any] = {"role": "assistant", "content": turn.get("content")}
                if turn.get("tool_calls"):
                    message["tool_calls"] = [
                        {
                            "id": f"call_{uuid.uuid4().hex[:8]}",
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc.get("arguments", {})),
                            },
                        }
                        for tc in turn["tool_calls"]
                    ]

                self._send(
                    200,
                    {
                        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": request.get("model", "mock-model"),
                        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    },
                )

            def _send_stream(self, turn: dict[str, Any], request: dict[str, Any]) -> None:
                """Emit the turn as SSE deltas, the way a real provider does.

                Prose is split into several chunks and tool-call arguments are
                deliberately fragmented across deltas, so the router's
                reassembly logic is genuinely exercised.
                """
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()

                base = {
                    "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": request.get("model", "mock-model"),
                }

                def emit(delta: dict[str, Any], finish: str | None = None) -> None:
                    payload = {**base, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                    self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
                    self.wfile.flush()

                emit({"role": "assistant"})

                content = turn.get("content")
                if content:
                    # Chunk on word boundaries to mimic real token streaming.
                    words = content.split(" ")
                    for index, word in enumerate(words):
                        emit({"content": word if index == 0 else f" {word}"})

                for position, call in enumerate(turn.get("tool_calls") or []):
                    arguments = json.dumps(call.get("arguments", {}))
                    emit({
                        "tool_calls": [{
                            "index": position,
                            "id": f"call_{uuid.uuid4().hex[:8]}",
                            "type": "function",
                            "function": {"name": call["name"], "arguments": ""},
                        }]
                    })
                    # Split arguments in half across two deltas.
                    midpoint = len(arguments) // 2
                    for fragment in (arguments[:midpoint], arguments[midpoint:]):
                        emit({
                            "tool_calls": [{
                                "index": position,
                                "function": {"arguments": fragment},
                            }]
                        })

                emit({}, finish="tool_calls" if turn.get("tool_calls") else "stop")
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        # Threaded: the OpenAI client uses keep-alive, which would deadlock
        # a single-threaded server waiting for the next request on a held connection.
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_port
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return f"http://127.0.0.1:{self.port}/v1"

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread:
            self._thread.join(timeout=5)

    # ---------------------------------------------------------------- helpers
    def reset(self, script: list[dict[str, Any]] | None = None) -> None:
        self.script = script or []
        self.calls = []
        self.embed_calls = []
        self._turn = 0
        self.fail_times = 0

    @property
    def tools_offered(self) -> list[str]:
        """Tool names advertised to the model on the first call."""
        if not self.calls:
            return []
        return [t["function"]["name"] for t in self.calls[0].get("tools", [])]

    def messages_at(self, index: int) -> list[dict[str, Any]]:
        return self.calls[index].get("messages", [])
