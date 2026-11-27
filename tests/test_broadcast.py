from datetime import datetime

import pytest
from conftest import make_facility, put_report
from test_api import mk_staff


@pytest.fixture
def world(env):
    """Two regions; a head of region 1 and three responsible people; today's reports: B1 sent, B2 not, B3 sent in region 2."""
    from app import editor, people
    from app.db import tx
    f1, f2, f3 = make_facility(1, "Район А", "Больница Б1"), make_facility(1, "Район Б", "Больница Б2"), make_facility(2, "Район В", "Больница Б3")
    su = {"id": 1, "role": "super_admin", "regions": None}
    with tx() as c:
        for tid, name in (("880001", "Глава"), ("880002", "Один"), ("880003", "Два"), ("880004", "Три")):
            people.add_tg_user(c, tid, name)
        c.execute("UPDATE tg_users SET lang='uz' WHERE tg_id='880003'")
        c.execute("UPDATE tg_users SET phone='998977897077' WHERE tg_id='880001'")                     # his confirmed phone is the one of the head of the region in the list
        people.assign_region(c, su, "880001", 1)
        people.assign(c, su, "880002", f1)
        people.assign(c, su, "880003", f2)
        people.assign(c, su, "880004", f3)
        editor.replace_contacts(c, f2, [{"kind": "main", "fio": "Петров", "phone": "93-000-00-03"}])
    put_report(f1, "2026-02-10"); put_report(f3, "2026-02-10")
    return {"f1": f1, "f2": f2, "f3": f3, "su": su}


def ids(c, user, spec):
    from app import broadcast
    return sorted(p["tg_id"] for p in broadcast.recipients(c, user, spec))


def test_the_audience_is_a_role_a_region_and_the_report_of_today(world):
    from app.db import connect
    c, su = connect(), world["su"]
    assert ids(c, su, {"roles": "all"}) == ["880001", "880002", "880003", "880004"]
    assert ids(c, su, {"roles": "heads"}) == ["880001"] and ids(c, su, {"roles": "responsibles"}) == ["880002", "880003", "880004"]
    assert ids(c, su, {"roles": "responsibles", "regions": [2]}) == ["880004"]
    assert ids(c, su, {"roles": "responsibles", "report": "unsent"}) == ["880003"]                  # only the owner of B2 has not sent
    assert ids(c, su, {"roles": "responsibles", "report": "sent"}) == ["880002", "880004"]
    assert ids(c, su, {"roles": "heads", "report": "unsent"}) == ["880001"]                         # the head of region 1: one of his facilities has not sent
    assert ids(c, su, {"roles": "all", "report": "unsent", "regions": [2]}) == []                    # nobody in region 2 owes
    assert ids(c, su, {"mode": "unsent"}) == ["880001", "880003"] and ids(c, su, {"mode": "regions", "regions": [1]}) == ["880001", "880002", "880003"]      # the old form still works


def test_the_figures_in_the_text_are_the_person_s_own(world):
    from app import broadcast
    from app.db import connect
    c = connect()
    head = broadcast.personalize(c, "{region}: {sent}/{total} ({percent}%), не сдали {unsent}:\n{unsent_list}", "880001", "ru")
    assert head.startswith("Республика Каракалпакстан: 1/2 (50%), не сдали 1:") and "1. Больница Б2 — 👤 Петров · +998 93 000 00 03" in head     # the head gets who to call
    one = broadcast.personalize(c, "{name}: «{facility}» до {deadline}; {status}", "880003", "uz")
    assert one.startswith("Два: «Больница Б2» до 18:00;") and "Больница Б2 — ❌ topshirilmagan" in one                                             # in the language of the person
    assert "✅ сдан" in broadcast.personalize(c, "{status}", "880002", "ru")
    assert broadcast.personalize(c, "Без подстановок", "880002", "ru") == "Без подстановок" and broadcast.personalize(c, "{нет} {unknown}", "880002", "ru") == "{нет} {unknown}"
    assert broadcast.personalize(c, "{date}", "880002", "ru") == "10.02.2026"
    all_sent = broadcast.personalize(c, "{unsent_list}", "880004", "ru")                           # nobody owes in region 2: a word, not an empty line
    assert all_sent == "все сдали" or all_sent.startswith("1.")


