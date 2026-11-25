import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.respond import read_json, send_json   # noqa: E402
from lib.service import resolve_request        # noqa: E402
from lib.xlsx_builder import workbook_bytes    # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            a, returns, cash, _ = resolve_request(read_json(self))
            data = workbook_bytes(a, returns, cash)
        except Exception:
            send_json(self, {"error": "Bad request"}, status=400)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Disposition", f'attachment; filename="FirmPulse_FY{a.fy}.xlsx"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)
