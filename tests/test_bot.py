from datetime import datetime

import pytest
from conftest import make_facility, put_report

SENT = []
DOCS = []
NOTE_SKIP = "⏭ Без сообщения, продолжить"        # the last question of the bot: an optional message for the Ministry


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
    msg(bot, 200200, NOTE_SKIP)
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
    msg(bot, 100103, NOTE_SKIP)
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


def test_empty_region_offers_to_propose_a_facility_and_adds_nothing(bot):
    from app.db import connect
    region_user(700700)
    msg(bot, 700700, "/submit")
    assert "пока нет учреждений" in last(700700).lower() and "sn:1" in kb_of(700700)
    cb(bot, 700700, "sn:1")                                                          # the button now asks what to propose: add or remove
    assert {"sa:1:add", "sa:1:del"} <= set(kb_of(700700))
    cb(bot, 700700, "sa:1:add")
    msg(bot, 700700, "аб")                                # too short
    assert "слишком" in last(700700).lower()
    msg(bot, 700700, "  Городская   больница №3 ")
    c = connect()
    assert c.execute("SELECT COUNT(*) FROM facilities").fetchone()[0] == 0           # the bot creates nothing any more
    p = c.execute("SELECT * FROM facility_proposals").fetchall()
    assert len(p) == 1 and p[0]["kind"] == "add" and p[0]["name"] == "Городская больница №3" and p[0]["region_id"] == 1 and p[0]["status"] == "new" and p[0]["tg_id"] == "700700"
    assert "отправлено администратору" in last(700700)
    # the same proposal again is not repeated
    cb(bot, 700700, "sn:1"); cb(bot, 700700, "sa:1:add"); msg(bot, 700700, "городская больница №3")
    assert "уже отправлено" in last(700700) and connect().execute("SELECT COUNT(*) FROM facility_proposals").fetchone()[0] == 1


def test_propose_to_remove_a_facility_with_a_reason(bot):
    from app.db import connect
    f = make_facility(1, "Район А", "Больница №7")
    region_user(700703)
    cb(bot, 700703, "sa:1:del")
    assert f"pz:{f}" in kb_of(700703)
    cb(bot, 700703, f"pz:{f}")
    msg(bot, 700703, "Закрыта, объединена с другой")
    p = connect().execute("SELECT * FROM facility_proposals").fetchall()
    assert len(p) == 1 and p[0]["kind"] == "remove" and p[0]["facility_id"] == f and p[0]["name"] == "Больница №7" and "объединена" in p[0]["comment"]
    assert connect().execute("SELECT active FROM facilities WHERE id=?", (f,)).fetchone()[0] == 1       # nothing is removed by the bot
    SENT.clear(); cb(bot, 700703, f"pz:{f}"); msg(bot, 700703, "⏭ Пропустить")                         # the same facility again: already waiting
    assert "уже отправлено" in last(700703)
    other = make_facility(2, "Район В", "Чужая")
    SENT.clear(); cb(bot, 700703, f"pz:{other}")                                                        # a facility of another region is refused, even with a forged callback
    assert "нет прав" in last(700703).lower() and connect().execute("SELECT COUNT(*) FROM facility_proposals").fetchone()[0] == 1


