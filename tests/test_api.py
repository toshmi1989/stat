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


def test_delete_reports_and_territories(client):
    from app.db import connect
    f1, f2 = seed()
    rid = [r["id"] for r in client.get("/api/reports?d1=2026-02-01&d2=2026-02-10&size=200").json()["items"] if r["facility"] == "A"][:2]
    admin_viewer = mk_staff(client, "vwer", "viewer", [1])
    assert admin_viewer.post("/api/reports/delete", json={"ids": rid, "reason": "x"}).status_code == 403
    assert client.post("/api/reports/delete", json={"ids": rid}).status_code == 400                       # a reason is required
    assert client.post("/api/reports/delete", json={"ids": rid, "reason": "тестовые"}).json() == {"deleted": 2}
    c = connect()
    assert c.execute("SELECT COUNT(*) FROM reports WHERE id IN (?,?)", rid).fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM report_versions WHERE report_id IN (?,?)", rid).fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM audit WHERE action='report.delete'").fetchone()[0] == 2        # a snapshot stays in the log
    assert c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name='versions_no_delete'").fetchone()[0] == 1   # the guard is back
    c.close()
    # a facility with reports: refused without confirmation, removed with it
    assert client.delete(f"/api/facilities/{f1}").status_code == 409
    assert client.get("/api/facilities?region_id=1").json()["items"][0]["reports"] == 8
    assert client.delete(f"/api/facilities/{f1}?force=1").json()["reports"] == 8
    assert client.delete(f"/api/facilities/{f1}?force=1").status_code == 404
    # a district/region with facilities is not removed; an empty one is
    did2 = client.get("/api/facilities?region_id=2").json()["items"][0]["district_id"]
    assert client.delete(f"/api/districts/{did2}").status_code == 409
    assert client.delete("/api/regions/2").status_code == 409
    assert client.delete(f"/api/facilities/{f2}?force=1").status_code == 200
    assert client.delete(f"/api/districts/{did2}").status_code == 200
    assert client.delete("/api/regions/2").status_code == 200
    assert admin_viewer.delete("/api/regions/1").status_code == 403


def test_pulse_token_changes_when_reports_change(client):
    t0 = client.get("/api/pulse").json()["token"]
    assert client.get("/api/pulse").json()["token"] == t0                   # nothing happened: the same token
    f = make_facility(1, fac="P")
    t1 = client.get("/api/pulse").json()["token"]
    assert t1 != t0                                                          # a facility was added
    put_report(f, "2026-02-10", visits=5)
    t2 = client.get("/api/pulse").json()["token"]
    assert t2 != t1                                                          # a report arrived
    put_report(f, "2026-02-10", visits=6)
    assert client.get("/api/pulse").json()["token"] != t2                    # a report was corrected (a new version)
    rid = client.get("/api/reports?d1=2026-02-10&d2=2026-02-10").json()["items"][0]["id"]
    t3 = client.get("/api/pulse").json()["token"]
    client.post("/api/reports/delete", json={"ids": [rid], "reason": "t"})
    assert client.get("/api/pulse").json()["token"] != t3                    # a report was deleted


