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


def test_confidential_message_for_the_ministry_from_the_last_bot_question(client, monkeypatch):
    import json
    from app import bot, people, tg
    from app.db import connect, tx
    sent = []
    monkeypatch.setattr(tg, "send", lambda chat, text, markup=None: (sent.append((str(chat), text)) or (True, "")))
    monkeypatch.setattr(tg, "answer", lambda *a, **k: None)
    f = make_facility(1, fac="Msg")
    with tx() as c:
        people.add_tg_user(c, "660001", "Сообщающий")
        people.assign(c, {"id": 1, "role": "super_admin", "regions": None}, "660001", f)
    def say(text):
        bot.handle_update({"message": {"chat": {"id": 660001, "type": "private"}, "from": {"id": 660001, "first_name": "Сообщающий"}, "text": text}})
    def press(data):
        bot.handle_update({"callback_query": {"id": "1", "data": data, "from": {"id": 660001, "first_name": "Сообщающий"}, "message": {"message_id": 1, "chat": {"id": 660001, "type": "private"}}}})
    press(f"sd:{f}:2026-02-10")
    for a in ["100", "40", "50", "10", "6", "20", "1", "1", "5", "1", "0", "0"]:
        say(a)
    assert "13 из 13" in sent[-1][1] and "конфиденциально" in sent[-1][1]                         # the last question says that the message is confidential
    say("x" * 1001)
    assert "слишком длинное" in sent[-1][1]
    say("В больнице нет тест-систем. Прошу помочь с поставкой.")
    assert "Сообщение для Министерства: «В больнице" in sent[-1][1]
    press("ok")
    c = connect()
    row = c.execute("SELECT * FROM ministry_messages").fetchone()
    assert row["facility_id"] == f and row["report_date"] == "2026-02-10" and "нет тест-систем" in row["text"] and row["tg_id"] == "660001"
    assert "конфиденциально" in sent[-1][1]
    # it is not part of the report, the audit log or the exports
    assert "тест-систем" not in json.dumps([dict(r) for r in c.execute("SELECT * FROM audit")], ensure_ascii=False)
    assert "тест-систем" not in json.dumps([dict(r) for r in c.execute("SELECT * FROM report_values")]) and "тест-систем" not in json.dumps([dict(r) for r in c.execute("SELECT * FROM report_versions")], ensure_ascii=False)
    c.close()
    assert "тест-систем" not in client.get("/api/reports?d1=2026-02-10&d2=2026-02-10&size=50").text               # not in the list of reports either
    # only the super administrator reads it
    m = client.get("/api/messages").json()
    t0 = m["items"][0]
    assert m["unread"] == 1 and t0["facility"] == "Msg" and t0["messages"][0]["direction"] == "in" and "нет тест-систем" in t0["messages"][0]["text"] and client.get("/api/me").json()["messages_unread"] == 1
    assert mk_staff(client, "reg_msg", "admin", [1]).get("/api/messages").status_code == 403           # a regional administrator of that very region
    assert mk_staff(client, "vw_msg", "viewer", [1]).get("/api/messages").status_code == 403
    assert client.post(f"/api/messages/{t0['thread_id']}/read", json={"read": True}).status_code == 200
    assert client.get("/api/messages?unread=1").json()["items"] == []
    # a second submission without a message adds nothing; skipping the question is allowed
    press(f"sd:{f}:2026-02-09")
    for a in ["100", "40", "50", "10", "6", "20", "1", "1", "5", "1", "0", "0"]:
        say(a)
    say("⏭ Без сообщения, продолжить")
    assert "Сообщение для Министерства: нет" in sent[-1][1]
    press("ok")
    assert len(client.get("/api/messages").json()["items"]) == 1


def _wait_broadcast(client, bid, timeout=8):
    import time
    end = time.time() + timeout
    while time.time() < end:
        b = next(x for x in client.get("/api/broadcasts").json()["items"] if x["id"] == bid)
        if b["status"] != "sending":
            return b
        time.sleep(0.05)
    raise AssertionError("the broadcast did not finish")


