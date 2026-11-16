"""A stand-in for api.telegram.org for the recording: accepts every message and says ok."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        out = json.dumps({"ok": True, "result": True}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

    do_GET = do_POST


HTTPServer(("127.0.0.1", 8099), H).serve_forever()
