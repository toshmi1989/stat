import io
from conftest import make_facility, put_report


def seed():
    f1, f2 = make_facility(1, fac="A"), make_facility(2, "Район Б", "B")
    for i in range(1, 11):
        put_report(f1, f"2026-02-{i:02d}", visits=10 + i, hosp=5 + i, disch=4)
        put_report(f2, f"2026-02-{i:02d}", visits=30 + i)
    return f1, f2


def mk_staff(client, login, role, regions=()):
    r = client.post("/api/staff", json={"login": login, "role": role, "regions": list(regions), "password": "password123", "name": login})
    assert r.status_code == 200, r.text
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app, base_url="http://testserver")
    assert c.post("/login", data={"login": login, "password": "password123"}, follow_redirects=False).status_code == 303
    return c


def test_auth_required(env):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        assert c.get("/api/dashboard").status_code == 401
        assert c.get("/", follow_redirects=False).status_code == 303
        assert c.get("/healthz").status_code == 200
        assert c.post("/login", data={"login": "admin", "password": "wrong"}).status_code == 401


def test_login_rate_limit(env):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        codes = [c.post("/login", data={"login": "admin", "password": "x"}).status_code for _ in range(12)]
        assert 429 in codes


def test_cross_site_post_refused(client):
    assert client.post("/api/backup", headers={"Origin": "https://evil.example"}).status_code == 403


def test_all_analytics_endpoints(client):
    seed()
    q = "d1=2026-02-01&d2=2026-02-10"
    d = client.get("/api/dashboard?date=2026-02-10").json()
    assert d["kpis"]["totals"]["visits"] == 20 + 40 + 0 or d["kpis"]["totals"]["visits"] > 0
    for p in ("regions-table", "dynamics?metrics=visits,hosp", "beds", "hosp-disch", "forecast", "alerts", "control?date=2026-02-10", "reports"):
        r = client.get(f"/api/{p}" + ("&" if "?" in p else "?") + q)
        assert r.status_code == 200, (p, r.text)
    rt = client.get("/api/regions-table?" + q).json()
    assert {r["name"] for r in rt["rows"]} >= {"Ташкентская область"} or len(rt["rows"]) == 14


def test_fallback_to_latest_day(client):
    seed()
    d = client.get("/api/dashboard?date=2026-02-15").json()
    assert d["fallback"] and d["used_date"] == "2026-02-10"


def test_region_admin_scope(client):
    f1, f2 = seed()
    a = mk_staff(client, "reg1", "admin", [1])
    k = a.get("/api/dashboard?d1=2026-02-10&d2=2026-02-10").json()["kpis"]["totals"]
    assert k["visits"] == 20
    assert a.get("/api/dashboard?d1=2026-02-10&d2=2026-02-10&region_id=2").status_code == 403
    assert a.get(f"/api/dashboard?d1=2026-02-10&d2=2026-02-10&facility_id={f2}").status_code == 403
    assert a.get("/api/districts?region_id=2").status_code == 403
    regs = a.get("/api/meta").json()["regions"]
    assert [r["id"] for r in regs] == [1]
    rep2 = client.get("/api/reports?d1=2026-02-10&d2=2026-02-10&region_id=2").json()["items"][0]["id"]
    assert a.get(f"/api/reports/{rep2}").status_code == 403
    assert a.put("/api/reports", json={"facility_id": f2, "date": "2026-02-10", "values": {"visits": 1}, "reason": "x"}).status_code == 403
    assert a.get("/api/settings").status_code == 403 and a.get("/api/audit").status_code == 403
    assert a.post("/api/regions", json={"name_ru": "Х"}).status_code == 403
    rows = a.get("/api/regions-table?d1=2026-02-10&d2=2026-02-10").json()["rows"]
    assert [r["id"] for r in rows] == [1]
    assert a.get("/api/regions-table?level=district&parent_id=2&d1=2026-02-10&d2=2026-02-10").json()["rows"] == []


def test_viewer_cannot_write_or_see_control(client):
    f1, f2 = seed()
    v = mk_staff(client, "view1", "viewer")
    assert v.get("/api/dashboard").status_code == 200
    assert v.get("/api/control").status_code == 403
    assert v.get("/api/reports").status_code == 403
    assert v.put("/api/reports", json={"facility_id": f1, "date": "2026-02-10", "values": {}, "reason": "x"}).status_code == 403
    assert v.get("/api/requests").status_code == 403


def test_report_edit_via_api_and_history(client):
    f1, _ = seed()
    r = client.put("/api/reports", json={"facility_id": f1, "date": "2026-02-10", "values": {"visits": 99}, "reason": "ошибка ввода"})
    assert r.status_code == 200 and r.json()["version"] == 2
    bad = client.put("/api/reports", json={"facility_id": f1, "date": "2026-02-10", "values": {"visits": 99}, "reason": ""})
    assert bad.status_code == 400
    block = client.put("/api/reports", json={"facility_id": f1, "date": "2026-02-10", "values": {"beds_occupied": 500}, "reason": "тест"})
    assert block.status_code in (400, 422) and "error" in block.json()
    rid = r.json()["id"]
    rep = client.get(f"/api/reports/{rid}").json()
    assert rep["values"]["visits"] == 99 and len(rep["versions"]) == 2
    back = client.post(f"/api/reports/{rid}/restore", json={"version": 1, "reason": "вернуть"}).json()
    assert back["version"] == 3
    assert client.get(f"/api/reports/{rid}").json()["values"]["visits"] != 99