def test_proposals_daily_limit_and_other_region(bot):
    from app.db import connect
    region_user(700710)
    for i in range(10):
        cb(bot, 700710, "sa:1:add"); msg(bot, 700710, f"Больница номер {i}")
    cb(bot, 700710, "sa:1:add"); msg(bot, 700710, "Одиннадцатая больница")
    assert "не больше" in last(700710) and connect().execute("SELECT COUNT(*) FROM facility_proposals").fetchone()[0] == 10
    cb(bot, 700710, "sa:2:add")
    assert "нет доступа" in last(700710).lower()


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
    msg(bot_mod(), uid, NOTE_SKIP)


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
    msg(bot, 700703, NOTE_SKIP)
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
    msg(bot, 700704, NOTE_SKIP)
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
    assert "1-savol / 13" in q1 and "Jami o‘rinlar soni" in q1
    assert "Muassasadagi" not in q1 and "raqamlar bilan" not in q1 and "O‘rinlar fondi" not in q1          # only the question: no explanations, no section titles
    assert "Son" in SENT[-1][2]["input_field_placeholder"]                                               # «write a number» is the placeholder of the input field
    assert not any("а" <= ch.lower() <= "я" for ch in q1.replace("Больница", ""))                # no Cyrillic in the questions of the Uzbek bot
    msg(bot, 700790, "40")
    q2 = last(700790)
    assert "2-savol / 13" in q2 and "Shundan gripp va ORVI bilan kasallangan bemorlar uchun ajratilgan o‘rinlar soni" in q2 and "Ko‘pi bilan <b>40</b> (1-savol)" in q2
    SENT.clear()
    msg(bot, 700790, "50")                                                                           # more than the answer to question 1
    both = " ".join(t for c, t, m in SENT)
    assert "<b>40</b> dan oshmasligi kerak" in both and "2-savol / 13" in last(700790)                      # told at once, and the same question again
    msg(bot, 700790, "30"); msg(bot, 700790, "5")                                                    # 2: 30, 3: 5 visits
    assert "4-savol / 13" in last(700790)
    for a in ["2", "1", "9", "1", "1", "4", "1", "0", "0"]:                                           # questions 4..12 (occupied 9 <= 30; 7 and 8 <= 9; severe 4 <= visits 5)
        msg(bot, 700790, a)
    assert "13-savol / 13" in last(700790) and "Sog‘liqni saqlash vazirligiga xabar" in last(700790) and "maxfiy" in last(700790)
    msg(bot, 700790, "⏭ Xabarsiz davom etish")
    prev = last(700790)
    assert "6. Hisobot kuni yakunida gripp va ORVI bilan kasallangan bemorlar band qilgan o‘rinlar soni: <b>9</b>" in prev and "12. " in prev


def test_new_users_get_uzbek_by_default_and_the_menu_buttons_work_in_latin(bot):
    from app.db import connect, tx
    with tx() as c:
        c.execute("UPDATE settings SET value='uz' WHERE key='default_lang'")
    SENT.clear()
    msg(bot, 990001, "/start")
    assert connect().execute("SELECT lang FROM tg_users WHERE tg_id=990001").fetchone()["lang"] == "uz"
    from app import people
    with tx() as c:
        people.assign_region(c, {"id": 1, "role": "super_admin", "regions": None}, "990001", 1)     # with access the whole menu is drawn
    SENT.clear()
    msg(bot, 990001, "/start")
    ask = [x for row in SENT[-1][2]["keyboard"] for x in row]
    assert ask[0].get("request_contact") is True and "Keyinroq" in ask[1]["text"]                      # the first start asks for the phone, with a way to do it later
    msg(bot, 990001, "⏭ Keyinroq")
    rows = [x for row in SENT[-1][2]["keyboard"] for x in row]
    assert rows[0].get("request_contact") is True                                                      # until he has sent his phone, the first button asks for it (Telegram sends his own contact)
    buttons = [x["text"] for x in rows if not x.get("request_contact")]
    assert len(buttons) == 5 and all(not any("а" <= ch.lower() <= "я" for ch in x) for x in buttons if "Язык" not in x), buttons      # the menu is in Latin
    assert "🌐 Til / Язык" in buttons                                                                     # except the language button: it can always be found
    for x in buttons:                                                                                  # every drawn button is recognised (this was broken: «Quyidagi menyudan tanlang»)
        assert bot.MENU_TEXT.get(x), x


