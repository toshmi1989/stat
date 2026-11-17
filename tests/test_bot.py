from datetime import datetime

import pytest
from conftest import make_facility, put_report

SENT = []
DOCS = []


@pytest.fixture()
def bot(env, monkeypatch):
    SENT.clear()
    from app import bot as b, tg
    monkeypatch.setattr(tg, "send", lambda chat, text, markup=None: (SENT.append((str(chat), text, markup)) or (True, "")))
    monkeypatch.setattr(tg, "edit", lambda *a, **k: None)
    monkeypatch.setattr(tg, "answer", lambda *a, **k: None)
    DOCS.clear()
    monkeypatch.setattr(tg, "send_document", lambda chat, data, name, caption="": (DOCS.append((str(chat), data, name, caption)) or (True, "")))
    return b


def msg(bot, uid, text, username="u1"):
    bot.handle_update({"message": {"chat": {"id": uid, "type": "private"}, "from": {"id": uid, "username": username, "first_name": "Али"}, "text": text}})


def cb(bot, uid, data):
    bot.handle_update({"callback_query": {"id": "1", "data": data, "from": {"id": uid, "first_name": "Али"}, "message": {"message_id": 1, "chat": {"id": uid, "type": "private"}}}})


def last(uid):
    return [t for c, t, m in SENT if c == str(uid)][-1]


def assign(uid, fid):
    from app import people
    from app.db import tx
    with tx() as c:
        people.add_tg_user(c, str(uid), "Али")
        people.assign(c, {"id": 1, "role": "super_admin", "regions": None}, str(uid), fid)


def test_start_without_access_offers_request(bot):
    msg(bot, 100, "/start")
    assert SENT and "доступ" in last(100).lower()


def test_access_request_for_region_only(bot):
    from app import people
    from app.db import connect, tx
    msg(bot, 100, "/start")
    cb(bot, 100, "rq:r:1")
    kb = [m for c, t, m in SENT if c == "100" and m][-1]
    flat = [x["callback_data"] for row in kb["inline_keyboard"] for x in row]
    assert "rq:g:1" in flat                      # a region alone is enough
    cb(bot, 100, "rq:g:1")
    q = connect().execute("SELECT * FROM access_requests").fetchone()
    assert q["status"] == "pending" and q["region_id"] == 1 and q["facility_id"] is None
    cb(bot, 100, "rq:g:1")                       # the second request is refused politely
    assert "ожидает" in last(100)
    with tx() as cc:
        out = people.decide(cc, {"id": 1, "role": "super_admin", "regions": None}, q["id"], True)
    bot.notify_decision(out["tg_id"], out["facility_id"], True, "", out["region_id"])
    assert connect().execute("SELECT COUNT(*) FROM region_access WHERE tg_id='100' AND active=1").fetchone()[0] == 1
    assert "регион" in last(100).lower()


def test_region_user_reports_for_any_facility_of_region(bot):
    from app import people
    from app.db import connect, tx
    f1 = make_facility(1, "Район А", "A1")
    f2 = make_facility(1, "Район Б", "B1")
    other = make_facility(2, "Район В", "C1")
    with tx() as c:
        people.add_tg_user(c, "200200", "Али")
        people.assign_region(c, {"id": 1, "role": "super_admin", "regions": None}, "200200", 1)
    msg(bot, 200200, "/submit")
    flat = kb_of(200200)
    assert f"sf:{f1}" in flat and f"sf:{f2}" in flat and "sn:1" in flat   # facilities of the region (any district) and "add new"
    assert f"sf:{other}" not in flat
    cb(bot, 200200, f"sf:{f2}")
    cb(bot, 200200, f"sd:{f2}:2026-02-10")
    for a in ["100", "40", "50", "10", "6", "20", "1", "1", "5", "1", "0", "0"]:
        msg(bot, 200200, a)
    cb(bot, 200200, "ok")
    assert connect().execute("SELECT COUNT(*) FROM reports WHERE facility_id=?", (f2,)).fetchone()[0] == 1
    SENT.clear()
    cb(bot, 200200, f"sf:{other}")                       # another region is closed, even with a forged callback
    assert connect().execute("SELECT COUNT(*) FROM reports WHERE facility_id=?", (other,)).fetchone()[0] == 0
    assert "нет прав" in last(200200).lower()
    cb(bot, 200200, "sn:2")
    assert "нет доступа" in last(200200).lower()


