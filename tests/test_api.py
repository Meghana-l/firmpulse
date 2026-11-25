"""Start the local server on a free port and hit the real HTTP routes."""
import json
import os
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.pop("FRED_API_KEY", None)           # force sample data: no network in tests
os.environ.pop("ANTHROPIC_API_KEY", None)

import dev_server  # noqa: E402


def _call(base, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status, r.headers.get("Content-Type"), r.read()


def test_routes():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), dev_server.Dev)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        st, ct, body = _call(base, "/")
        assert st == 200 and b"FirmPulse" in body

        st, _, body = _call(base, "/api/market")
        mk = json.loads(body)
        assert mk["source"] == "sample"

        st, _, body = _call(base, "/api/model", {"assumptions": {"start_aum": 8000},
                                                 "market": {"monthly_market_returns": [0.01, 0.02]}})
        out = json.loads(body)
        assert out["completed_months"] == 2 and out["assumptions"]["start_aum"] == 8000

        st, _, body = _call(base, "/api/commentary", {})
        assert json.loads(body)["source"] == "template"

        st, ct, body = _call(base, "/api/export", {})
        assert "spreadsheetml" in ct and body[:2] == b"PK"

        st, _, body = _call(base, "/api/holdings")
        assert "ok" in json.loads(body)         # works with or without network
    finally:
        srv.shutdown()