def test_menu_has_no_help_and_my_facilities_buttons(bot):
    from app import people
    from app.db import tx
    for lang in ("uz", "ru"):
        for has in (True, False):
            texts = [x["text"] for row in bot.main_kb(lang, has)["keyboard"] for x in row]
            assert not any(k in x for x in texts for k in ("Yordam", "Помощь", "Mening muassasalarim", "Мои учреждения", "hisobotlar tarixi", "История")), texts
            assert len(texts) >= 3
    assert bot.MENU_TEXT.get("❓ Yordam") == "help"            # an old keyboard that is still on someone's phone keeps working


def test_status_lists_facilities_who_have_not_sent_and_fits_telegram(bot):
    from app import people
    from app.db import tx
    fs = [make_facility(1, "Район А", f"Больница {i:03d}") for i in range(120)]
    with tx() as c:
        people.add_tg_user(c, "991001", "Ответственный")
        people.assign_region(c, {"id": 1, "role": "super_admin", "regions": None}, "991001", 1)
    for f in fs[:100]:                                                                             # 100 of 120 have sent for today, 20 have not
        put_report(f, "2026-02-10")
    SENT.clear()
    msg(bot, 991001, "/status")
    texts = [t for c, t, m in SENT if c == "991001"]
    assert all(len(x) <= 4096 for x in texts), [len(x) for x in texts]                              # Telegram's limit
    allt = "\n".join(texts)
    assert "Не сдали (20)" in allt and "100/120" in allt and "▰" in allt                            # who has not sent, the count and a progress bar
    for i in range(100, 120):
        assert f"Больница {i:03d}" in allt                                                          # every facility that has not sent is named
    assert "1. Больница 100" in allt and "<blockquote expandable>" in allt                          # numbered; those who have sent are folded
    assert SENT[-1][2] is not None and "keyboard" in SENT[-1][2]                                    # the menu comes back with the last message


def test_status_is_in_uzbek_for_an_uzbek_user(bot):
    from app import people
    from app.db import tx
    f = make_facility(1, "Район А", "Касса")
    with tx() as c:
        people.add_tg_user(c, "991002", "Ли")
        people.assign_region(c, {"id": 1, "role": "super_admin", "regions": None}, "991002", 1)
        c.execute("UPDATE tg_users SET lang='uz' WHERE tg_id='991002'")
    SENT.clear()
    msg(bot, 991002, "/status")
    allt = "\n".join(t for c, t, m in SENT if c == "991002")
    assert "Hisobot holati" in allt and "Topshirmaganlar (1)" in allt and "1. Касса" in allt and "bugun" in allt


def contact(bot, uid, phone, user_id=None, first="Али"):
    bot.handle_update({"message": {"chat": {"id": uid, "type": "private"}, "from": {"id": uid, "first_name": first}, "contact": {"phone_number": phone, "first_name": first, "user_id": uid if user_id is None else user_id}}})


def seed_contacts():
    from app import editor
    from app.db import tx
    f1, f2, f3 = make_facility(1, "Район А", "Больница Ф1"), make_facility(1, "Район Б", "Больница Ф2"), make_facility(2, "Район В", "Чужая Ф3")
    with tx() as c:
        editor.replace_contacts(c, f1, [{"kind": "main", "fio": "Иванов Иван", "phone": "90-123-45-67"}, {"kind": "reserve", "fio": "Резерв", "phone": "91-000-00-01"}])
        editor.replace_contacts(c, f2, [{"kind": "main", "fio": "Иванов Иван", "phone": "+998 90 123 45 67\n93-111-22-33"}])    # the same person leads two facilities
        editor.replace_contacts(c, f3, [{"kind": "main", "fio": "Петров", "phone": "97-777-77-77"}])
    return f1, f2, f3


