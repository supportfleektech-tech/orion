#!/usr/bin/env python3
"""A tiny OpenAI-compatible model server for demoing ORION without Ollama.

This is NOT an LLM. It is a deterministic rule-based responder that speaks the
OpenAI chat-completions protocol, including tool calling, so the full agent loop
(tool selection -> execution -> result -> final answer) can be exercised in a
preview environment with no model download and no API key.

Replace it with real Ollama or OpenRouter for actual reasoning:

    ollama pull qwen3:4b     # then unset OLLAMA_BASE_URL override

Usage:  python scripts/demo_model.py [port]
"""

from __future__ import annotations

import json
import re
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MATH_RE = re.compile(r"(-?\d[\d\s]*(?:[+\-*/^()][\d\s.]*)+)")


def latest_user_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def tool_results(messages: list[dict]) -> list[dict]:
    out = []
    for message in messages:
        if message.get("role") == "tool":
            try:
                out.append(json.loads(message.get("content") or "{}"))
            except json.JSONDecodeError:
                pass
    return out


def build_reply(messages: list[dict], available: set[str]) -> dict:
    """Decide the next assistant turn: either call a tool or answer."""
    results = tool_results(messages)
    user = latest_user_text(messages)
    lowered = user.lower()

    # ---- Second pass: we already have tool output, so summarise it.
    if results:
        last = results[-1]
        if not last.get("ok"):
            return {"content": f"That tool call did not succeed: {last.get('error', 'unknown error')}"}

        payload = last.get("result", {})
        if isinstance(payload, dict):
            if "result" in payload and "expression" in payload:
                return {"content": f"{payload['expression']} = {payload['result']:g}"}
            if "utc_iso" in payload:
                return {"content": f"The current UTC time is {payload['utc_iso']} ({payload.get('weekday','')})."}
            if "results" in payload:
                hits = payload["results"]
                if not hits:
                    return {"content": "I searched but found nothing relevant stored yet."}
                lines = [f"- {h.get('content', '')[:200]}" for h in hits[:4]]
                return {"content": "Here is what I found:\n" + "\n".join(lines)}
            if "files" in payload:
                files = payload["files"]
                listing = "\n".join(f"- {f}" for f in files[:15]) or "(empty)"
                return {"content": f"The knowledge directory contains:\n{listing}"}
            if "content" in payload:
                return {"content": f"File contents:\n\n{str(payload['content'])[:1200]}"}
            if "stored" in payload:
                return {"content": "Saved that to long-term memory."}
        return {"content": f"Tool output:\n```json\n{json.dumps(payload, indent=2)[:900]}\n```"}

    # ---- First pass: pick a tool when the request clearly calls for one.
    math = MATH_RE.search(user)
    if math and any(op in user for op in "+-*/^") and "calculate" in available:
        return {"tool": "calculate", "arguments": {"expression": math.group(1).strip()}}

    if any(word in lowered for word in ("time", "date", "today")) and "current_time" in available:
        return {"tool": "current_time", "arguments": {}}

    if any(word in lowered for word in ("list files", "what files", "directory")) and "list_files" in available:
        return {"tool": "list_files", "arguments": {"path": "."}}

    if any(word in lowered for word in ("remember that", "note that", "save that")) and "memory_write" in available:
        return {"tool": "memory_write", "arguments": {"content": user, "kind": "fact", "confidence": 0.8}}

    if any(word in lowered for word in ("remember", "recall", "know about", "my ")) and "memory_search" in available:
        return {"tool": "memory_search", "arguments": {"query": user}}

    if any(word in lowered for word in ("document", "knowledge", "file say", "ingested")) and "knowledge_search" in available:
        return {"tool": "knowledge_search", "arguments": {"query": user}}

    if lowered.strip() in {"hi", "hello", "hey"} or lowered.startswith(("hi ", "hello ")):
        return {
            "content": (
                "Hello. I am ORION running against the bundled demo model.\n\n"
                "I can exercise the real agent loop: try \"what is 47 * 19?\", \"what time is it?\", "
                "\"what files do you have?\", or \"what do you remember about me?\".\n\n"
                "Swap in Ollama or OpenRouter for genuine reasoning."
            )
        }

    return {
        "content": (
            "I am the bundled demo model, so I pattern-match rather than reason. "
            "I can still demonstrate the full tool pipeline — ask me to calculate something, "
            "check the time, list files, or search memory and knowledge.\n\n"
            "For real answers, point ORION at Ollama or set OPENROUTER_API_KEY."
        )
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_stream(self, message: dict) -> None:
        """Emit the reply as OpenAI-style SSE deltas.

        Content is chunked word-by-word with a small delay so the UI's token
        streaming is genuinely exercised rather than arriving in one burst.
        Tool calls cannot be partially applied, so they go out in a single
        delta before the content.
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

        def emit(delta: dict, finish: str | None = None) -> None:
            payload = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "orion-demo",
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
            self.wfile.flush()

        emit({"role": "assistant"})

        if message.get("tool_calls"):
            emit({"tool_calls": message["tool_calls"]})
        else:
            for token in re.findall(r"\s*\S+", message.get("content") or ""):
                emit({"content": token})
                time.sleep(0.015)

        emit({}, finish="stop")
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def do_GET(self):
        self._send(200, {"object": "list", "data": [{"id": "orion-demo", "object": "model"}]})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        request = json.loads(self.rfile.read(length) or "{}")

        if self.path.rstrip("/").endswith("/api/embed"):
            # Let ORION's own hashed embedder handle vectors.
            self._send(404, {"error": "embeddings not provided by the demo model"})
            return

        messages = request.get("messages", [])
        available = {t["function"]["name"] for t in request.get("tools", [])}
        decision = build_reply(messages, available)

        message: dict = {"role": "assistant", "content": decision.get("content")}
        if decision.get("tool"):
            message["tool_calls"] = [
                {
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": decision["tool"],
                        "arguments": json.dumps(decision.get("arguments", {})),
                    },
                }
            ]

        if request.get("stream"):
            self._send_stream(message)
            return

        self._send(
            200,
            {
                "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "orion-demo",
                "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            },
        )


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 11435
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    print(f"ORION demo model listening on http://127.0.0.1:{port}/v1", flush=True)
    server.serve_forever()