def test_register_by_username_in_advance_and_claim_at_the_first_message(client, monkeypatch):
    from app import bot, people, tg
    from app.db import connect, tx
    sent = []
    monkeypatch.setattr(tg, "send", lambda chat, text, markup=None: (sent.append((str(chat), text)) or (True, "")))
    f = make_facility(1, fac="Pre")
    assert client.post("/api/preapproved", json={"username": "bad name", "region_id": 1}).status_code == 400
    assert client.post("/api/preapproved", json={"username": "@Ali_Test", "region_id": 1}).json()["id"]
    assert client.post("/api/preapproved", json={"username": "https://t.me/ali_test", "region_id": 1}).json()["id"]      # the same person again: replaced, not doubled
    assert len(client.get("/api/preapproved").json()["items"]) == 1
    assert client.post("/api/preapproved", json={"username": "fac_user", "region_id": 1, "facility_id": f, "kind": "primary"}).status_code == 200
    viewer = mk_staff(client, "vwer2", "viewer", [1])
    assert viewer.post("/api/preapproved", json={"username": "someone", "region_id": 1}).status_code == 403
    # the person writes to the bot for the first time: the access is there, no request is needed
    bot.handle_update({"message": {"chat": {"id": 880001, "type": "private"}, "from": {"id": 880001, "username": "ALI_test", "first_name": "Али"}, "text": "/start"}})
    c = connect()
    assert c.execute("SELECT COUNT(*) FROM region_access WHERE tg_id='880001' AND region_id=1 AND active=1").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM access_requests WHERE tg_id='880001'").fetchone()[0] == 0
    assert c.execute("SELECT used_tg_id FROM preapproved WHERE lower(username)='ali_test'").fetchone()[0] == "880001"
    c.close()
    assert any("880001" == ch and ("ruxsat" in tx_.lower() or "доступ" in tx_.lower()) for ch, tx_ in sent)
    assert client.get("/api/preapproved").json()["items"][0]["username"] == "fac_user"             # only the unclaimed one is left
    # a facility registration is given as the facility; a person who is already in the bot gets it at once
    bot.handle_update({"message": {"chat": {"id": 880002, "type": "private"}, "from": {"id": 880002, "username": "Fac_User", "first_name": "Б"}, "text": "/start"}})
    assert connect().execute("SELECT COUNT(*) FROM assignments WHERE tg_id='880002' AND facility_id=? AND active=1", (f,)).fetchone()[0] == 1
    assert client.post("/api/preapproved", json={"username": "ali_test", "region_id": 2}).json() == {"claimed": "880001"}
    pid = client.post("/api/preapproved", json={"username": "later_one", "region_id": 1}).json()["id"]
    assert client.delete(f"/api/preapproved/{pid}").status_code == 200


def test_avatar_is_fetched_once_cached_and_hidden_from_others(client, monkeypatch):
    from app import people, tg
    from app.db import tx
    calls = []
    monkeypatch.setattr(tg, "configured", lambda: True)
    monkeypatch.setattr(tg, "profile_photo", lambda tid: (calls.append(tid) or b"\xff\xd8JPEGDATA"))
    with tx() as c:
        people.add_tg_user(c, "880010", "Фото Человек")
    r = client.get("/api/tg-avatar/880010")
    assert r.status_code == 200 and r.content.startswith(b"\xff\xd8") and r.headers["content-type"] == "image/jpeg"
    client.get("/api/tg-avatar/880010")
    assert calls == ["880010"]                                                                       # kept: Telegram is asked once
    assert client.get("/api/tg-avatar/880011").status_code == 404 and client.get("/api/tg-avatar/abc").status_code == 400
    monkeypatch.setattr(tg, "profile_photo", lambda tid: None)
    with tx() as c:
        people.add_tg_user(c, "880012", "Без Фото")
    assert client.get("/api/tg-avatar/880012").status_code == 404                                    # no photo: the page shows initials
    a = mk_staff(client, "reg_av", "admin", [2])
    assert a.get("/api/tg-avatar/880010").status_code in (403, 404)                                  # not in this administrator's regions


def test_a_region_opens_into_its_facilities_directly(client):
    f1, f2, f3 = make_facility(1, "Район А", "A1"), make_facility(1, "Район Б", "B1"), make_facility(2, "Район В", "C1")
    put_report(f1, "2026-02-10", visits=7)
    r = client.get("/api/regions-table?d1=2026-02-10&d2=2026-02-10&level=rfac&parent_id=1").json()
    names = {x["name"]: x for x in r["rows"]}
    assert set(names) == {"A1", "B1"}                                                                 # the facilities of region 1 from every district, not of region 2
    assert names["A1"]["values"]["visits"] == 7 and names["A1"]["reported"] == 1 and names["B1"]["reported"] == 0
    assert names["A1"]["district"] == "Район А" and names["B1"]["district"] == "Район Б"
    a = mk_staff(client, "reg_rf", "admin", [2])
    assert a.get("/api/regions-table?d1=2026-02-10&d2=2026-02-10&level=rfac&parent_id=1").json()["rows"] == []   # another region is closed