def test_the_phone_of_the_responsible_person_links_his_telegram_account(bot):
    from app.db import connect
    f1, f2, f3 = seed_contacts()
    msg(bot, 810001, "/start")
    assert any(x.get("request_contact") for row in SENT[-1][2]["keyboard"] for x in row)               # the button that sends his own number is offered
    SENT.clear()
    contact(bot, 810001, "+998901234567")                                                              # Telegram gives it with a plus
    c = connect()
    rows = {r["facility_id"]: r["kind"] for r in c.execute("SELECT facility_id, kind FROM assignments WHERE tg_id='810001' AND active=1")}
    assert rows == {f1: "primary", f2: "primary"} and "подключены" in last(810001) and "Больница Ф1" in last(810001)
    assert c.execute("SELECT phone FROM tg_users WHERE tg_id='810001'").fetchone()[0] == "998901234567"
    assert not any(x.get("request_contact") for row in SENT[-1][2]["keyboard"] for x in row)           # the phone is known: the button is gone
    assert c.execute("SELECT COUNT(*) FROM audit WHERE action='phone.linked'").fetchone()[0] == 2
    SENT.clear(); contact(bot, 810001, "+998901234567")                                                # again: nothing new
    assert connect().execute("SELECT COUNT(*) FROM assignments WHERE tg_id='810001'").fetchone()[0] == 2 and "новых подключений нет" in last(810001)


def test_a_contact_of_somebody_else_proves_nothing_and_an_unknown_phone_links_nothing(bot):
    from app.db import connect
    seed_contacts()
    msg(bot, 810002, "/start")
    SENT.clear(); contact(bot, 810002, "+998901234567", user_id=555)                                   # a forwarded contact of another person
    assert "собственный номер" in last(810002) and connect().execute("SELECT COUNT(*) FROM assignments WHERE tg_id='810002'").fetchone()[0] == 0
    assert connect().execute("SELECT phone FROM tg_users WHERE tg_id='810002'").fetchone()[0] == ""
    SENT.clear(); contact(bot, 810002, "+998909999999")                                                # his own, but not in any list
    assert "в списках ответственных его нет" in last(810002) and connect().execute("SELECT COUNT(*) FROM assignments WHERE tg_id='810002'").fetchone()[0] == 0


def test_a_phone_written_later_by_the_administrator_links_the_person_who_is_already_in_the_bot(bot):
    from app import editor
    from app.db import connect, tx
    f1 = make_facility(1, "Район А", "Больница Л1")
    msg(bot, 810003, "/start"); contact(bot, 810003, "998935551234")                                  # he sent his number first, nothing is linked yet
    assert connect().execute("SELECT COUNT(*) FROM assignments WHERE tg_id='810003'").fetchone()[0] == 0
    with tx() as c:                                                                                    # the list is loaded afterwards (the editor or the table)
        editor.replace_contacts(c, f1, [{"kind": "main", "fio": "Сидоров", "phone": "93-555-12-34"}])
    assert [(r["facility_id"], r["kind"]) for r in connect().execute("SELECT facility_id, kind FROM assignments WHERE tg_id='810003' AND active=1")] == [(f1, "primary")]


def test_an_existing_primary_person_is_not_pushed_out_by_the_phone(bot):
    from app import editor, people
    from app.db import connect, tx
    f = make_facility(1, "Район А", "Больница Л2")
    with tx() as c:
        people.add_tg_user(c, "810004", "Старый")
        people.assign(c, {"id": 1, "role": "super_admin", "regions": None}, "810004", f)               # the administrator has already named a primary person
    msg(bot, 810005, "/start"); contact(bot, 810005, "998945550000")
    with tx() as c:
        editor.replace_contacts(c, f, [{"kind": "main", "fio": "Новый", "phone": "94-555-00-00"}])
    kinds = {r["tg_id"]: r["kind"] for r in connect().execute("SELECT tg_id, kind FROM assignments WHERE facility_id=? AND active=1", (f,))}
    assert kinds == {"810004": "primary", "810005": "reserve"}                                         # the new one reports as a reserve, the old one stays