def test_region_user_gets_one_reminder_with_unsent_list(env, monkeypatch):
    from datetime import datetime
    from app import notify, people, tg
    from app.db import tx
    sent = []
    monkeypatch.setattr(tg, "send", lambda chat, text, markup=None: (sent.append((str(chat), text)) or (True, "")))
    f1, f2 = make_facility(1, fac="A"), make_facility(1, "Район Б", "B")
    with tx() as c:
        people.add_tg_user(c, "300300", "Али")
        people.assign_region(c, {"id": 1, "role": "super_admin", "regions": None}, "300300", 1)
    put_report(f1, "2026-02-10")
    notify.run_due(datetime(2026, 2, 10, 15, 5))
    assert len(sent) == 1 and "B" in sent[0][1] and "A" not in sent[0][1].replace("Район", "")


def test_unassigned_cannot_submit_for_facility(bot):
    from app import reports
    from app.db import tx
    fid = make_facility()
    msg(bot, 101, "/start")
    with pytest.raises(reports.ReportError):
        with tx() as c:
            reports.submit(c, fid, "2026-02-10", {"visits": 1}, reports.by_tg({"tg_id": "101", "first_name": "x", "last_name": "", "username": ""}))


def test_form_validation_blocks_and_saves(bot):
    from app import bot as b
    from app.db import connect
    fid = make_facility()
    assign(100103, fid)
    cb(bot, 100103, f"sf:{fid}")
    cb(bot, 100103, f"sd:{fid}:2026-02-10")
    answers = ["100", "40", "50", "10", "6", "20", "1", "1", "5", "1", "0", "0"]
    for a in answers:
        msg(bot, 100103, a)
    assert connect().execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 0   # still waiting for confirmation
    cb(bot, 100103, "ok")
    c = connect()
    assert c.execute("SELECT COUNT(*) FROM reports WHERE facility_id=?", (fid,)).fetchone()[0] == 1
    assert c.execute("SELECT value FROM report_values WHERE code='visits'").fetchone()["value"] == 50


def test_form_rejects_text_and_negative(bot):
    fid = make_facility()
    assign(100104, fid)
    cb(bot, 100104, f"sf:{fid}")
    cb(bot, 100104, f"sd:{fid}:2026-02-10")
    msg(bot, 100104, "abc")
    assert "числ" in last(100104).lower() or "цел" in last(100104).lower()
    msg(bot, 100104, "-5")
    assert "числ" in last(100104).lower() or "цел" in last(100104).lower() or "отриц" in last(100104).lower()


def test_reminders_only_to_unsent_and_once(env, monkeypatch):
    from app import notify, tg
    sent = []
    monkeypatch.setattr(tg, "send", lambda chat, text, markup=None: (sent.append(str(chat)) or (True, "")))
    from app import people
    from app.db import tx
    f1, f2 = make_facility(fac="A"), make_facility(fac="B")
    with tx() as c:
        for u, f in (("10001", f1), ("10002", f2)):
            people.add_tg_user(c, u, "x")
            people.assign(c, {"id": 1, "role": "super_admin", "regions": None}, u, f)
    put_report(f1, "2026-02-10")
    at = datetime(2026, 2, 10, 15, 5)
    notify.run_due(at)
    assert sent == ["10002"]
    notify.run_due(at)
    assert sent == ["10002"]                      # once per slot
    notify.run_due(datetime(2026, 2, 10, 17, 35))
    assert sent == ["10002", "10002"]                 # second slot
    sent.clear()
    notify.run_due(datetime(2026, 2, 10, 9, 0))
    assert sent == []                         # before the slots


