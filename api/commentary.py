import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.commentary import get_commentary      # noqa: E402
from lib.respond import read_json, send_json   # noqa: E402
from lib.service import outlook_for            # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            send_json(self, get_commentary(outlook_for(read_json(self))))
        except Exception:
            send_json(self, {"error": "Bad request"}, status=400)