def test_buttons_edit_their_own_message_instead_of_filling_the_chat(monkeypatch):
    from app import tg
    calls = []
    monkeypatch.setattr(tg, "api", lambda method, payload=None, timeout=15: calls.append((method, payload)) or {})
    inline = {"inline_keyboard": [[{"text": "x", "callback_data": "y"}]]}
    token = tg.set_edit_target(42, 7)
    try:
        assert tg.send(42, "step 2", inline) == (True, "")                                              # the first answer is the old message, edited
        assert calls[-1][0] == "editMessageText" and calls[-1][1]["message_id"] == 7 and calls[-1][1]["reply_markup"] == inline
        tg.send(42, "another one", inline)                                                              # a second message of the same handler is a new one
        assert calls[-1][0] == "sendMessage"
    finally:
        tg.reset_edit_target(token)
    calls.clear()
    token = tg.set_edit_target(42, 8)
    try:
        tg.send(42, "menu", {"keyboard": [[{"text": "a"}]]})                                            # a reply keyboard cannot be set by an edit: the old buttons go, a new message comes
        assert [c[0] for c in calls] == ["editMessageReplyMarkup", "sendMessage"] and calls[0][1]["reply_markup"] == {"inline_keyboard": []}
    finally:
        tg.reset_edit_target(token)
    calls.clear(); tg.send(42, "no button pressed", inline)                                             # outside of a button press nothing is edited
    assert [c[0] for c in calls] == ["sendMessage"]


def test_if_the_edit_fails_the_answer_is_sent_as_a_new_message(monkeypatch):
    from app import tg
    seen = []
    def api(method, payload=None, timeout=15):
        seen.append(method)
        if method == "editMessageText":
            raise tg.TgError(400, "Bad Request: message to edit not found")
        return {}
    monkeypatch.setattr(tg, "api", api)
    token = tg.set_edit_target(1, 2)
    try:
        assert tg.send(1, "text") == (True, "") and seen == ["editMessageText", "sendMessage"]
    finally:
        tg.reset_edit_target(token)


def test_the_head_of_a_region_gets_the_access_to_the_whole_region_by_his_phone(bot):
    from app.db import connect
    make_facility(1, "Район А", "Больница Р1")
    msg(bot, 830001, "/start")
    SENT.clear(); contact(bot, 830001, "+998977897077")                                                # the head of the Karakalpakstan department (the list that is built in)
    c = connect()
    assert [(r["region_id"], r["kind"]) for r in c.execute("SELECT region_id, kind FROM region_access WHERE tg_id='830001' AND active=1")] == [(1, "primary")]
    assert "подключены" in last(830001) and c.execute("SELECT COUNT(*) FROM audit WHERE action='phone.linked'").fetchone()[0] == 1
    assert bot.reports.has_access(c, "830001")


def test_status_is_for_today_only_and_names_the_responsible_person_with_the_phone(bot):
    from app import editor, people
    from app.db import tx
    f1, f2, f3 = (make_facility(1, "Район А", n) for n in ("Больница Т1", "Больница Т2", "Больница Т3"))
    with tx() as c:
        people.add_tg_user(c, "991003", "Руководитель")
        people.assign_region(c, {"id": 1, "role": "super_admin", "regions": None}, "991003", 1)
        editor.replace_contacts(c, f1, [{"kind": "main", "fio": "Иванов Иван", "phone": "90-123-45-67"}])
        editor.replace_contacts(c, f2, [{"kind": "main", "fio": "Петров Пётр", "phone": "91-000-00-02\n93-000-00-03"}])
    put_report(f3, "2026-02-10")                          # sent today
    put_report(f1, "2026-02-09")                          # yesterday only: for today it still counts as not sent
    SENT.clear()
    msg(bot, 991003, "/status")
    allt = "\n".join(t for c, t, m in SENT if c == "991003")
    assert "Не сдали (2)" in allt and "1/3" in allt                                                # one of three has sent today
    assert "Иванов Иван" in allt and "+998 90 123 45 67" in allt                                  # who to call, and the number
    assert "Петров Пётр" in allt and "+998 91 000 00 02, +998 93 000 00 03" in allt
    assert "09.02" not in allt and "вчера" not in allt                                            # nothing about yesterday
    assert allt.count("📅") == 1                                                                  # one day only