def test_no_reminder_on_disabled_weekday(env, monkeypatch):
    from app import notify, people, tg
    from app.db import tx
    sent = []
    monkeypatch.setattr(tg, "send", lambda chat, text, markup=None: (sent.append(1) or (True, "")))
    f = make_facility()
    with tx() as c:
        people.add_tg_user(c, "90009", "x"); people.assign(c, {"id": 1, "role": "super_admin", "regions": None}, "90009", f)
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES ('remind_weekdays','1,2,3,4,5')")
    notify.run_due(datetime(2026, 2, 8, 15, 5))   # Sunday
    assert sent == []


def kb_of(uid):
    m = [m for c, t, m in SENT if c == str(uid) and m][-1]
    return [x["callback_data"] for row in (m.get("inline_keyboard") or []) for x in row]


def region_user(uid, region=1):
    from app import people
    from app.db import tx
    with tx() as c:
        people.add_tg_user(c, str(uid), "Али")
        people.assign_region(c, {"id": 1, "role": "super_admin", "regions": None}, str(uid), region)


def test_empty_region_offers_to_add_first_facility(bot):
    from app.db import connect
    region_user(700700)
    msg(bot, 700700, "/submit")
    assert "пока нет учреждений" in last(700700).lower() and "sn:1" in kb_of(700700)
    cb(bot, 700700, "sn:1")
    msg(bot, 700700, "аб")                                # too short
    assert "слишком" in last(700700).lower()
    msg(bot, 700700, "  Городская   больница №3 ")
    c = connect()
    f = c.execute("SELECT f.id, f.name_ru, d.name_ru AS d FROM facilities f JOIN districts d ON d.id=f.district_id").fetchall()
    assert len(f) == 1 and f[0]["name_ru"] == "Городская больница №3" and f[0]["d"] == "Без района"
    assert any(f"sd:{f[0]['id']}:2026-02-10" == x for x in kb_of(700700))   # straight on to the date
    assert c.execute("SELECT COUNT(*) FROM audit WHERE action='facility.create'").fetchone()[0] == 1
    # the same name again does not duplicate
    cb(bot, 700700, "sn:1"); msg(bot, 700700, "городская больница №3")
    assert connect().execute("SELECT COUNT(*) FROM facilities").fetchone()[0] == 1


def test_add_facility_daily_limit_and_other_region(bot):
    from app.db import connect
    region_user(700710)
    for i in range(10):
        cb(bot, 700710, "sn:1"); msg(bot, 700710, f"Больница номер {i}")
    cb(bot, 700710, "sn:1"); msg(bot, 700710, "Одиннадцатая больница")
    assert "не больше" in last(700710) and connect().execute("SELECT COUNT(*) FROM facilities").fetchone()[0] == 10


def test_facility_by_typed_name_in_region(bot):
    f = make_facility(1, "Мирзо Улугбекский район", "Поликлиника №5")
    make_facility(1, "Чиланзарский район", "Поликлиника №1")
    region_user(700701)
    msg(bot, 700701, "/submit")
    msg(bot, 700701, "несуществующая")
    assert "не нашёл" in last(700701).lower()
    msg(bot, 700701, "поликлиника №5")
    assert f"sd:{f}:2026-02-10" in kb_of(700701)


def test_date_step_is_one_button_plus_typed_date(bot):
    f = make_facility()
    assign(700702, f)
    cb(bot, 700702, f"sf:{f}")
    flat = kb_of(700702)
    assert flat == [f"sd:{f}:2026-02-10"]               # only "today"; no list of past days
    msg(bot, 700702, "abc")
    assert "не понял" in last(700702).lower()
    msg(bot, 700702, "15.02.2026")
    assert "будущ" in last(700702).lower()
    msg(bot, 700702, "01.02.2026")
    assert "нельзя" in last(700702).lower()            # outside the backfill window
    msg(bot, 700702, "09.02")
    assert "Вопрос 1 из" in last(700702) and "2026-02-09" in last(700702) and "▰▱" in last(700702)


