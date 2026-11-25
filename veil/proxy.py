"""A drop-in privacy proxy with an OpenAI-compatible API.

Point any app that speaks the OpenAI chat API at this server instead of the
real provider. Every request is masked on the way out and every answer is
unmasked on the way back, so existing apps get privacy without code changes:

    python -m veil serve --backend anthropic --port 8787
    curl http://127.0.0.1:8787/v1/chat/completions -d '{"messages":[...]}'

Limitations (prototype): no streaming, text content only, one shared mapping
for all clients of a server.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .shield import Shield


def make_server(backend, shield: Shield | None = None, host: str = "127.0.0.1", port: int = 8787,
                audit=None) -> ThreadingHTTPServer:
    shield = shield or Shield()
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quieter default logging
            pass

        def _send(self, code: int, payload: dict):
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.rstrip("/") in ("", "/health"):
                return self._send(200, {"status": "ok", "service": "pii-veil"})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self.path.rstrip("/").endswith("/chat/completions"):
                return self._send(404, {"error": "only /v1/chat/completions is supported"})
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                if req.get("stream"):
                    return self._send(400, {"error": "streaming not supported in the prototype"})
                with lock:
                    masked = [{"role": m["role"], "content": shield.mask(m.get("content") or "")}
                              for m in req.get("messages", [])]
                if audit:
                    audit(masked)
                answer_fake = backend.chat(masked)
                with lock:
                    answer = shield.unmask(answer_fake)
                self._send(200, {
                    "id": f"veil-{int(time.time() * 1000)}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": req.get("model", "pii-veil"),
                    "choices": [{"index": 0, "finish_reason": "stop",
                                 "message": {"role": "assistant", "content": answer}}],
                })
            except Exception as exc:  # report, never echo request data
                self._send(500, {"error": type(exc).__name__ + ": " + str(exc)[:200]})

    return ThreadingHTTPServer((host, port), Handler)