def test_every_person_gets_a_text_made_for_him_when_it_is_sent(world, client, monkeypatch):
    from app import broadcast, tg
    broadcast.PACE = 0
    sent = []
    monkeypatch.setattr(tg, "send", lambda chat, text, markup=None: (sent.append((str(chat), text)) or (True, "")))
    pv = client.post("/api/broadcasts/preview", json={"audience": {"roles": "responsibles", "report": "unsent"}, "text_ru": "{name}, {facility}", "text_uz": "{name}: {facility}", "sample_tg_id": "880003"}).json()
    assert pv["total"] == 1 and pv["sample"]["tg_id"] == "880003" and "Два: Больница Б2" in pv["sample"]["text"] and "{" not in pv["sample"]["text"]
    assert pv["sample_uz"].endswith("{name}: {facility}")                                                 # the generic one keeps the placeholders
    aud = client.post("/api/broadcasts/audience", json={"audience": {"roles": "responsibles", "report": "sent", "regions": [1]}}).json()
    assert aud["total"] == 1 and aud["list"][0]["tg_id"] == "880002"
    bid = client.post("/api/broadcasts", json={"audience": {"roles": "all"}, "text_ru": "{name} → {sent}/{total}", "text_uz": "{name} → {sent}/{total}", "confirm": True}).json()["id"]
    import time
    for _ in range(100):
        if client.get("/api/broadcasts").json()["items"][0]["status"] == "done":
            break
        time.sleep(0.05)
    by = dict(sent)
    assert "Глава → 1/2" in by["880001"] and "Один → 1/1" in by["880002"] and "Два → 0/1" in by["880003"] and "Три → 1/1" in by["880004"]


def test_ready_made_and_saved_templates(world, client):
    items = client.get("/api/broadcast-templates").json()
    ids_ = [t["id"] for t in items["items"]]
    assert {"remind", "head_summary", "free"} <= set(ids_) and "unsent_list" in items["placeholders"]
    rem = next(t for t in items["items"] if t["id"] == "remind")
    assert rem["audience"] == {"roles": "responsibles", "regions": [], "report": "unsent"} and "{facility}" in rem["text_ru"] and "{facility}" in rem["text_uz"] and rem["builtin"] is True
    tid = client.post("/api/broadcast-templates", json={"name": "Мой шаблон", "text_ru": "Привет, {name}", "text_uz": "", "audience": {"roles": "heads"}}).json()["id"]
    mine = next(t for t in client.get("/api/broadcast-templates").json()["items"] if t["id"] == tid)
    assert mine["builtin"] is False and mine["audience"]["roles"] == "heads" and mine["text_ru"] == "Привет, {name}"
    assert client.post("/api/broadcast-templates", json={"name": "x", "text_ru": "t"}).status_code == 400                # a name is needed
    a = mk_staff(client, "tpl_adm", "admin", [1])
    assert a.delete(f"/api/broadcast-templates/{tid}").status_code in (403, 404)                                          # not his
    assert client.delete(f"/api/broadcast-templates/{tid}").status_code == 200


def test_a_broadcast_on_a_schedule_goes_at_its_time_once_a_day(world, client, monkeypatch):
    from app import broadcast, tg
    from app.db import connect
    broadcast.PACE = 0
    sent = []
    monkeypatch.setattr(tg, "send", lambda chat, text, markup=None: (sent.append((str(chat), text)) or (True, "")))
    base = {"audience": {"roles": "heads"}, "text_ru": "Сводка: {sent}/{total}", "text_uz": ""}
    assert client.post("/api/broadcast-schedules", json=base | {"repeat": "daily", "at_time": "25:00"}).status_code == 400
    assert client.post("/api/broadcast-schedules", json=base | {"repeat": "once", "at_time": "18:00", "run_date": "2020-01-01"}).status_code == 400     # the past
    daily = client.post("/api/broadcast-schedules", json=base | {"repeat": "daily", "at_time": "18:30", "title": "Вечерняя сводка"}).json()["id"]
    wk = client.post("/api/broadcast-schedules", json=base | {"repeat": "weekdays", "at_time": "09:00"}).json()["id"]
    once = client.post("/api/broadcast-schedules", json=base | {"repeat": "once", "at_time": "10:00", "run_date": "2026-03-02"}).json()["id"]      # a Monday
    assert {x["id"] for x in client.get("/api/broadcast-schedules").json()["items"]} == {daily, wk, once}
    r = broadcast.run_due(datetime(2026, 2, 10, 18, 29))                                                                                                # a Tuesday: the weekdays one (09:00) goes, the daily one (18:30) is not yet due
    assert [x["id"] for x in r] == [wk]
    r = broadcast.run_due(datetime(2026, 2, 14, 18, 31))                                                                                                # a Saturday after 18:30
    assert [x["id"] for x in r] == [daily] and r[0]["result"] == "отправлено"                                                                          # weekdays do not go on Saturday
    assert broadcast.run_due(datetime(2026, 2, 14, 19, 0)) == []                                                                                       # once a day
    r = broadcast.run_due(datetime(2026, 3, 2, 18, 40))
    assert {x["id"] for x in r} == {daily, wk, once}                                                                                                    # Monday: all three are due
    sch = {x["id"]: x for x in client.get("/api/broadcast-schedules").json()["items"]}
    assert sch[once]["active"] == 0 and sch[once]["last_result"] == "отправлено" and sch[daily]["active"] == 1 and sch[daily]["last_broadcast_id"]
    import time
    time.sleep(0.4)
    assert any("Сводка: 1/2" in t for c, t in sent if c == "880001")
    # a one-time broadcast of a day that has gone by without being sent is closed as missed, not sent late
    late = client.post("/api/broadcast-schedules", json=base | {"repeat": "once", "at_time": "10:00", "run_date": "2026-03-05"}).json()["id"]
    assert broadcast.run_due(datetime(2026, 3, 7, 12, 0)) == [] and connect().execute("SELECT active, last_result FROM broadcast_schedules WHERE id=?", (late,)).fetchone()[0] == 0
    # pause and delete
    assert client.post(f"/api/broadcast-schedules/{daily}/active", json={"active": False}).status_code == 200
    assert [x["id"] for x in broadcast.run_due(datetime(2026, 3, 3, 19, 0))] == [wk]                                                                     # the paused daily one stays silent, the weekdays one goes
    assert client.delete(f"/api/broadcast-schedules/{daily}").status_code == 200 and client.delete(f"/api/broadcast-schedules/{daily}").status_code == 404