def test_typed_word_yesterday(bot):
    f = make_facility()
    assign(700705, f)
    cb(bot, 700705, f"sf:{f}")
    msg(bot, 700705, "вчера")
    assert "2026-02-09" in last(700705)


ANS = ["100", "40", "50", "10", "6", "20", "1", "1", "5", "1", "0", "0"]


def send_report(uid, f, d, answers):
    cb(bot_mod(), uid, f"sd:{f}:{d}")
    for a in answers:
        msg(bot_mod(), uid, a)


def bot_mod():
    from app import bot as b
    return b


def test_repeat_submission_is_compared_and_needs_confirmation(bot):
    from app.db import connect
    f = make_facility()
    assign(700703, f)
    send_report(700703, f, "2026-02-10", ANS)
    cb(bot, 700703, "ok")
    assert connect().execute("SELECT version FROM reports WHERE facility_id=?", (f,)).fetchone()["version"] == 1
    # second time: the visits changed from 50 to 70, everything else is kept with the button
    SENT.clear()
    cb(bot, 700703, f"sd:{f}:2026-02-10")
    assert "уже отправлена" in " ".join(t for c, t, m in SENT)
    for i, a in enumerate(ANS):
        msg(bot, 700703, "70" if i == 2 else f"↩️ Оставить: {a}")
    prev = last(700703)
    assert "50 → <b>70</b>" in prev and prev.count("→ <b>") == 1
    assert "ok" in kb_of(700703)
    assert connect().execute("SELECT version FROM reports WHERE facility_id=?", (f,)).fetchone()["version"] == 1   # nothing accepted before the confirmation
    cb(bot, 700703, "ok")
    r = connect().execute("SELECT id, version FROM reports WHERE facility_id=?", (f,)).fetchone()
    assert r["version"] == 2
    assert connect().execute("SELECT value FROM report_values WHERE report_id=? AND code='visits'", (r["id"],)).fetchone()["value"] == 70


def test_repeat_with_same_numbers_offers_no_confirm(bot):
    from app.db import connect
    f = make_facility()
    assign(700704, f)
    send_report(700704, f, "2026-02-10", ANS)
    cb(bot, 700704, "ok")
    cb(bot, 700704, f"sd:{f}:2026-02-10")
    for a in ANS:
        msg(bot, 700704, f"↩️ Оставить: {a}")
    assert "совпадают" in last(700704)
    assert "ok" not in kb_of(700704)
    assert connect().execute("SELECT version FROM reports WHERE facility_id=?", (f,)).fetchone()["version"] == 1


def test_download_region_summary_for_a_date(bot):
    import io
    import openpyxl
    f1, f2 = make_facility(1, "Район А", "A1"), make_facility(1, "Район Б", "B1")
    other = make_facility(2, "Район В", "C1")
    put_report(f1, "2026-02-09", visits=11); put_report(f2, "2026-02-09", visits=22); put_report(other, "2026-02-09", visits=999)
    region_user(800800)
    msg(bot, 800800, "📥 Скачать сводку")
    assert f"dd:r1:2026-02-10" in kb_of(800800)             # one region: straight to the date, with a Today button
    msg(bot, 800800, "09.02")
    assert "dx:r1:2026-02-09:xlsx" in kb_of(800800) and "dx:r1:2026-02-09:pdf" in kb_of(800800)
    cb(bot, 800800, "dx:r1:2026-02-09:xlsx")
    chat, data, name, cap = DOCS[-1]
    assert chat == "800800" and name == "flu_2026-02-09.xlsx" and "Отправлено учреждений: 2" in cap
    wb = openpyxl.load_workbook(io.BytesIO(data))
    text = " ".join(str(c.value) for ws in wb for row in ws.iter_rows() for c in row if c.value is not None)
    assert "A1" in text and "B1" in text and "C1" not in text and "999" not in text       # only their own region
    cb(bot, 800800, "dx:r1:2026-02-09:pdf")
    assert DOCS[-1][1][:4] == b"%PDF"


