import importlib
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture()
def env(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setenv("DATA_DIR", d)
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    monkeypatch.setenv("FLU_TODAY", "2026-02-10")
    monkeypatch.setenv("FLU_NOW", "12:00")
    monkeypatch.setenv("FLU_NO_TELEGRAM", "1")
    monkeypatch.setenv("FLU_NO_BACKUP", "1")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]
    from app import db
    db.init_db()
    with db.tx() as c:
        c.execute("UPDATE settings SET value='ru' WHERE key='default_lang'")   # the tests were written in Russian; the default for new databases is Uzbek (tested separately)
    return d


@pytest.fixture()
def client(env):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app, base_url="http://testserver") as c:
        c.cookies.set("lang", "ru")      # the web defaults to Uzbek; the tests were written for the Russian texts (Uzbek is tested in test_uz.py)
        r = c.post("/login", data={"login": "admin", "password": "secret123"}, follow_redirects=False)
        assert r.status_code == 303
        yield c


def make_facility(region=1, district="Район А", fac="Больница 1"):
    from app.db import tx
    with tx() as c:
        d = c.execute("SELECT id FROM districts WHERE region_id=? AND name_ru=?", (region, district)).fetchone()
        did = d["id"] if d else c.execute("INSERT INTO districts(region_id,name_ru) VALUES (?,?)", (region, district)).lastrowid
        return c.execute("INSERT INTO facilities(district_id,name_ru,created_at) VALUES (?,?,datetime('now'))", (did, fac)).lastrowid


def put_report(fid, date, **v):
    from app import reports
    from app.db import tx
    base = dict(beds_total=100, beds_flu=40, beds_occupied=20, visits=50, severe=5, occ_pregnant=1, occ_children=1, extreme=1, extreme_pregnant=0, extreme_children=0, hosp=10, disch=6, visits_flu=1, hosp_flu=1)
    base.update(v)
    with tx() as c:
        return reports.admin_save(c, fid, date, base, "тест", {"kind": "staff", "id": 1, "name": "admin"})
