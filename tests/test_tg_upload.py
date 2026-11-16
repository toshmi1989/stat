import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def test_send_document_multipart(env, monkeypatch):
    got = {}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def do_POST(self):
            got["path"], got["ct"] = self.path, self.headers["Content-Type"]
            got["body"] = self.rfile.read(int(self.headers["Content-Length"]))
            out = json.dumps({"ok": True, "result": {}}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("TELEGRAM_API", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:TEST")
    import importlib
    from app import tg
    importlib.reload(tg)
    payload = bytes(range(256)) * 20                       # binary content survives
    ok, err = tg.send_document(12345, payload, 'flu_2026-02-10.xlsx', "подпись")
    srv.shutdown()
    assert ok and err == ""
    assert got["path"] == "/bot1:TEST/sendDocument" and got["ct"].startswith("multipart/form-data; boundary=")
    assert payload in got["body"] and b'filename="flu_2026-02-10.xlsx"' in got["body"] and 'подпись'.encode() in got["body"] and b'name="chat_id"\r\n\r\n12345' in got["body"]