def test_download_refuses_foreign_region_and_empty_date(bot):
    f = make_facility(1, fac="A")
    other = make_facility(2, "Район В", "C1")
    put_report(other, "2026-02-09")
    region_user(800801)
    DOCS.clear()
    cb(bot, 800801, "dx:r2:2026-02-09:xlsx")              # a forged button for a region without access
    assert DOCS == [] and "нет доступа" in last(800801).lower()
    cb(bot, 800801, "dx:f%d:2026-02-09:xlsx" % other)
    assert DOCS == []
    cb(bot, 800801, "dx:r1:2026-02-09:xlsx")              # allowed, but nobody of the region reported that day
    assert DOCS == [] and "нечего скачивать" in last(800801)
    cb(bot, 800801, "dx:r1:2030-01-01:xlsx")
    assert DOCS == [] and "будущ" in last(800801).lower()


def test_download_for_person_with_facility_only(bot):
    f = make_facility(1, fac="Моя")
    other = make_facility(1, "Район Б", "Чужая")
    put_report(f, "2026-02-10"); put_report(other, "2026-02-10")
    assign(800802, f)
    msg(bot, 800802, "📥 Скачать сводку")
    cb(bot, 800802, f"dd:f{f}:2026-02-10")
    cb(bot, 800802, f"dx:f{f}:2026-02-10:xlsx")
    import io, openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(DOCS[-1][1]))
    text = " ".join(str(c.value) for ws in wb for row in ws.iter_rows() for c in row if c.value is not None)
    assert "Моя" in text and "Чужая" not in text


def test_questionnaire_in_uzbek_latin_with_clear_questions_and_limits(bot):
    from app.db import connect, tx
    f = make_facility()
    assign(700790, f)
    with tx() as c:
        c.execute("UPDATE tg_users SET lang='uz' WHERE tg_id=700790")
    cb(bot, 700790, f"sd:{f}:2026-02-10")
    q1 = last(700790)
    assert "1-savol / 12" in q1 and "Jami o‘rinlar soni" in q1 and "O‘rinlar fondi" in q1 and "raqamlar bilan" in q1
    assert not any("а" <= ch.lower() <= "я" for ch in q1.replace("Больница", ""))                # no Cyrillic in the questions of the Uzbek bot
    msg(bot, 700790, "40")
    q2 = last(700790)
    assert "2-savol / 12" in q2 and "Shundan gripp bilan kasallangan bemorlar uchun ajratilgan o‘rinlar soni" in q2 and "1-savoldagi sondan oshmasligi kerak: <b>40</b>" in q2
    SENT.clear()
    msg(bot, 700790, "50")                                                                           # more than the answer to question 1
    both = " ".join(t for c, t, m in SENT)
    assert "<b>40</b> dan oshmasligi kerak" in both and "2-savol / 12" in last(700790)                      # told at once, and the same question again
    msg(bot, 700790, "30"); msg(bot, 700790, "5")                                                    # 2: 30, 3: 5 visits
    assert "3-savol" in " ".join(t for c, t, m in SENT[-3:]) and "Murojaatlar va yotqizish" in " ".join(t for c, t, m in SENT[-4:])
    for a in ["2", "1", "9", "1", "1", "4", "1", "0", "0"]:                                           # questions 4..12 (occupied 9 <= 30; 7 and 8 <= 9; severe 4 <= visits 5)
        msg(bot, 700790, a)
    prev = last(700790)
    assert "6. Hisobot kuni yakunida gripp bilan kasallangan bemorlar band qilgan o‘rinlar soni: <b>9</b>" in prev and "12. " in prev
