import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.respond import send_json          # noqa: E402
from lib.sec13f import get_13f             # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        out = get_13f()
        # 13F filings change once a quarter, so cache for 6 hours (failures are not cached long).
        send_json(self, out, cache="public, s-maxage=21600, stale-while-revalidate=86400" if out.get("ok") else "public, s-maxage=60")
