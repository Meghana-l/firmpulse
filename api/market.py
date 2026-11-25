import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.market import get_market          # noqa: E402
from lib.respond import send_json          # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Edge cache for 5 minutes so many visitors do not burn your free API quota.
        send_json(self, get_market(), cache="public, s-maxage=300, stale-while-revalidate=600")
