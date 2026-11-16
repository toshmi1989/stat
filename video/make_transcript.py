"""Plays a real conversation with the bot (code of app/bot.py) and writes transcript.json for the video. Run from the repo root:
   python3 video/make_transcript.py"""
import json
import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.update(DATA_DIR=tempfile.mkdtemp(), APP_PASSWORD="x", FLU_TODAY="2026-11-16", FLU_NOW="16:40", FLU_NO_TELEGRAM="1", FLU_NO_BACKUP="1")
from app import bot, db, notify, people, tg  # noqa: E402

db.init_db()
EV = []
last_inline = {}


def rows_of(markup, key):
    return [[(b["text"], b.get("callback_data", "")) if key == "inline_keyboard" else b["text"] for b in row] for row in (markup or {}).get(key, [])]


def send(chat, text, markup=None):
    inline = rows_of(markup, "inline_keyboard") or None
    reply = rows_of(markup, "keyboard") or None
    EV.append({"t": "bot", "html": text, "inline": inline, "reply": reply})
    if inline:
        last_inline["rows"] = inline
    return True, ""


tg.send = send
tg.edit = lambda *a, **k: None
tg.answer = lambda *a, **k: None
tg.send_document = lambda chat, data, name, caption="": (EV.append({"t": "doc", "name": name, "caption": caption}) or (True, ""))

UID, NAME = 100100, "Азиз"


def cap(title, text="", ms=0):
    EV.append({"t": "cap", "title": title, "text": text})
    if ms:
        EV.append({"t": "wait", "ms": ms})


def say(text, uid=UID, fast=False):
    EV.append({"t": "user", "text": text, "fast": fast})
    bot.handle_update({"message": {"chat": {"id": uid, "type": "private"}, "from": {"id": uid, "first_name": NAME, "last_name": "Каримов", "username": "azizk"}, "text": text}})


def tap(data_prefix, uid=UID, fast=False):
    for row in last_inline.get("rows", []):
        for label, data in row:
            if data.startswith(data_prefix):
                EV.append({"t": "tap", "label": label, "fast": fast})
                bot.handle_update({"callback_query": {"id": "1", "data": data, "from": {"id": uid, "first_name": NAME, "last_name": "Каримов", "username": "azizk"}, "message": {"message_id": 1, "chat": {"id": uid, "type": "private"}}}})
                return
    raise SystemExit("no button " + data_prefix)


# territory: the region the person works in
with db.tx() as c:
    rid = c.execute("SELECT id FROM regions WHERE name_ru='город Ташкент'").fetchone()["id"]
    did = c.execute("INSERT INTO districts(region_id,name_ru) VALUES (?,?)", (rid, "Без района")).lastrowid
    fids = [c.execute("INSERT INTO facilities(district_id,name_ru,created_at) VALUES (?,?,datetime('now'))", (did, n)).lastrowid
            for n in ("Городская клиническая больница №1", "Инфекционная больница №2", "Детская городская больница №3", "Многопрофильный центр №5")]
FAC = fids[0]

# ---- 1. access
EV.append({"t": "scene", "id": "access"})
cap("Шаг 1. Запрос доступа", "Откройте бота и нажмите /start. Регистрация занимает полминуты.")
say("/start")
cap("Выберите регион", "Достаточно региона — район указывать не нужно. Сводки можно отправлять по любому учреждению региона.")
say("🔑 Запросить доступ")
tap("rq:r:%d" % rid)
tap("rq:g:%d" % rid)
cap("Заявка ушла администратору", "Он видит её в панели и одобряет одним нажатием.", 1200)
with db.tx() as c:
    q = c.execute("SELECT id FROM access_requests").fetchone()["id"]
    out = people.decide(c, {"id": 1, "role": "super_admin", "regions": None}, q, True)
bot.notify_decision(out["tg_id"], out["facility_id"], True, "", out["region_id"])

# ---- 2. the daily report
EV.append({"t": "scene", "id": "submit"})
cap("Шаг 2. Ежедневная сводка", "Нажмите «Отправить сводку»: бот покажет учреждения региона. Нужного нет — кнопка «Добавить новое».")
say("📝 Отправить ежедневную сводку")
tap("sf:%d" % FAC)
cap("Дата — одной кнопкой", "«Сегодня» — одно нажатие. Другую дату можно просто написать: 15.11 или «вчера».")
tap("sd:%d" % FAC)
vals = ["320", "120", "84", "96", "11", "2", "3", "3", "0", "1", "18", "14"]
cap("Бот спрашивает показатели по одному", "Видно, на каком вопросе вы находитесь. Ошибки ввода ловятся сразу: текст, минус, больше чем койки.")
for i, v in enumerate(vals):
    if i == 3:
        cap("12 вопросов — меньше двух минут", "Каждое число проверяется по правилам. Невозможные значения бот не примет.")
    say(v, fast=i >= 3)
cap("Проверка перед отправкой", "Вы видите все цифры и предупреждения. Подтверждение — одна кнопка.")
tap("ok")
cap("Сводка принята", "Версия 1 сохранена. Администратор видит её в панели мгновенно.", 800)

# ---- 3. correction with comparison
EV.append({"t": "scene", "id": "fix"})
cap("Ошиблись? Исправьте — со сверкой", "Повторная отправка за ту же дату показывает, что именно изменилось, и просит подтвердить.")
say("📝 Отправить ежедневную сводку")
tap("sf:%d" % FAC)
tap("sd:%d" % FAC)
for i, v in enumerate(vals):
    if i == 3:
        say("104")
    else:
        say(f"↩️ Оставить: {v}", fast=i >= 4)
cap("Изменено только одно значение", "Видно: было 96 → стало 104. После подтверждения создаётся версия 2, история хранится.")
tap("ok")

# ---- 4. download
EV.append({"t": "scene", "id": "download"})
cap("Скачать сводку региона", "Excel или PDF за любую дату — прямо в чате, готовый к печати.")
say("📥 Скачать сводку")
tap("dd:")
tap("dx:r%d:2026-11-16:xlsx" % rid)

# ---- 5. reminder
EV.append({"t": "scene", "id": "remind"})
UID2 = 100200
with db.tx() as c:
    people.add_tg_user(c, str(UID2), "Мадина Юсупова")
    people.assign(c, {"id": 1, "role": "super_admin", "regions": None}, str(UID2), fids[2])
    people.assign(c, {"id": 1, "role": "super_admin", "regions": None}, str(UID2), fids[3])
EV.append({"t": "who", "name": "Мадина Юсупова"})
cap("Автоматические напоминания", "В 15:00 и 17:30 бот сам напоминает тем, кто ещё не сдал. Сдавшим сообщения не приходят.")
notify.run_due(datetime(2026, 11, 16, 15, 5))
EV.append({"t": "tap2", "label": "📝 Отправить сводку"})

json.dump(EV, open(os.path.join(os.path.dirname(__file__), "transcript.json"), "w"), ensure_ascii=False, indent=1)
print(len(EV), "events")
for e in EV:
    if e["t"] == "bot":
        print("BOT:", e["html"][:90].replace("\n", " | "))
    elif e["t"] in ("user", "tap", "doc", "scene"):
        print(e["t"].upper(), e.get("text") or e.get("label") or e.get("id") or e.get("name"))
