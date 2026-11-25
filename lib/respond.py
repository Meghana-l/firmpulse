"""Tiny helpers shared by the Vercel API routes and the local dev server."""
import json


def send_json(handler, obj, status=200, cache=None):
    body = json.dumps(obj, default=float).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", cache or "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler, max_bytes=100_000):
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    if length > max_bytes:
        raise ValueError("request too large")
    return json.loads(handler.rfile.read(length).decode("utf-8") or "{}")
