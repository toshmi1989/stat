"""Regression: the site must keep answering other requests while an action of the site waits for a slow Telegram (the reply to a message used to freeze the whole worker:
every section hung on «Загрузка…»). A fake Telegram answers sendMessage after 4 s.  Run: python3 tests/e2e/freeze.py [code dir, default the project] [port, default 8801]"""
import json, os, subprocess, sys, threading, time, urllib.request, http.cookiejar, tempfile
code = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8801
data = tempfile.mkdtemp()
env = dict(os.environ, DATA_DIR=data, APP_PASSWORD="secret123", TELEGRAM_BOT_TOKEN="123:fake", TELEGRAM_API="http://127.0.0.1:9911", FLU_NO_BACKUP="1")
subprocess.run([sys.executable, "-c", "from app import db, cli; db.init_db(); cli.demo()"], cwd=code, env=env, capture_output=True)
subprocess.run([sys.executable, "-c", f"""
from app import db
db.init_db()
with db.tx() as c:
    fid = c.execute('select id from facilities limit 1').fetchone()[0]
    c.execute("insert into tg_users(tg_id, first_name, lang, created_at) values ('900', 'Тест', 'uz', 'x')")
    cur = c.execute("insert into ministry_messages(facility_id, report_date, tg_id, sender, text, created_at, direction) values (?,?,?,?,?,?, 'in')", (fid, '2026-01-01', '900', 'Тест', 'Нужна помощь', 'x'))
    c.execute('update ministry_messages set thread_id=id where id=?', (cur.lastrowid,))
"""], cwd=code, env=env, capture_output=True)
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
class FakeTg(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length") or 0))
        if self.path.endswith("/sendMessage"):
            time.sleep(4)                                                   # a slow Telegram
        body = json.dumps({"ok": True, "result": [] if self.path.endswith("/getUpdates") else {"username": "fakebot", "message_id": 1}}).encode()
        self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
fake = ThreadingHTTPServer(("127.0.0.1", 9911), FakeTg)
threading.Thread(target=fake.serve_forever, daemon=True).start()
tgsrv = type("X", (), {"terminate": lambda self: fake.shutdown()})()
srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--workers", "1"], cwd=code, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(3.5)
try:
    cj = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj)); base = f"http://127.0.0.1:{port}"
    op.open(urllib.request.Request(base + "/login", b"login=admin&password=secret123", method="POST")).read()
    mid = json.load(op.open(base + "/api/messages"))["items"][0]["thread_id"]
    res = {}
    def reply():
        t0 = time.time(); r = op.open(urllib.request.Request(f"{base}/api/messages/{mid}/reply", json.dumps({"text": "Ответ"}).encode(), {"content-type": "application/json"}, method="POST")); res["reply"] = round(time.time() - t0, 1)
    th = threading.Thread(target=reply); th.start(); time.sleep(0.8)
    lat = []
    for _ in range(4):
        t0 = time.time()
        try: op.open(base + "/api/pulse", timeout=8).read(); lat.append(round(time.time() - t0, 2))
        except Exception as e: lat.append(f"timeout({e})")
        time.sleep(0.3)
    th.join(15)
    print(f"reply took {res.get('reply')} s; other requests meanwhile answered in: {lat}")
    slow = [x for x in lat if isinstance(x, str) or x > 1.0]
    print("FAIL: the site froze while Telegram was slow" if slow else "PASS: other requests are not held up by a slow Telegram")
    sys.exit(1 if slow else 0)
finally:
    srv.terminate(); tgsrv.terminate()
