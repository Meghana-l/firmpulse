"""
Run the whole app locally (no Vercel account needed):

    python dev_server.py            # then open http://localhost:3000

It serves ./public and routes /api/* to the same handlers Vercel runs.
Set keys first, e.g.  export FRED_API_KEY=...   (see .env.example)
"""
import importlib
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def load_dotenv(path):
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_dotenv(os.path.join(ROOT, ".env"))


class Dev(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=os.path.join(ROOT, "public"), **k)

    def _api(self, verb):
        name = self.path.split("?")[0].strip("/").split("/")[1] if self.path.startswith("/api/") else None
        try:
            mod = importlib.import_module(f"api.{name}")
            getattr(mod.handler, f"do_{verb}")(self)
        except (ImportError, AttributeError):
            self.send_error(404)

    def do_GET(self):
        self._api("GET") if self.path.startswith("/api/") else super().do_GET()

    def do_POST(self):
        self._api("POST") if self.path.startswith("/api/") else self.send_error(405)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3000"))
    print(f"FirmPulse running at http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Dev).serve_forever()