def test_the_first_start_asks_the_phone_and_the_answer_is_compared_with_the_lists(bot):
    from app import editor
    from app.db import connect, tx
    f = make_facility(1, "Район А", "Больница С1")
    with tx() as c:
        editor.replace_contacts(c, f, [{"kind": "main", "fio": "Сидоров", "phone": "93-555-12-34"}])
    SENT.clear()
    msg(bot, 840001, "/start")
    text, markup = SENT[-1][1], SENT[-1][2]
    assert "номер телефона" in text and markup["keyboard"][0][0].get("request_contact") is True and markup.get("one_time_keyboard") is True
    SENT.clear(); contact(bot, 840001, "+998935551234")
    assert "подключены" in last(840001) and [r["facility_id"] for r in connect().execute("SELECT facility_id FROM assignments WHERE tg_id='840001' AND active=1")] == [f]
    SENT.clear(); msg(bot, 840001, "/start")                                                      # the phone is known: no second question, the menu
    assert not any(x.get("request_contact") for row in SENT[-1][2]["keyboard"] for x in row) and "номер телефона" not in SENT[-1][1]
    msg(bot, 840002, "/start"); SENT.clear(); msg(bot, 840002, "⏭ Позже")                          # «later»: the menu, with the button of the phone kept
    assert SENT[-1][2]["keyboard"][0][0].get("request_contact") is True


def test_broadcast_can_go_to_the_heads_of_regions_or_to_the_responsible_for_facilities_only(client):
    from app import broadcast, people
    from app.db import connect, tx
    f1, f2 = make_facility(1, "Район А", "Больница Б1"), make_facility(2, "Район В", "Больница Б2")
    with tx() as c:
        for tid in ("850001", "850002", "850003"):
            people.add_tg_user(c, tid, "Человек" + tid)
        su = {"id": 1, "role": "super_admin", "regions": None}
        people.assign_region(c, su, "850001", 1)                          # the head of region 1
        c.execute("UPDATE tg_users SET phone='998977897077' WHERE tg_id='850001'")                   # confirmed by the phone of the head in the list
        people.assign(c, su, "850002", f1)                                # responsible for a facility of region 1
        people.assign(c, su, "850003", f2)                                # responsible for a facility of region 2
    c = connect()
    me = {"id": 1, "role": "super_admin", "regions": None}
    ids = lambda spec: sorted(p["tg_id"] for p in broadcast.recipients(c, me, spec))
    assert ids({"mode": "all"}) == ["850001", "850002", "850003"]
    assert ids({"mode": "heads"}) == ["850001"] and ids({"mode": "responsibles"}) == ["850002", "850003"]
    assert ids({"mode": "responsibles", "regions": [2]}) == ["850003"] and ids({"mode": "heads", "regions": [2]}) == []     # narrowed to a region
    assert ids({"mode": "regions", "regions": [1]}) == ["850001", "850002"]
    regional = {"id": 9, "role": "admin", "regions": [1]}                  # an administrator of region 1 never reaches region 2
    assert [p["tg_id"] for p in broadcast.recipients(c, regional, {"mode": "responsibles"})] == ["850002"]
    with __import__("pytest").raises(broadcast.BroadcastError):
        broadcast.recipients(c, regional, {"mode": "responsibles", "regions": [2]})


def edited_questionnaire():
    """As an administrator would edit it on the site: four questions switched off, an optional one added."""
    from app.db import tx
    with tx() as c:
        for code in ("occ_pregnant", "occ_children", "extreme_pregnant", "extreme_children"):
            c.execute("UPDATE indicators SET active=0 WHERE code=?", (code,))
        c.execute("INSERT INTO indicators(code, grp, name_ru, name_uz, hint_ru, hint_uz, agg, sort, required) VALUES ('q_opt','extra','Необязательный вопрос','Ixtiyoriy savol','Если знаете','Bilsangiz','sum',99,0)")