def test_a_regional_administrator_cannot_reach_another_region_by_a_schedule(world, client):
    from app import broadcast
    a = mk_staff(client, "sch_adm", "admin", [1])
    from app.db import connect
    c0 = connect(); c0.execute("UPDATE staff SET can_manage_users=1 WHERE login='sch_adm'"); c0.commit(); c0.close()
    base = {"text_ru": "x", "repeat": "daily", "at_time": "10:00"}
    assert a.post("/api/broadcast-schedules", json=base | {"audience": {"roles": "all", "regions": [2]}}).status_code == 403
    sid = a.post("/api/broadcast-schedules", json=base | {"audience": {"roles": "all"}}).json()["id"]
    assert client.get("/api/broadcast-schedules").json()["items"][0]["id"] == sid and a.get("/api/broadcast-schedules").json()["items"][0]["id"] == sid
    assert mk_staff(client, "sch_view", "viewer", [1]).get("/api/broadcast-schedules").status_code == 403


def test_the_heads_are_the_people_of_the_list_not_everyone_who_has_the_access_to_a_region(world, client):
    """One head per region (the main person of the list, confirmed by his phone). Many responsible people hold the access to a whole region: they are the responsible ones."""
    from app import people
    from app.db import connect, tx
    with tx() as c:
        for i in range(5):                                                                              # five ordinary people with the access to region 1 (as it is in the real system)
            people.add_tg_user(c, f"8900{i}", f"Обычный{i}")
            people.assign_region(c, world["su"], f"8900{i}", 1)
        people.add_tg_user(c, "889999", "Глава Андижана")
        c.execute("UPDATE tg_users SET phone='998903805590' WHERE tg_id='889999'")                    # the phone of the head of Andijan: no access linked yet, he is a head all the same
        people.add_tg_user(c, "889998", "Резерв")
        c.execute("UPDATE tg_users SET phone='998000000000' WHERE tg_id='889998'")                    # a phone that is in nobody's list
        people.assign_region(c, world["su"], "889998", 1)
    c = connect()
    heads = ids(c, world["su"], {"roles": "heads"})
    assert heads == ["880001", "889999"]                                                              # not the five ordinary ones
    assert ids(c, world["su"], {"roles": "heads", "regions": [1]}) == ["880001"]
    resp = ids(c, world["su"], {"roles": "responsibles"})
    assert all(f"8900{i}" in resp for i in range(5)) and "889998" in resp and "880001" not in resp and "889999" not in resp     # a head is not counted twice
    assert set(ids(c, world["su"], {"roles": "all"})) == set(heads) | set(resp)
    aud = client.post("/api/broadcasts/audience", json={"audience": {"roles": "heads"}}).json()
    assert aud["total"] == 2 and len(aud["unlinked_heads"]) == 12                                      # the other 12 regions have a head in the list that nobody has confirmed yet
    assert {x["region_id"] for x in aud["unlinked_heads"]}.isdisjoint({1, 2}) and aud["unlinked_heads"][0]["fio"]
    assert client.post("/api/broadcasts/audience", json={"audience": {"roles": "responsibles"}}).json()["unlinked_heads"] == []


def test_the_facility_in_a_reminder_is_the_one_that_has_not_sent_and_is_never_empty(world):
    """A person with access to a region and no facility of his own got «» in the reminder; now he gets the facilities of the region that owe, shortened."""
    from app import broadcast, people
    from app.db import connect, tx
    su = world["su"]
    for i in range(5):
        make_facility(1, "Район А", f"Поликлиника {i}")                                              # five more that have not sent today
    with tx() as c:
        people.add_tg_user(c, "880009", "Шукуров")
        people.assign_region(c, su, "880009", 1)                                                       # access to the region, no facility of his own
    c = connect()
    text = broadcast.personalize(c, "Сводка по «{facility}» не получена", "880009", "ru")
    assert "Больница Б2" in text and "(+" in text and "«»" not in text                                   # the ones that owe: three names and how many more
    assert broadcast.personalize(c, "{facility}", "880002", "ru") == "Больница Б1"                         # sent already: all of his own
    assert broadcast.personalize(c, "{facility}", "880003", "ru") == "Больница Б2"                         # not sent: this one
    assert broadcast.personalize(c, "{facility}", "880001", "ru").count(",") == 2                          # the head of the region: three names of those who owe