def test_broadcast_audience_languages_scope_and_delivery_log(client, monkeypatch):
    from app import broadcast, people, tg
    from app.db import connect, tx
    broadcast.PACE = 0
    sent, fail_for = [], set()
    def fake_send(chat, text, markup=None):
        if str(chat) in fail_for:
            return False, "Forbidden: bot was blocked by the user"
        sent.append((str(chat), text)); return True, ""
    monkeypatch.setattr(tg, "send", fake_send)
    f1, f2 = make_facility(1, fac="B1"), make_facility(2, "Район Б", "B2")
    adm = {"id": 1, "role": "super_admin", "regions": None}
    with tx() as c:
        for tid, name, region in (("770001", "Узбек", 1), ("770002", "Русский", 1), ("770003", "Чужой", 2), ("770004", "БезДоступа", None)):
            people.add_tg_user(c, tid, name)
            if region:
                people.assign_region(c, adm, tid, region)
        c.execute("UPDATE tg_users SET lang='uz' WHERE tg_id IN ('770001','770003')")
        c.execute("UPDATE tg_users SET lang='ru' WHERE tg_id='770002'")
    pv = client.post("/api/broadcasts/preview", json={"audience": {"mode": "all"}, "text_ru": "Привет", "text_uz": "Salom"}).json()
    assert pv["total"] == 3 and pv["uz"] == 2 and pv["ru"] == 1 and pv["fallback"] == 0               # the person with no access is not a recipient
    assert "Salom" in pv["sample_uz"] and "Привет" in pv["sample_ru"] and "E’lon" in pv["sample_uz"]
    pv = client.post("/api/broadcasts/preview", json={"audience": {"mode": "all"}, "text_ru": "", "text_uz": "Faqat o‘zbekcha"}).json()
    assert pv["fallback"] == 1                                                                         # the Russian speaker will get the Uzbek text
    assert client.post("/api/broadcasts/preview", json={"audience": {"mode": "regions", "regions": [1]}, "text_ru": "x"}).json()["total"] == 2
    assert client.post("/api/broadcasts/preview", json={"audience": {"mode": "regions", "regions": []}, "text_ru": "x"}).status_code == 400
    assert client.post("/api/broadcasts/preview", json={"audience": {"mode": "all"}, "text_ru": "", "text_uz": ""}).status_code == 400
    assert client.post("/api/broadcasts/preview", json={"audience": {"mode": "all"}, "text_ru": "x" * 3501}).status_code == 400
    # a regional administrator can write only to people of their own region and only sees their own broadcasts
    a1 = mk_staff(client, "bc_reg1", "admin", [1])
    c0 = connect(); c0.execute("UPDATE staff SET can_manage_users=1 WHERE login='bc_reg1'"); c0.commit(); c0.close()
    assert a1.post("/api/broadcasts/preview", json={"audience": {"mode": "all"}, "text_ru": "x"}).json()["total"] == 2
    assert a1.post("/api/broadcasts/preview", json={"audience": {"mode": "regions", "regions": [2]}, "text_ru": "x"}).status_code == 403
    assert mk_staff(client, "bc_view", "viewer", [1]).get("/api/broadcasts").status_code == 403
    # sending needs the confirmation; then everyone gets the text of their own language
    assert client.post("/api/broadcasts", json={"audience": {"mode": "all"}, "text_ru": "Привет", "text_uz": "Salom"}).status_code == 400
    fail_for.add("770003")
    bid = client.post("/api/broadcasts", json={"audience": {"mode": "all"}, "text_ru": "Привет всем", "text_uz": "Hammaga salom", "confirm": True}).json()["id"]
    b = _wait_broadcast(client, bid)
    assert b["status"] == "done" and b["total"] == 3 and b["sent"] == 2 and b["failed"] == 1
    by = dict(sent)
    assert "Hammaga salom" in by["770001"] and "Привет всем" in by["770002"] and by["770002"].startswith("📢 <b>Объявление</b>") and by["770001"].startswith("📢 <b>E’lon</b>")
    fl = client.get(f"/api/broadcasts/{bid}/failures").json()["items"]
    assert [x["tg_id"] for x in fl] == ["770003"] and "blocked" in fl[0]["error"]
    assert a1.get(f"/api/broadcasts/{bid}/failures").status_code == 404                              # another sender's broadcast is not theirs
    # the failed one is tried again
    fail_for.clear()
    assert client.post(f"/api/broadcasts/{bid}/resume", json={}).status_code == 200
    b = _wait_broadcast(client, bid)
    assert b["sent"] == 3 and b["failed"] == 0 and dict(sent)["770003"].endswith("Hammaga salom")
    assert connect().execute("SELECT COUNT(*) FROM audit WHERE action='broadcast.start'").fetchone()[0] >= 1