def test_the_bot_asks_the_questionnaire_that_was_edited_on_the_site(bot):
    from app.db import connect
    edited_questionnaire()
    f = make_facility(1, "Район А", "Больница В1"); assign(820001, f)
    cb(bot, 820001, f"sf:{f}"); cb(bot, 820001, f"sd:{f}:2026-02-10")
    asked = []
    for a in ["100", "40", "50", "10", "6", "20", "5", "1"]:                                           # the eight core questions that are left, in their order
        asked.append(last(820001)); msg(bot, 820001, a)
    assert "Вопрос 1 из 10" in asked[0] and "Вопрос 8 из 10" in asked[7] and "Необязательный вопрос" in last(820001) and "Вопрос 9 из 10" in last(820001)      # 9 questions and the message to the Ministry
    kb = [x["text"] for row in [m for c_, t_, m in SENT if c_ == "820001" and m][-1]["keyboard"] for x in row]
    assert "⏭ Пропустить вопрос" in kb                                                                  # an optional question has a skip button
    msg(bot, 820001, "⏭ Пропустить вопрос")
    assert "сообщение" in last(820001).lower() and "Министерств" in last(820001)                       # then the last question
    msg(bot, 820001, NOTE_SKIP)
    cb(bot, 820001, "ok")
    c = connect()
    vals = {r["code"]: r["value"] for r in c.execute("SELECT code, value FROM report_values")}
    assert vals["beds_total"] == 100 and vals["extreme"] == 1 and "q_opt" not in vals and "occ_pregnant" not in vals


def test_the_limit_at_a_question_comes_from_the_rules_and_the_last_question_can_be_switched_off(bot):
    from app.db import connect, tx
    f = make_facility(1, "Район А", "Больница В2"); assign(820002, f)
    cb(bot, 820002, f"sf:{f}"); cb(bot, 820002, f"sd:{f}:2026-02-10")
    msg(bot, 820002, "100")
    assert "Не больше" in last(820002) and "(вопрос 1)" in last(820002)                                # beds_flu <= beds_total is a rule of the system
    msg(bot, 820002, "150")
    assert any("не может быть больше" in t_ for c_, t_, m in SENT[-2:] if c_ == "820002")                # refused at once, and the same question again
    with tx() as c:                                                                                    # the administrator removes the rule on the site: the limit is gone
        c.execute("DELETE FROM rules WHERE expr='beds_flu <= beds_total'")
        c.execute("INSERT INTO rules(kind, expr, message_ru, message_uz, sort) VALUES ('error','visits <= beds_flu','m','m',99)")      # and writes a new one
    msg(bot, 820002, "150")
    assert "Не больше" in last(820002) and "(вопрос 2)" in last(820002)                                # now the visits are limited by the second answer
    with tx() as c:
        c.execute("UPDATE settings SET value='0' WHERE key='note_enabled'")
        c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('q_hints','1')")
    msg(bot, 820002, "10")
    assert "Все койки" not in last(820002)
    for a in ["10", "6", "20", "1", "1", "5", "1", "0", "0"]:
        msg(bot, 820002, a)
    assert "Проверьте" in last(820002) or "Отчёт" in last(820002)
    assert "Министерств" not in last(820002)                                                           # no question and no line about the message to the Ministry


def test_hints_are_shown_under_the_question_when_they_are_on(bot):
    from app.db import tx
    f = make_facility(1, "Район А", "Больница В3"); assign(820003, f)
    with tx() as c:
        c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('q_hints','1')")
    cb(bot, 820003, f"sf:{f}"); cb(bot, 820003, f"sd:{f}:2026-02-10")
    assert "Все койки учреждения" in last(820003)
