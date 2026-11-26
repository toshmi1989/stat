import io

import openpyxl
import pytest
from conftest import make_facility
from test_api import mk_staff


def workbook(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ГРИПП ва ОРВИ билан бемор қабул қиладиган стационар муассасалар рўйхати"])
    ws.append(["Т/р", "Муассаса", "Койка сони", "Бош шифокор\nФИШ", "Тел рақами (телеграмм)"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue()


LIST = [
    ["Андижон вилояти "],
    [1, "Андижон шаҳар тиббиёт бирлашмаси", 865, "Мирзаахмедова Малика Маннаповна", "90-211-01-74"],
    [2, "Асака тумани тиббиёт бирлашмаси", 600, "Исомидинов Баходиржон", "998 99 760 32 60"],
    [3, "Хонобод шаҳар тиббиёт бирлашмаси", 100, "Усмонов Дилшодбек", "90-146-00-65\n91-171-23-25"],
    [4, "ОТМ клиникаси (мавжуд бўлса)", 453, "Рахмонов Баҳодир", "93-789-00-22"],
    ["Тошкент шаҳар"],
    [1, "Шаҳар 1-сон БКШ", 425, "Табибова Мавлюда", "88-169-00-03"],
    [2, "Шаҳар 2-сон БКШ", 176, "Собиров Дониёр", ""],
]


def post_preview(client, data):
    return client.post("/api/editor/preview", files={"file": ("list.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})


def test_phones_are_digits_with_998():
    from app import editor
    assert editor.phones("90-211-01-74") == ["998902110174"]
    assert editor.phones("998 99 760 32 60") == ["998997603260"]
    assert editor.phones("99-909-58-02\n91-171-23-25\n") == ["998999095802", "998911712325"]
    assert editor.phones("90-146-00-65                   91-171-23-25") == ["998901460065", "998911712325"]
    assert editor.phones("90 146 00 65 91 171 23 25") == ["998901460065", "998911712325"]
    assert editor.phones("999999999") == ["998999999999"] and editor.phones(None) == [] and editor.phones("Мавжуд эмас") == []


def test_names_that_are_misspelled_still_match_and_numbers_must_agree():
    from app import editor
    k = editor.key
    assert editor.sim(k("Хонобод шаҳар тиббиёт бирлашмаси"), k("Хонобод шахар тиббиёт бирлашмаси ")) > 0.95
    assert editor.sim(k("Хонобод шаҳар тиббиёт бирлашмаси"), k("Xonobod shahar tibbiyot birlashmasi")) > 0.95      # Latin and Cyrillic are the same name
    assert editor.sim(k("Шаҳар 1-сон БКШ"), k("Шаҳар 2-сон БКШ")) < 0.6                                                # another number is another facility
    assert editor.sim(k("Асака тумани тиббиёт бирлашмаси"), k("Андижон тумани тиббиёт бирлашмаси")) < 0.8


def test_parse_reads_regions_and_rows_and_skips_the_footer():
    from app import editor
    rows = editor.parse(workbook(LIST + [[None, "ВССБ бошлиғи", "Имзо"]]))
    assert len(rows) == 6 and rows[0]["region"] == "Андижон вилояти" and rows[0]["beds"] == 865 and rows[0]["fio"].startswith("Мирзаахмедова")
    assert rows[-1]["region"] == "Тошкент шаҳар" and rows[-1]["phone_raw"] == ""
    with pytest.raises(editor.EditorError):
        editor.parse(workbook([]))


def seed():
    # the platform has the same facilities, spelled with errors, and one extra
    a = make_facility(2, "Без района", "Андижон шахар тиббиёт бирлашмаси")
    b = make_facility(2, "Без района", "Асака туман тиббиёт бирлашмаси")
    x = make_facility(2, "Без района", "Какая-то старая больница")
    t = make_facility(14, "Без района", "Шахар 1 сон БКШ")
    return a, b, x, t


def test_preview_matches_by_region_and_offers_new_for_the_rest(client):
    a, b, x, t = seed()
    r = post_preview(client, workbook(LIST)); assert r.status_code == 200, r.text
    pv = r.json()
    rows = {(x_["region_id"], x_["name"]): x_ for x_ in pv["rows"]}
    andijan = [x_ for x_ in pv["rows"] if x_["region_id"] == 2]
    assert {x_["region_text"] for x_ in pv["rows"]} == {"Андижон вилояти", "Тошкент шаҳар"} and pv["problems"] == []
    m1 = rows[(2, "Андижон шаҳар тиббиёт бирлашмаси")]
    assert m1["action"] == "match" and m1["facility_id"] == a and m1["current"]["name"] == "Андижон шахар тиббиёт бирлашмаси" and m1["phone"] == "998902110174"
    assert rows[(2, "Асака тумани тиббиёт бирлашмаси")]["facility_id"] == b
    assert rows[(2, "Хонобод шаҳар тиббиёт бирлашмаси")]["action"] == "new" and rows[(2, "Хонобод шаҳар тиббиёт бирлашмаси")]["phone"] == "998901460065, 998911712325"
    assert rows[(2, "ОТМ клиникаси (мавжуд бўлса)")]["action"] == "skip" and rows[(2, "ОТМ клиникаси (мавжуд бўлса)")]["reason"] == "placeholder"
    assert rows[(14, "Шаҳар 1-сон БКШ")]["facility_id"] == t                       # the city of Tashkent, not the oblast
    assert [u["id"] for u in pv["unmatched"]] == [x]                                # the platform facility that no row claimed
    assert "phone" in rows[(14, "Шаҳар 2-сон БКШ")]["warn"] and len(andijan) == 4


def test_apply_corrects_names_sets_contacts_creates_and_disables(client):
    from app.db import connect
    a, b, x, t = seed()
    pv = post_preview(client, workbook(LIST)).json()
    rows = [{k: r[k] for k in ("region_id", "name", "beds", "fio", "phone", "action", "facility_id")} for r in pv["rows"]]
    res = client.post("/api/editor/apply", json={"rows": rows, "disable": [x]}).json()
    assert res["renamed"] == 3 and res["created"] == 1 + 1 and res["disabled"] == 1 and res["skipped"] == 1 and res["errors"] == [] and res["contacts"] >= 4
    c = connect()
    f = c.execute("SELECT * FROM facilities WHERE id=?", (a,)).fetchone()
    assert f["name_ru"] == "Андижон шаҳар тиббиёт бирлашмаси" and f["name_uz"] == "Andijon shahar tibbiyot birlashmasi" and f["beds"] == 865 and f["active"] == 1
    cts = c.execute("SELECT * FROM facility_contacts WHERE facility_id=?", (a,)).fetchall()
    assert len(cts) == 1 and cts[0]["fio"].startswith("Мирзаахмедова") and cts[0]["phone"] == "998902110174" and cts[0]["kind"] == "main"
    assert c.execute("SELECT active FROM facilities WHERE id=?", (x,)).fetchone()[0] == 0
    new = c.execute("SELECT f.*, d.region_id FROM facilities f JOIN districts d ON d.id=f.district_id WHERE f.name_ru='Хонобод шаҳар тиббиёт бирлашмаси'").fetchone()
    assert new["region_id"] == 2 and new["beds"] == 100 and c.execute("SELECT phone FROM facility_contacts WHERE facility_id=?", (new["id"],)).fetchone()[0] == "998901460065,998911712325"
    assert c.execute("SELECT COUNT(*) FROM audit WHERE action='editor.apply'").fetchone()[0] == 1
    # a second run with the same list changes nothing and creates nothing: everything now matches by name
    pv2 = post_preview(client, workbook(LIST)).json()
    assert pv2["summary"] == {"rows": 6, "match": 5, "new": 0, "skip": 1, "review": 0}
    rows2 = [{k: r[k] for k in ("region_id", "name", "beds", "fio", "phone", "action", "facility_id")} for r in pv2["rows"]]
    res2 = client.post("/api/editor/apply", json={"rows": rows2, "disable": []}).json()
    assert res2["created"] == 0 and res2["renamed"] == 0 and res2["same"] == 5 and res2["contacts"] == 0


def test_contacts_and_beds_on_the_facility_and_the_summary(client):
    f = make_facility(1, "Район А", "Больница К1")
    did = client.get("/api/districts?region_id=1").json()["items"][0]["id"]
    r = client.patch(f"/api/facilities/{f}", json={"beds": "120", "contacts": [{"kind": "main", "fio": " Иванов  Иван ", "phone": "90-123-45-67"}, {"kind": "reserve", "fio": "Петров", "phone": ""}, {"fio": "", "phone": ""}]})
    assert r.status_code == 200, r.text
    item = next(x for x in client.get("/api/facilities?region_id=1&size=200").json()["items"] if x["id"] == f)
    assert item["beds"] == 120 and [(c["kind"], c["fio"], c["phone"]) for c in item["contacts"]] == [("main", "Иванов Иван", "998901234567"), ("reserve", "Петров", "")]
    assert client.patch(f"/api/facilities/{f}", json={"beds": "много"}).status_code == 400
    new = client.post("/api/facilities", json={"district_id": did, "name_ru": "Новая К2", "beds": 50, "contacts": [{"fio": "Сидоров", "phone": "998901111111"}]}).json()["id"]
    assert next(x for x in client.get("/api/facilities?region_id=1&size=200").json()["items"] if x["id"] == new)["contacts"][0]["kind"] == "main"
    summ = client.get("/api/territory-summary").json()["items"]["1"]
    assert summ["total"] == 2 and summ["with_contact"] == 2 and summ["with_phone"] == 2
    client.patch(f"/api/facilities/{f}", json={"contacts": []})                                      # an empty list removes them
    assert client.get("/api/territory-summary").json()["items"]["1"]["with_contact"] == 1
    # deleting the facility removes its contacts
    assert client.delete(f"/api/facilities/{new}?force=1").status_code == 200
    from app.db import connect
    assert connect().execute("SELECT COUNT(*) FROM facility_contacts WHERE facility_id=?", (new,)).fetchone()[0] == 0


def test_editor_is_for_the_territory_managers_and_only_in_their_regions(client):
    make_facility(2, "Без района", "Андижон шахар тиббиёт бирлашмаси")
    make_facility(14, "Без района", "Шахар 1 сон БКШ")
    a = mk_staff(client, "ed_adm", "admin", [2])
    assert post_preview(a, workbook(LIST)).status_code == 403                                         # without the section
    sid = [x for x in client.get("/api/staff").json()["items"] if x["login"] == "ed_adm"][0]["id"]
    client.patch(f"/api/staff/{sid}", json={"can_manage_territories": True})
    pv = post_preview(a, workbook(LIST)).json()
    other = [r for r in pv["rows"] if r["region_id"] == 14]
    assert other and all(r["action"] == "skip" and r["reason"] == "access" for r in other)             # Tashkent is not his
    assert all(u["region_id"] == 2 for u in pv["unmatched"])
    forged = [{"region_id": 14, "name": "Подделка больница", "action": "new", "beds": 1, "fio": "", "phone": ""}]
    res = a.post("/api/editor/apply", json={"rows": forged, "disable": []}).json()
    assert res["created"] == 0 and res["errors"][0]["message"] == "Этот регион вам не назначен"
    assert post_preview(client, b"not an excel file").status_code == 400


def test_a_row_that_looks_alike_but_not_enough_must_be_decided_by_the_person(client):
    from app.db import connect
    # «Андижон шаҳар…» vs «Андижон шаҳри…»-like name: similar, but the same? the person decides; nothing is created by default
    make_facility(2, "Без района", "Андижон шахар касалхонаси тиббиёт марказ")
    pv = post_preview(client, workbook([["Андижон вилояти"], [1, "Андижон шаҳар тиббиёт бирлашмаси", 865, "Мирзаахмедова Малика", "90-211-01-74"]])).json()
    row = pv["rows"][0]
    assert row["action"] == "review" and row["candidates"] and row["facility_id"] is None and pv["summary"]["review"] == 1
    rows = [{k: row[k] for k in ("region_id", "name", "beds", "fio", "phone", "action", "facility_id")}]
    res = client.post("/api/editor/apply", json={"rows": rows, "disable": []}).json()
    assert res["created"] == 0 and res["errors"][0]["message"].startswith("Строка не решена")
    assert connect().execute("SELECT COUNT(*) FROM facilities").fetchone()[0] == 1
    # ў / у and o‘ are one letter for the matching
    from app import editor
    assert editor.sim(editor.key("Тўрткўл туман тиббиёт бирлашмаси"), editor.key("Турткул туман тиббиёт бирлашмаси")) == 1.0
    assert editor.sim(editor.key("Тўрткўл туман тиббиёт бирлашмаси"), editor.key("To‘rtko‘l tuman tibbiyot birlashmasi")) == 1.0


def test_the_editor_links_the_people_of_the_bot_whose_phone_is_in_the_list(client):
    from app import people
    from app.db import connect, tx
    a = make_facility(2, "Без района", "Андижон шахар тиббиёт бирлашмаси")
    with tx() as c:
        people.add_tg_user(c, "820001", "Мирзаахмедова")
        c.execute("UPDATE tg_users SET phone='998902110174' WHERE tg_id='820001'")            # sent to the bot earlier with the button
    pv = post_preview(client, workbook(LIST)).json()
    rows = [{k: r[k] for k in ("region_id", "name", "beds", "fio", "phone", "action", "facility_id")} for r in pv["rows"]]
    res = client.post("/api/editor/apply", json={"rows": rows, "disable": []}).json()
    assert res["linked"] == 1
    assert [(r["facility_id"], r["kind"]) for r in connect().execute("SELECT facility_id, kind FROM assignments WHERE tg_id='820001' AND active=1")] == [(a, "primary")]
    item = next(x for x in client.get("/api/facilities?region_id=2&size=200").json()["items"] if x["id"] == a)
    assert [x["tg_id"] for x in item["assignments"]] == ["820001"]


def test_the_heads_of_the_regional_departments_are_attached_once_and_editable(client):
    from app import db
    from app.db import connect, tx
    c = connect()
    rows = {r["region_id"]: r for r in c.execute("SELECT * FROM region_contacts")}
    assert len(rows) == 14 and rows[1]["fio"] == "Курбанов Мурад Исмайлович" and rows[1]["phone"] == "998977897077"
    assert rows[11]["phone"] == "998958334445,998946124637" and rows[12]["phone"] == "998975950528" and rows[14]["fio"].startswith("Исабеков")     # Tashkent oblast and the city are told apart
    assert "Неъматуллоевич" in rows[6]["fio"] and rows[5]["fio"].startswith("в.в.б. ")
    with tx() as c:
        c.execute("UPDATE region_contacts SET fio='Другой' WHERE region_id=1")
        db.region_heads_v1(c)                                                                         # a second start does not overwrite what the administrator changed
    assert connect().execute("SELECT fio FROM region_contacts WHERE region_id=1").fetchone()[0] == "Другой"
    got = client.get("/api/region-contacts").json()["items"]
    assert got["12"][0]["phone"] == "998975950528" and got["12"][0]["linked"] is False
    r = client.put("/api/regions/12/contacts", json={"contacts": [{"kind": "main", "fio": " Новый  Глава ", "phone": "90-111-22-33"}, {"kind": "reserve", "fio": "Резерв", "phone": ""}, {"fio": "", "phone": ""}]})
    assert r.status_code == 200, r.text
    assert [(x["kind"], x["fio"], x["phone"]) for x in client.get("/api/region-contacts").json()["items"]["12"]] == [("main", "Новый Глава", "998901112233"), ("reserve", "Резерв", "")]
    assert client.put("/api/regions/999/contacts", json={"contacts": []}).status_code == 404 and client.put("/api/regions/12/contacts", json={"contacts": "x"}).status_code == 400
    # only the person with the section «Территории» and only in his own regions
    a = mk_staff(client, "rc_adm", "admin", [1])
    assert a.put("/api/regions/1/contacts", json={"contacts": []}).status_code == 403
    sid = [x for x in client.get("/api/staff").json()["items"] if x["login"] == "rc_adm"][0]["id"]
    client.patch(f"/api/staff/{sid}", json={"can_manage_territories": True})
    assert a.put("/api/regions/1/contacts", json={"contacts": [{"kind": "main", "fio": "Свой", "phone": ""}]}).status_code == 200
    assert a.put("/api/regions/2/contacts", json={"contacts": []}).status_code == 403 and set(a.get("/api/region-contacts").json()["items"]) == {"1"}


def test_proposals_of_one_region_and_the_counts_per_region(client):
    from app.db import tx
    with tx() as c:
        for rid, name in ((1, "А1"), (1, "А2"), (2, "Б1")):
            c.execute("INSERT INTO facility_proposals(region_id, kind, name, tg_id, created_at) VALUES (?,?,?,?,datetime('now'))", (rid, "add", name, "1"))
    r = client.get("/api/facility-proposals?region_id=1").json()
    assert {p["name"] for p in r["items"]} == {"А1", "А2"} and r["per_region"] == {"1": 2, "2": 1} and r["new"] == 3
    c_ = client.get("/api/facility-proposals?count_only=1&status=new").json()
    assert c_["items"] == [] and c_["per_region"] == {"1": 2, "2": 1}