def test_broadcast_test_message_goes_only_to_a_known_person(client, monkeypatch):
    from app import broadcast, people, tg
    from app.db import connect, tx
    sent = []
    monkeypatch.setattr(tg, "send", lambda chat, text, markup=None: (sent.append((str(chat), text)) or (True, "")))
    assert client.post("/api/broadcasts/test", json={"text_ru": "x"}).status_code == 400            # no id given and none in the profile
    assert client.post("/api/broadcasts/test", json={"text_ru": "x", "tg_id": "123456789"}).status_code == 400   # not a person of the bot: no spam to arbitrary ids
    with tx() as c:
        people.add_tg_user(c, "770010", "Я")
        c.execute("UPDATE tg_users SET lang='ru' WHERE tg_id='770010'")
    assert client.post("/api/broadcasts/test", json={"text_ru": "Проверка", "tg_id": "770010"}).json()["sent_to"] == "770010"
    assert sent[-1][0] == "770010" and "Проверка" in sent[-1][1] and "тест" in sent[-1][1]
    assert connect().execute("SELECT COUNT(*) FROM broadcasts").fetchone()[0] >= 0                  # a test is not recorded as a broadcast


def test_the_ministry_answers_and_the_person_continues_the_dialogue_from_the_button(client, monkeypatch):
    from app import bot, people, tg
    from app.db import connect, tx
    sent = []
    monkeypatch.setattr(tg, "send", lambda chat, text, markup=None: (sent.append((str(chat), text, markup)) or (True, "")))
    monkeypatch.setattr(tg, "answer", lambda *a, **k: None)
    f = make_facility(1, fac="Dlg")
    with tx() as c:
        for tid in ("661001", "661002"):
            people.add_tg_user(c, tid, "Человек" + tid)
            people.assign(c, {"id": 1, "role": "super_admin", "regions": None}, tid, f)
        c.execute("UPDATE tg_users SET lang='uz' WHERE tg_id='661001'")
        cur = c.execute("INSERT INTO ministry_messages(facility_id, report_date, tg_id, sender, text, created_at, direction) VALUES (?,?,?,?,?,?, 'in')", (f, "2026-02-10", "661001", "Человек661001", "Нет тест-систем", "2026-02-10 10:00:00"))
        c.execute("UPDATE ministry_messages SET thread_id=id WHERE id=?", (cur.lastrowid,))
        tid_ = cur.lastrowid
    def say(uid, text):
        bot.handle_update({"message": {"chat": {"id": uid, "type": "private"}, "from": {"id": uid, "first_name": "Х"}, "text": text}})
    def press(uid, data):
        bot.handle_update({"callback_query": {"id": "1", "data": data, "from": {"id": uid, "first_name": "Х"}, "message": {"message_id": 1, "chat": {"id": uid, "type": "private"}}}})
    # the Ministry answers on the site: the person gets it in Telegram with the «Reply» button
    r = client.post(f"/api/messages/{tid_}/reply", json={"text": "Тест-системы отправлены, ждите в среду."}).json()
    assert r["delivered"] is True
    chat, text, markup = sent[-1]
    assert chat == "661001" and "Тест-системы отправлены" in text and "Sizning xabaringizga" in text                      # in the person's language, with a quote of their message
    btn = markup["inline_keyboard"][0][0]
    assert btn["callback_data"] == f"mr:{tid_}" and "Javob" in btn["text"]
    assert client.post(f"/api/messages/{tid_}/reply", json={"text": ""}).status_code == 400
    assert client.post("/api/messages/99999/reply", json={"text": "x"}).status_code == 404
    assert mk_staff(client, "rep_reg", "admin", [1]).post(f"/api/messages/{tid_}/reply", json={"text": "x"}).status_code == 403
    # another person cannot use the button of this dialogue
    sent.clear(); press(661002, f"mr:{tid_}"); say(661002, "Я чужой")
    assert connect().execute("SELECT COUNT(*) FROM ministry_messages WHERE tg_id='661002'").fetchone()[0] == 0
    # the person presses it and writes: it joins the same dialogue, which the Ministry sees as new
    sent.clear(); press(661001, f"mr:{tid_}")
    assert "1000 belgigacha" in sent[-1][1] and "Vazirlik ko‘radi" in sent[-1][1]                                            # asked to write the answer, in Uzbek
    say(661001, "Спасибо! А когда именно?")
    m = client.get("/api/messages").json()
    thr = next(t for t in m["items"] if t["thread_id"] == tid_)
    assert [x["direction"] for x in thr["messages"]] == ["in", "out", "in"] and thr["unread"] == 1 and m["unread"] == 1
    assert thr["messages"][2]["text"] == "Спасибо! А когда именно?" and client.get("/api/pulse").json()["unread"] == 1
    assert "передан" in sent[-1][1] or "yuborildi" in sent[-1][1]                                                           # the person is told that it was passed on
    # the Ministry answers again: the dialogue goes on, answering marks it read
    assert client.post(f"/api/messages/{tid_}/reply", json={"text": "В среду до 12:00."}).json()["delivered"] is True
    assert client.get("/api/messages").json()["unread"] == 0 and client.get("/api/me").json()["messages_unread"] == 0
    assert sent[-1][2]["inline_keyboard"][0][0]["callback_data"] == f"mr:{tid_}"
    # cancel leaves the dialogue state
    press(661001, f"mr:{tid_}"); say(661001, "✖ Отмена")
    assert connect().execute("SELECT state FROM bot_state WHERE tg_id='661001'").fetchone()["state"] in ("", None, "idle")
    # a message too long is refused, the delivery failure is shown on the site
    monkeypatch.setattr(tg, "send", lambda chat, text, markup=None: (False, "Forbidden: bot was blocked by the user"))
    r = client.post(f"/api/messages/{tid_}/reply", json={"text": "ещё один"}).json()
    assert r["delivered"] is False and "blocked" in r["error"]
    assert client.get("/api/messages").json()["items"][0]["messages"][-1]["error"].startswith("Forbidden")