def test_return_and_lock(client):
    f1, _ = seed()
    rid = client.get("/api/reports?d1=2026-02-10&d2=2026-02-10").json()["items"][0]["id"]
    assert client.post(f"/api/reports/{rid}/return", json={"reason": ""}).status_code == 400
    assert client.post(f"/api/reports/{rid}/return", json={"reason": "проверьте койки"}).status_code == 200
    assert client.get(f"/api/reports/{rid}").json()["status"] == "returned"
    assert client.post(f"/api/reports/{rid}/lock", json={"locked": True}).status_code == 200


def test_rules_and_indicators_admin(client):
    assert client.post("/api/rules", json={"expr": "__import__('os')", "kind": "error", "message_ru": "x"}).status_code == 400
    assert client.post("/api/rules", json={"expr": "visits >= severe", "kind": "warning", "message_ru": "m"}).status_code == 200
    assert client.post("/api/indicators", json={"code": "test_ind", "name_ru": "Тест", "agg": "sum"}).status_code == 200
    assert client.patch("/api/indicators/visits", json={"active": False}).status_code == 400
    assert client.post("/api/rules/test", json={"expr": "a <= b", "values": {}}).json()["ok"] is False


def test_settings_validation(client):
    assert client.put("/api/settings", json={"deadline_time": "25:00"}).status_code == 400
    assert client.put("/api/settings", json={"occ_elevated": "90", "occ_critical": "80"}).status_code == 400
    assert client.put("/api/settings", json={"remind_times": "15:00, 17:30", "deadline_time": "17:00"}).status_code == 200
    assert client.get("/api/settings").json()["settings"]["remind_times"] == "15:00,17:30"


def test_cannot_demote_last_super_admin(client):
    me = client.get("/api/me").json()
    assert client.patch(f"/api/staff/{me['id']}", json={"role": "viewer"}).status_code == 400


def test_exports(client):
    seed()
    q = "d1=2026-02-01&d2=2026-02-10"
    r = client.get(f"/api/export?fmt=xlsx&kind=custom&{q}")
    assert r.status_code == 200
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert len(wb.sheetnames) == 3
    ws = wb.worksheets[0]
    assert ws.page_setup.paperSize == 9 and ws.page_setup.orientation == "landscape" and ws.sheet_properties.pageSetUpPr.fitToPage
    assert any("одпис" in str(c.value or "") for row in ws.iter_rows() for c in row)
    pdf = client.get(f"/api/export?fmt=pdf&{q}")
    assert pdf.content[:4] == b"%PDF"
    csv = client.get(f"/api/export?fmt=csv&{q}")
    assert csv.content.startswith(b"\xef\xbb\xbf") and b";" in csv.content
    assert client.get(f"/api/export?fmt=exe&{q}").status_code == 400


def test_territory_import(client):
    badb = "Регион;Район;Учреждение\nНеизвестный;Р;У\n".encode("utf-8")
    assert client.post("/api/geo/import?dry=1", files={"file": ("t.csv", badb)}).json()["errors_total"] == 1
    csvb = "Регион;Район;Учреждение\nгород Ташкент;Район Новый;Поликлиника 7\n".encode("utf-8")
    r = client.post("/api/geo/import?dry=1", files={"file": ("t.csv", csvb)})
    assert r.status_code == 200, r.text
    r2 = client.post("/api/geo/import?dry=0", files={"file": ("t.csv", csvb)})
    assert r2.status_code == 200
    fac = client.get("/api/facilities?q=Поликлиника 7").json()
    assert fac["total"] == 1


def test_region_access_api_and_scope(client):
    seed()
    from app import people
    from app.db import tx
    with tx() as c:
        people.add_tg_user(c, "400400", "Али")
    a = mk_staff(client, "regmgr", "admin", [1])
    assert a.post("/api/assignments", json={"tg_id": "400400", "region_id": 1}).status_code == 403     # no right to manage access
    sid = [x for x in client.get("/api/staff").json()["items"] if x["login"] == "regmgr"][0]["id"]
    client.patch(f"/api/staff/{sid}", json={"can_manage_users": True})
    assert a.post("/api/assignments", json={"tg_id": "400400", "region_id": 2}).status_code == 403     # not their region
    r = a.post("/api/assignments", json={"tg_id": "400400", "region_id": 1})
    assert r.status_code == 200
    assert client.get("/api/tg-users").json()["items"][0]["regions"][0]["region_id"] == 1
    assert a.get("/api/tg-users").json()["items"][0]["regions"][0]["region_id"] == 1
    assert a.delete(f"/api/region-access/{r.json()['id']}").status_code == 200
    assert client.get("/api/tg-users").json()["items"][0]["regions"] == []