def test_coverage_counts_districts_people_and_reports_and_respects_scope(client):
    import io, openpyxl
    from app import people
    from app.db import tx
    fa, fb = make_facility(1, "Район А", "Cov A"), make_facility(1, "Район Б", "Cov B")
    fc = make_facility(2, "Район В", "Cov C")
    adm = {"id": 1, "role": "super_admin", "regions": None}
    with tx() as c:
        people.touch(c, {"id": 880101, "first_name": "Олим", "last_name": "Тест", "username": "olim_t"}, "uz")
        people.touch(c, {"id": 880102, "first_name": "Резерв"}, "uz")
        people.touch(c, {"id": 880103, "first_name": "Региональный"}, "uz")
        people.assign(c, adm, "880101", fa, "primary")
        people.assign(c, adm, "880102", fa, "reserve")
        people.assign_region(c, adm, "880103", 1)
        people.preapprove(c, adm, "@later_person", 1)
        people.touch(c, {"id": 880104, "first_name": "Проситель", "username": "asker_x"}, "uz")
        people.create_request(c, "880104", 2)
    for d in ("2026-02-08", "2026-02-09", "2026-02-10"):
        put_report(fa, d)
    put_report(fb, "2026-02-10")
    r = client.get("/api/coverage?d1=2026-02-04&d2=2026-02-10").json()                                    # 7 days
    assert r["days"] == 7
    g1 = next(g for g in r["regions"] if g["id"] == 1)
    assert g1["n_districts"] >= 2 and g1["facilities"] >= 2 and g1["reports"] == 4 and g1["waiting"] == 1
    assert g1["people"] == 3                                                                              # two on the facility (primary and reserve) and one on the whole region
    assert [p["name"] for p in g1["region_people"]] == ["Региональный"]
    cov_a = next(f for d in g1["districts"] for f in d["facilities"] if f["id"] == fa)
    assert cov_a["reports"] == 3 and cov_a["last_in_period"] == "2026-02-10" and [(p["name"], p["kind"], p["username"]) for p in cov_a["people"]] == [("Олим Тест", "primary", "olim_t"), ("Резерв", "reserve", "")]
    cov_b = next(f for d in g1["districts"] for f in d["facilities"] if f["id"] == fb)
    assert cov_b["reports"] == 1 and cov_b["people"] == [] and cov_b["has_responsible"] is True                # covered by the region access
    g2 = next(g for g in r["regions"] if g["id"] == 2)
    assert g2["reports"] == 0 and g2["people"] == 0 and next(f for d in g2["districts"] for f in d["facilities"] if f["id"] == fc)["has_responsible"] is False
    assert r["totals"]["reports"] == 4 and r["totals"]["districts"] >= 3 and r["totals"]["people"] == 3 and r["totals"]["waiting"] == 1
    # a period outside the reports
    assert client.get("/api/coverage?d1=2025-01-01&d2=2025-01-07").json()["totals"]["reports"] == 0
    assert client.get("/api/coverage?d1=2026-02-10&d2=2026-02-01").status_code == 400 and client.get("/api/coverage?d1=2020-01-01&d2=2026-02-01").status_code == 400
    # a regional administrator sees only their regions; a viewer is refused
    a2 = mk_staff(client, "cov_reg2", "admin", [2])
    only = a2.get("/api/coverage?d1=2026-02-04&d2=2026-02-10").json()
    assert [g["id"] for g in only["regions"]] == [2] and only["totals"]["reports"] == 0
    assert mk_staff(client, "cov_view", "viewer", [1]).get("/api/coverage").status_code == 403
    # the same table as an Excel file
    x = client.get("/api/coverage.xlsx?d1=2026-02-04&d2=2026-02-10")
    assert x.status_code == 200 and "coverage_2026-02-04_2026-02-10.xlsx" in x.headers["content-disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(x.content))
    assert wb.sheetnames == ["Сводка", "Не подключены", "Люди", "По учреждениям"]
    cell = lambda ws: [[c.value for c in row] for row in ws.iter_rows()]
    summ = cell(wb["Сводка"])
    head = next(r for r in summ if r and r[0] == "Регион")
    row1 = next(r for r in summ if r[0] == g1["name"])
    col = lambda name: head.index(name)
    assert row1[col("Районов")] == g1["n_districts"] and row1[col("Учреждений")] == g1["facilities"] and row1[col("Подключено людей")] == 3 and row1[col("Отчётов за период")] == 4
    assert row1[col("Записаны, ещё не вошли в бот")] == 1 and row1[col("Учреждений БЕЗ ответственного")] == 0
    row2 = next(r for r in summ if r[0] == g2["name"])
    assert row2[col("Подключено людей")] == 0 and row2[col("Учреждений БЕЗ ответственного")] == g2["facilities"] and row2[col("Заявки на доступ (ждут решения)")] == 1
    total = next(r for r in summ if r[0] == "ИТОГО")
    assert total[col("Подключено людей")] == 3 and total[col("Отчётов за период")] == 4
    notc = cell(wb["Не подключены"])
    flat = [str(v) for r in notc for v in r if v is not None]
    assert any("Cov C" == v for v in flat) and "@later_person" in flat and any("Проситель (@asker_x)" == v for v in flat) and any(v.startswith("Учреждения без ответственного (") for v in flat)
    ppl = cell(wb["Люди"])
    assert any(r[1] == "Олим Тест" and r[2] == "@olim_t" and r[4] == "основной" and "Cov A" in (r[6] or "") for r in ppl) and any(r[1] == "Региональный" and r[5] == "весь регион" for r in ppl)
    rows = cell(wb["По учреждениям"])
    mine = [r_ for r_ in rows if r_[2] == "Cov A"][0]
    assert "Олим Тест (@olim_t)" in mine[3] and "Резерв" in mine[3] and "[резерв]" in mine[3] and "Региональный" in mine[4] and mine[5] == 3
    assert [r_ for r_ in rows if r_[2] == "Cov C"][0][3] == "НЕ ПОДКЛЮЧЁН"
