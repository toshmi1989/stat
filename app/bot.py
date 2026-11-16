"""The Telegram bot: access, requests for access, the daily report form, status and history (§4). Russian and Uzbek (Cyrillic).
Every right is checked on the server in reports.submit(); the bot only hides what a person may not do."""
import html
import json
from datetime import timedelta

from . import people, reports, rules, tg
from .db import all_settings, connect, now, now_dt, today, tx

T = {
    "ru": {
        "hello": "Здравствуйте, <b>{name}</b>!\nЭто бот ежедневной отчётности по гриппу.", "pick": "Выберите действие в меню ниже.",
        "no_access": "У вас отсутствуют права доступа для отправки отчётности. Вы можете отправить запрос администратору на предоставление доступа.",
        "m_submit": "📝 Отправить ежедневную сводку", "m_fac": "🏥 Мои учреждения", "m_status": "📊 Статус отчётности", "m_hist": "🗂 История отправленных отчётов",
        "m_req": "🔑 Запросить доступ", "m_help": "❓ Помощь", "m_lang": "🌐 Тил / Язык", "m_rights": "📋 Мои права доступа",
        "help": "<b>Как пользоваться</b>\n📝 «Отправить ежедневную сводку» — заполнить форму по вашему учреждению: бот спросит каждый показатель.\n📊 «Статус отчётности» — отправлен ли отчёт сегодня.\n🗂 «История» — ваши прошлые отчёты.\n🔑 «Запросить доступ» — если нужного учреждения нет в списке.\nОтмена в любой момент: кнопка «✖ Отмена».",
        "pick_region": "Выберите <b>регион</b>:", "pick_district": "Регион: <b>{region}</b>\nВыберите <b>район</b>:", "pick_facility": "Район: <b>{district}</b>\nВыберите <b>учреждение</b>:",
        "req_sent": "✅ Запрос отправлен администратору.\nУчреждение: <b>{fac}</b>\nКогда доступ откроют, вы получите сообщение.", "req_dup": "ℹ️ {why}",
        "approved": "✅ Вам открыт доступ к учреждению <b>{fac}</b>. Теперь можно отправлять отчёты.", "rejected": "❌ Запрос на доступ к учреждению <b>{fac}</b> отклонён.{note}",
        "rights": "<b>Мои права доступа</b>", "rights_none": "Закреплённых учреждений нет.", "rights_pending": "\n\n<b>Ожидают рассмотрения:</b>", "primary": "основной", "reserve": "резервный",
        "pick_fac_submit": "Выберите <b>учреждение</b>, по которому отправляете отчёт:", "pick_date": "За какую <b>дату</b> отчёт?",
        "exists_edit": "Отчёт по этому учреждению за {date} уже отправлен (версия {ver}). Его можно исправить.", "exists_locked": "Отчёт за {date} уже отправлен ({sent}). Исправление недоступно — обратитесь к администратору.",
        "returned": "↩️ Отчёт возвращён на исправление: {why}", "fix": "✏️ Исправить отчёт", "nothing_to_send": "За доступные даты все отчёты уже отправлены. ✅",
        "form_head": "<b>{fac}</b>\nОтчётная дата: <b>{date}</b>\n\nПоказатель {i}/{n}:\n<b>{name}</b>", "form_hint": "Введите целое число (0 или больше).{old}",
        "bad_number": "⚠️ Нужно целое число, не меньше нуля. Попробуйте ещё раз.", "back": "⬅️ Назад", "cancel": "✖ Отмена", "cancelled": "Отправка отменена.",
        "preview": "<b>Проверьте отчёт</b>\n{path}\nОтчётная дата: <b>{date}</b>\n\n{lines}", "errors": "\n\n❌ <b>Ошибки (отправка невозможна):</b>\n{items}", "warnings": "\n\n⚠️ <b>Предупреждения (можно отправить):</b>\n{items}",
        "confirm": "✅ Подтвердить и отправить", "change": "✏️ Изменить данные", "pick_field": "Какой показатель изменить?", "send_anyway": "✅ Отправить всё равно",
        "saved": "✅ Отчёт отправлен.\n{fac}, {date}\nВерсия: {ver}", "saved_late": "\n⏰ Отправлен после установленного срока.", "saved_fix": "✅ Отчёт исправлен.\n{fac}, {date}\nВерсия: {ver}",
        "fail": "❌ {msg}", "status_head": "<b>Статус отчётности</b>", "st_sent": "✅ отправлен в {t}", "st_none": "❌ не отправлен", "st_ret": "↩️ возвращён: {why}", "st_over": "⚠️ просрочен",
        "hist_head": "<b>Ваши последние отчёты</b>", "hist_none": "Отправленных отчётов пока нет.", "hist_item": "{date} · {fac} · v{ver} · {st}", "rep": "<b>{fac}</b>\n{date}, версия {ver}\n\n{lines}",
        "lang_set": "Язык: русский 🇷🇺", "region": "Регион", "district": "Район", "facility": "Учреждение", "next": "Далее ▶️", "prev": "◀️ Назад",
        "remind": "🔔 <b>Напоминание!</b>\n\nНеобходимо предоставить ежедневную сводку по гриппу за <b>{date}</b>.\n\n{items}\n\nСтатус: отчёт не отправлен.\nПожалуйста, заполните отчёт через бота.",
        "remind_late": "🔔 <b>Повторное напоминание.</b> Отчёт за <b>{date}</b> всё ещё не отправлен:\n\n{items}", "go": "📝 Отправить сводку",
        "stopped": "Вы остановлены администратором. Обратитесь к руководителю.",
    },
    "uz": {
        "hello": "Ассалому алайкум, <b>{name}</b>!\nБу грипп бўйича кундалик ҳисобот боти.", "pick": "Қуйидаги менюдан танланг.",
        "no_access": "Сизда ҳисобот юбориш учун рухсат йўқ. Администраторга рухсат бериш сўровини юборишингиз мумкин.",
        "m_submit": "📝 Кундалик маълумот юбориш", "m_fac": "🏥 Менинг муассасаларим", "m_status": "📊 Ҳисобот ҳолати", "m_hist": "🗂 Юборилган ҳисоботлар тарихи",
        "m_req": "🔑 Рухсат сўраш", "m_help": "❓ Ёрдам", "m_lang": "🌐 Тил / Язык", "m_rights": "📋 Менинг рухсатларим",
        "help": "<b>Қандай фойдаланиш</b>\n📝 «Кундалик маълумот юбориш» — муассасангиз бўйича шаклни тўлдиринг: бот ҳар бир кўрсаткични сўрайди.\n📊 «Ҳисобот ҳолати» — бугун ҳисобот юборилганми.\n🗂 «Тарих» — олдинги ҳисоботларингиз.\n🔑 «Рухсат сўраш» — керакли муассаса рўйхатда бўлмаса.\nИстаган пайтда бекор қилиш: «✖ Бекор қилиш» тугмаси.",
        "pick_region": "<b>Вилоятни</b> танланг:", "pick_district": "Вилоят: <b>{region}</b>\n<b>Туманни</b> танланг:", "pick_facility": "Туман: <b>{district}</b>\n<b>Муассасани</b> танланг:",
        "req_sent": "✅ Сўров администраторга юборилди.\nМуассаса: <b>{fac}</b>\nРухсат берилгач, сизга хабар келади.", "req_dup": "ℹ️ {why}",
        "approved": "✅ Сизга <b>{fac}</b> муассасаси бўйича рухсат берилди. Энди ҳисобот юборишингиз мумкин.", "rejected": "❌ <b>{fac}</b> муассасасига рухсат сўрови рад этилди.{note}",
        "rights": "<b>Менинг рухсатларим</b>", "rights_none": "Бириктирилган муассасалар йўқ.", "rights_pending": "\n\n<b>Кўриб чиқилмоқда:</b>", "primary": "асосий", "reserve": "захира",
        "pick_fac_submit": "Ҳисобот юбораётган <b>муассасани</b> танланг:", "pick_date": "Қайси <b>санага</b> ҳисобот?",
        "exists_edit": "Бу муассаса бўйича {date} санасидаги ҳисобот юборилган (версия {ver}). Уни тузатиш мумкин.", "exists_locked": "{date} санасидаги ҳисобот юборилган ({sent}). Тузатиш мумкин эмас — администраторга мурожаат қилинг.",
        "returned": "↩️ Ҳисобот тузатиш учун қайтарилди: {why}", "fix": "✏️ Ҳисоботни тузатиш", "nothing_to_send": "Мавжуд саналар учун барча ҳисоботлар юборилган. ✅",
        "form_head": "<b>{fac}</b>\nҲисобот санаси: <b>{date}</b>\n\nКўрсаткич {i}/{n}:\n<b>{name}</b>", "form_hint": "Бутун сон киритинг (0 ёки катта).{old}",
        "bad_number": "⚠️ Нолдан кичик бўлмаган бутун сон керак. Яна уриниб кўринг.", "back": "⬅️ Орқага", "cancel": "✖ Бекор қилиш", "cancelled": "Юбориш бекор қилинди.",
        "preview": "<b>Ҳисоботни текширинг</b>\n{path}\nҲисобот санаси: <b>{date}</b>\n\n{lines}", "errors": "\n\n❌ <b>Хатолар (юбориш мумкин эмас):</b>\n{items}", "warnings": "\n\n⚠️ <b>Огоҳлантиришлар (юбориш мумкин):</b>\n{items}",
        "confirm": "✅ Тасдиқлаш ва юбориш", "change": "✏️ Маълумотни ўзгартириш", "pick_field": "Қайси кўрсаткични ўзгартирасиз?", "send_anyway": "✅ Барибир юбориш",
        "saved": "✅ Ҳисобот юборилди.\n{fac}, {date}\nВерсия: {ver}", "saved_late": "\n⏰ Белгиланган муддатдан кейин юборилди.", "saved_fix": "✅ Ҳисобот тузатилди.\n{fac}, {date}\nВерсия: {ver}",
        "fail": "❌ {msg}", "status_head": "<b>Ҳисобот ҳолати</b>", "st_sent": "✅ {t} да юборилган", "st_none": "❌ юборилмаган", "st_ret": "↩️ қайтарилган: {why}", "st_over": "⚠️ муддати ўтган",
        "hist_head": "<b>Сўнгги ҳисоботларингиз</b>", "hist_none": "Юборилган ҳисоботлар ҳали йўқ.", "hist_item": "{date} · {fac} · v{ver} · {st}", "rep": "<b>{fac}</b>\n{date}, версия {ver}\n\n{lines}",
        "lang_set": "Тил: ўзбекча 🇺🇿", "region": "Вилоят", "district": "Туман", "facility": "Муассаса", "next": "Кейинги ▶️", "prev": "◀️ Орқага",
        "remind": "🔔 <b>Эслатма!</b>\n\n<b>{date}</b> санаси учун грипп бўйича кундалик маълумотни тақдим этиш керак.\n\n{items}\n\nҲолат: ҳисобот юборилмаган.\nИлтимос, ботда ҳисоботни тўлдиринг.",
        "remind_late": "🔔 <b>Такрорий эслатма.</b> <b>{date}</b> санаси учун ҳисобот ҳали юборилмаган:\n\n{items}", "go": "📝 Маълумот юбориш",
        "stopped": "Сиз администратор томонидан тўхтатилгансиз. Раҳбарга мурожаат қилинг.",
    },
}


def t(lang: str, key: str, **kw) -> str:
    s = T.get(lang, T["ru"]).get(key) or T["ru"][key]
    return s.format(**kw) if kw else s


MENU_KEYS = {"m_submit": "submit", "m_fac": "fac", "m_status": "status", "m_hist": "hist", "m_req": "req", "m_help": "help", "m_lang": "lang", "m_rights": "rights"}
MENU_TEXT = {T[lang][k]: a for lang in T for k, a in MENU_KEYS.items()}
CANCEL_TEXT = {T[lang]["cancel"] for lang in T}


def esc(s) -> str:
    return html.escape(str(s or ""), quote=False)


def nm(row, lang: str, base: str = "name") -> str:
    """The name of a row in the person's language (Uzbek when it exists)."""
    if lang == "uz" and row[f"{base}_uz"]:
        return row[f"{base}_uz"]
    return row[f"{base}_ru"]


def main_kb(lang: str, has_access: bool) -> dict:
    rows = [[{"text": t(lang, "m_submit")}], [{"text": t(lang, "m_fac")}, {"text": t(lang, "m_status")}], [{"text": t(lang, "m_hist")}, {"text": t(lang, "m_req")}],
            [{"text": t(lang, "m_rights") if not has_access else t(lang, "m_help")}, {"text": t(lang, "m_lang")}]]
    if not has_access:
        rows = [[{"text": t(lang, "m_req")}], [{"text": t(lang, "m_rights")}, {"text": t(lang, "m_help")}], [{"text": t(lang, "m_lang")}]]
    return {"keyboard": rows, "resize_keyboard": True, "is_persistent": True}


def ik(rows) -> dict:
    return {"inline_keyboard": rows}


def btn(text, data) -> dict:
    return {"text": text, "callback_data": data}


# ---------------------------------------------------------------- state
def get_state(c, tg_id: str) -> dict:
    r = c.execute("SELECT * FROM bot_state WHERE tg_id=?", (tg_id,)).fetchone()
    return {"state": r["state"], "data": json.loads(r["data"])} if r else {"state": "", "data": {}}


def set_state(c, tg_id: str, state: str = "", data: dict | None = None) -> None:
    c.execute("INSERT INTO bot_state(tg_id, state, data, updated_at) VALUES (?,?,?,?) ON CONFLICT(tg_id) DO UPDATE SET state=excluded.state, data=excluded.data, updated_at=excluded.updated_at",
              (tg_id, state, json.dumps(data or {}, ensure_ascii=False), now()))


# ---------------------------------------------------------------- entry point
def handle_update(u: dict) -> None:
    if u.get("callback_query"):
        return handle_callback(u["callback_query"])
    msg = u.get("message") or {}
    chat = msg.get("chat") or {}
    if chat.get("type") != "private" or not msg.get("text"):
        return
    frm = msg.get("from") or {}
    text = msg["text"].strip()
    with tx() as c:
        user = people.touch(c, frm, all_settings(c)["default_lang"])
        lang = user["lang"]
        if not user["active"]:
            tg.send(chat["id"], t(lang, "stopped"))
            return
        has = bool(reports.user_facilities(c, user["tg_id"]))
        st = get_state(c, user["tg_id"])
        cmd = text.split()[0].split("@")[0].lower()
        action = MENU_TEXT.get(text) or {"/start": "start", "/help": "help", "/status": "status", "/cancel": "cancel", "/submit": "submit", "/lang": "lang"}.get(cmd)
        if text in CANCEL_TEXT or action == "cancel":
            set_state(c, user["tg_id"])
            tg.send(chat["id"], t(lang, "cancelled"), main_kb(lang, has))
            return
        if action:
            set_state(c, user["tg_id"])
            return do_action(c, user, chat["id"], action, has)
        if st["state"] in ("form", "edit_field"):
            return form_input(c, user, chat["id"], st, text, has)
        tg.send(chat["id"], t(lang, "pick"), main_kb(lang, has))


def do_action(c, user, chat, action: str, has: bool) -> None:
    lang, tid = user["lang"], user["tg_id"]
    if action == "start":
        name = " ".join(x for x in (user["first_name"], user["last_name"]) if x) or user["username"] or tid
        tg.send(chat, t(lang, "hello", name=esc(name)) + "\n\n" + (t(lang, "pick") if has else t(lang, "no_access")), main_kb(lang, has))
    elif action == "help":
        tg.send(chat, t(lang, "help"), main_kb(lang, has))
    elif action == "lang":
        new = "uz" if lang == "ru" else "ru"
        c.execute("UPDATE tg_users SET lang=? WHERE tg_id=?", (new, tid))
        tg.send(chat, t(new, "lang_set"), main_kb(new, has))
    elif action in ("fac", "rights"):
        show_rights(c, user, chat, has)
    elif action == "req":
        regions = c.execute("SELECT id, name_ru, name_uz FROM regions WHERE active=1 ORDER BY sort").fetchall()
        rows = [[btn(nm(r, lang), f"rq:r:{r['id']}")] for r in regions]
        tg.send(chat, t(lang, "pick_region"), ik(rows))
    elif action == "status":
        show_status(c, user, chat, has)
    elif action == "hist":
        show_history(c, user, chat, has)
    elif action == "submit":
        begin_submit(c, user, chat, has)


def show_rights(c, user, chat, has) -> None:
    lang = user["lang"]
    facs = reports.user_facilities(c, user["tg_id"])
    lines = [f"• <b>{esc(nm(f, lang))}</b>\n   {esc(nm(f, lang, 'region'))} / {esc(nm(f, lang, 'district'))} ({t(lang, f['kind'])})" for f in facs]
    pend = c.execute("""SELECT f.name_ru, f.name_uz FROM access_requests q JOIN facilities f ON f.id=q.facility_id WHERE q.tg_id=? AND q.status='pending'""", (user["tg_id"],)).fetchall()
    text = t(lang, "rights") + "\n\n" + ("\n".join(lines) if lines else t(lang, "rights_none"))
    if pend:
        text += t(lang, "rights_pending") + "\n" + "\n".join("• " + esc(nm(p, lang)) for p in pend)
    tg.send(chat, text, main_kb(lang, has))


def show_status(c, user, chat, has) -> None:
    lang = user["lang"]
    st = all_settings(c)
    facs = reports.user_facilities(c, user["tg_id"])
    if not facs:
        return tg.send(chat, t(lang, "no_access"), main_kb(lang, has))
    out = [t(lang, "status_head")]
    for f in facs:
        out.append(f"\n<b>{esc(nm(f, lang))}</b>")
        for d in reports.allowed_dates(st):
            rep = reports.find(c, f["id"], d.isoformat())
            if rep:
                s = t(lang, "st_ret", why=esc(rep["return_reason"])) if rep["status"] == "returned" else t(lang, "st_sent", t=rep["submitted_at"][11:16])
            else:
                s = t(lang, "st_over") if now_dt() > reports.deadline(st, d) else t(lang, "st_none")
            out.append(f"{d.strftime('%d.%m')}: {s}")
    tg.send(chat, "\n".join(out), main_kb(lang, has))


def show_history(c, user, chat, has) -> None:
    lang = user["lang"]
    rows = c.execute("""SELECT rep.id, rep.report_date, rep.version, rep.status, f.name_ru, f.name_uz FROM reports rep JOIN facilities f ON f.id=rep.facility_id
                        JOIN assignments a ON a.facility_id=f.id AND a.tg_id=? AND a.active=1 ORDER BY rep.report_date DESC, rep.id DESC LIMIT 10""", (user["tg_id"],)).fetchall()
    if not rows:
        return tg.send(chat, t(lang, "hist_none"), main_kb(lang, has))
    kb = [[btn(t(lang, "hist_item", date=r["report_date"][5:].replace("-", "."), fac=nm(r, lang)[:28], ver=r["version"], st="↩️" if r["status"] == "returned" else "✅"), f"hi:{r['id']}")] for r in rows]
    tg.send(chat, t(lang, "hist_head"), ik(kb))


# ---------------------------------------------------------------- the daily report form
def indicator_list(c) -> list:
    return c.execute("SELECT code, name_ru, name_uz, hint_ru, hint_uz FROM indicators WHERE active=1 ORDER BY sort").fetchall()


def begin_submit(c, user, chat, has) -> None:
    lang = user["lang"]
    facs = reports.user_facilities(c, user["tg_id"])
    if not facs:
        return tg.send(chat, t(lang, "no_access"), main_kb(lang, has))
    if len(facs) == 1:
        return pick_facility(c, user, chat, facs[0]["id"])
    tg.send(chat, t(lang, "pick_fac_submit"), ik([[btn(nm(f, lang)[:60], f"sf:{f['id']}")] for f in facs]))


def pick_facility(c, user, chat, fid: int, message_id=None) -> None:
    lang = user["lang"]
    st = all_settings(c)
    if not reports.access(c, user["tg_id"], fid):
        return tg.send(chat, t(lang, "fail", msg="У вас нет прав отправлять отчёт за это учреждение"))
    options = []
    for d in reports.allowed_dates(st):
        rep = reports.find(c, fid, d.isoformat())
        if rep is None or reports.user_can_edit(rep, st):
            options.append((d, rep))
    if not options:
        return tg.send(chat, t(lang, "nothing_to_send"), main_kb(lang, True))
    if len(options) == 1:
        return pick_date(c, user, chat, fid, options[0][0].isoformat())
    kb = [[btn(d.strftime("%d.%m.%Y") + (" ✏️" if rep else ""), f"sd:{fid}:{d.isoformat()}")] for d, rep in options]
    tg.send(chat, t(lang, "pick_date"), ik(kb))


def pick_date(c, user, chat, fid: int, d: str) -> None:
    lang = user["lang"]
    st = all_settings(c)
    if not reports.access(c, user["tg_id"], fid):
        return tg.send(chat, t(lang, "fail", msg="У вас нет прав отправлять отчёт за это учреждение"))
    rep = reports.find(c, fid, d)
    values = {}
    if rep:
        if not reports.user_can_edit(rep, st):
            return tg.send(chat, t(lang, "exists_locked", date=d, sent=rep["submitted_at"][:16]), main_kb(lang, True))
        values = reports.values_of(c, rep["id"])
        note = t(lang, "returned", why=esc(rep["return_reason"])) if rep["status"] == "returned" else t(lang, "exists_edit", date=d, ver=rep["version"])
        tg.send(chat, note)
    codes = [i["code"] for i in indicator_list(c)]
    set_state(c, user["tg_id"], "form", {"fid": fid, "date": d, "codes": codes, "idx": 0, "values": values, "fix": bool(rep)})
    ask(c, user, chat, get_state(c, user["tg_id"])["data"])


def ask(c, user, chat, data: dict) -> None:
    lang = user["lang"]
    inds = {i["code"]: i for i in indicator_list(c)}
    i = data["idx"]
    ind = inds[data["codes"][i]]
    f = reports.facility_info(c, data["fid"])
    old = data["values"].get(ind["code"])
    hint = (ind["hint_uz"] if lang == "uz" and ind["hint_uz"] else ind["hint_ru"])
    text = t(lang, "form_head", fac=esc(nm(f, lang)), date=data["date"], i=i + 1, n=len(data["codes"]), name=esc(nm(ind, lang))) + "\n\n" + t(lang, "form_hint", old=(f"\nТекущее значение: <b>{old}</b>" if old is not None else "")) + (f"\n<i>{esc(hint)}</i>" if hint else "")
    kb = {"keyboard": [[{"text": t(lang, "back")}, {"text": t(lang, "cancel")}]], "resize_keyboard": True}
    tg.send(chat, text, kb)


def form_input(c, user, chat, st: dict, text: str, has: bool) -> None:
    lang, tid, data = user["lang"], user["tg_id"], st["data"]
    if text == t(lang, "back") and st["state"] == "form":
        if data["idx"] > 0:
            data["idx"] -= 1
            set_state(c, tid, "form", data)
            return ask(c, user, chat, data)
        return
    if text == t(lang, "back") and st["state"] == "edit_field":
        return preview(c, user, chat, data)
    s = text.replace(" ", "")
    if not s.isdigit():
        return tg.send(chat, t(lang, "bad_number"))
    code = data["codes"][data["idx"]] if st["state"] == "form" else data["edit_code"]
    data["values"][code] = int(s)
    if st["state"] == "form":
        data["idx"] += 1
        if data["idx"] < len(data["codes"]):
            set_state(c, tid, "form", data)
            return ask(c, user, chat, data)
    set_state(c, tid, "preview", data)
    preview(c, user, chat, data)


def preview(c, user, chat, data: dict, message_id=None) -> None:
    lang, tid = user["lang"], user["tg_id"]
    f = reports.facility_info(c, data["fid"])
    inds = indicator_list(c)
    lines = "\n".join(f"{esc(nm(i, lang))}: <b>{data['values'].get(i['code'], '—')}</b>" for i in inds)
    res = rules.validate(c, data["values"], lang, data["fid"], data["date"])
    path = f"{esc(nm(f, lang, 'region'))} / {esc(nm(f, lang, 'district'))} / <b>{esc(nm(f, lang))}</b>"
    text = t(lang, "preview", path=path, date=data["date"], lines=lines)
    if res["errors"]:
        text += t(lang, "errors", items="\n".join("• " + esc(e) for e in res["errors"]))
    if res["warnings"]:
        text += t(lang, "warnings", items="\n".join("• " + esc(w) for w in res["warnings"]))
    rows = []
    if not res["errors"]:
        rows.append([btn(t(lang, "send_anyway") if res["warnings"] else t(lang, "confirm"), "ok")])
    rows.append([btn(t(lang, "change"), "ch")])
    rows.append([btn(t(lang, "cancel"), "no")])
    set_state(c, tid, "preview", data)
    tg.send(chat, text, ik(rows))


def handle_callback(cq: dict) -> None:
    msg = cq.get("message") or {}
    chat = (msg.get("chat") or {}).get("id")
    data = cq.get("data", "")
    with tx() as c:
        user = people.touch(c, cq["from"], all_settings(c)["default_lang"])
        lang = user["lang"]
        has = bool(reports.user_facilities(c, user["tg_id"]))
        tg.answer(cq["id"])
        if not user["active"]:
            return
        p = data.split(":")
        k = p[0]
        if k == "rq":
            return request_flow(c, user, chat, msg, p)
        if k == "sf":
            return pick_facility(c, user, chat, int(p[1]))
        if k == "sd":
            return pick_date(c, user, chat, int(p[1]), p[2])
        if k == "go" or k == "sub":
            return begin_submit(c, user, chat, has)
        if k == "hi":
            return show_report(c, user, chat, int(p[1]))
        st = get_state(c, user["tg_id"])
        if k in ("ok", "ch", "no", "ef") and st["state"] not in ("preview", "edit_pick", "edit_field"):
            return
        d = st["data"]
        if k == "no":
            set_state(c, user["tg_id"])
            return tg.send(chat, t(lang, "cancelled"), main_kb(lang, has))
        if k == "ch":
            inds = indicator_list(c)
            set_state(c, user["tg_id"], "edit_pick", d)
            return tg.send(chat, t(lang, "pick_field"), ik([[btn(f"{nm(i, lang)[:48]}: {d['values'].get(i['code'], '—')}", f"ef:{i['code']}")] for i in inds]))
        if k == "ef":
            d["edit_code"] = p[1]
            set_state(c, user["tg_id"], "edit_field", d)
            ind = c.execute("SELECT name_ru, name_uz FROM indicators WHERE code=?", (p[1],)).fetchone()
            kb = {"keyboard": [[{"text": t(lang, "back")}, {"text": t(lang, "cancel")}]], "resize_keyboard": True}
            return tg.send(chat, f"<b>{esc(nm(ind, lang))}</b>\n" + t(lang, "form_hint", old=f"\nТекущее значение: <b>{d['values'].get(p[1], '—')}</b>"), kb)
        if k == "ok":
            return confirm(c, user, chat, d, has)


def request_flow(c, user, chat, msg, p) -> None:
    lang = user["lang"]
    step = p[1]
    if step == "r":
        r = c.execute("SELECT * FROM regions WHERE id=? AND active=1", (int(p[2]),)).fetchone()
        if not r:
            return
        ds = c.execute("SELECT id, name_ru, name_uz FROM districts WHERE region_id=? AND active=1 ORDER BY name_ru", (r["id"],)).fetchall()
        return paged(chat, lang, t(lang, "pick_district", region=esc(nm(r, lang))), ds, f"rq:d:", int(p[3]) if len(p) > 3 else 0, f"rq:r:{r['id']}")
    if step == "d":
        d = c.execute("SELECT * FROM districts WHERE id=? AND active=1", (int(p[2]),)).fetchone()
        if not d:
            return
        fs = c.execute("SELECT id, name_ru, name_uz FROM facilities WHERE district_id=? AND active=1 ORDER BY name_ru", (d["id"],)).fetchall()
        return paged(chat, lang, t(lang, "pick_facility", district=esc(nm(d, lang))), fs, "rq:f:", int(p[3]) if len(p) > 3 else 0, f"rq:d:{d['id']}")
    if step == "f":
        fid = int(p[2])
        f = c.execute("SELECT name_ru, name_uz FROM facilities WHERE id=?", (fid,)).fetchone()
        try:
            rid = people.create_request(c, user["tg_id"], fid)
        except people.PeopleError as e:
            return tg.send(chat, t(lang, "req_dup", why=esc(e.message)))
        tg.send(chat, t(lang, "req_sent", fac=esc(nm(f, lang))))
        notify_admins_about_request(c, rid)


def paged(chat, lang, text, items, prefix, page, self_cb, per=10) -> None:
    chunk = items[page * per:(page + 1) * per]
    rows = [[btn(nm(i, lang)[:60], f"{prefix}{i['id']}")] for i in chunk]
    nav = []
    if page > 0:
        nav.append(btn(t(lang, "prev"), f"{self_cb}:{page - 1}"))
    if (page + 1) * per < len(items):
        nav.append(btn(t(lang, "next"), f"{self_cb}:{page + 1}"))
    if nav:
        rows.append(nav)
    tg.send(chat, text, ik(rows))


def confirm(c, user, chat, d: dict, has: bool) -> None:
    lang = user["lang"]
    f = reports.facility_info(c, d["fid"])
    try:
        out = reports.submit(c, d["fid"], d["date"], d["values"], reports.by_tg(user), lang)
    except reports.ReportError as e:
        set_state(c, user["tg_id"])
        return tg.send(chat, t(lang, "fail", msg=esc(e.message)), main_kb(lang, has))
    set_state(c, user["tg_id"])
    text = t(lang, "saved" if out.get("created") else "saved_fix", fac=esc(nm(f, lang)), date=d["date"], ver=out["version"])
    if out.get("late") and out.get("created"):
        text += t(lang, "saved_late")
    tg.send(chat, text, main_kb(lang, True))


def show_report(c, user, chat, rid: int) -> None:
    lang = user["lang"]
    rep = c.execute("SELECT * FROM reports WHERE id=?", (rid,)).fetchone()
    if not rep or not reports.access(c, user["tg_id"], rep["facility_id"]):
        return
    f = reports.facility_info(c, rep["facility_id"])
    vals = reports.values_of(c, rid)
    lines = "\n".join(f"{esc(nm(i, lang))}: <b>{vals.get(i['code'], '—')}</b>" for i in indicator_list(c))
    tg.send(chat, t(lang, "rep", fac=esc(nm(f, lang)), date=rep["report_date"], ver=rep["version"], lines=lines))


# ---------------------------------------------------------------- notifications triggered from the web
def notify_admins_about_request(c, request_id: int) -> None:
    q = c.execute("""SELECT q.*, u.first_name, u.last_name, u.username, r.name_ru AS region, d.name_ru AS district, f.name_ru AS facility
                     FROM access_requests q JOIN tg_users u ON u.tg_id=q.tg_id JOIN regions r ON r.id=q.region_id JOIN districts d ON d.id=q.district_id JOIN facilities f ON f.id=q.facility_id WHERE q.id=?""", (request_id,)).fetchone()
    if not q:
        return
    who = " ".join(x for x in (q["first_name"], q["last_name"]) if x) or "—"
    text = (f"🔑 <b>Новый запрос доступа</b>\n{esc(who)}" + (f" (@{esc(q['username'])})" if q["username"] else "") + f", Telegram ID {q['tg_id']}\n"
            f"{esc(q['region'])} / {esc(q['district'])} / <b>{esc(q['facility'])}</b>\nРассмотрите запрос в разделе «Запросы доступа».")
    for s in c.execute("SELECT * FROM staff WHERE active=1 AND tg_id != '' AND (role='super_admin' OR (role='admin' AND can_manage_users=1))").fetchall():
        if s["role"] == "admin" and not c.execute("SELECT 1 FROM staff_scope WHERE staff_id=? AND region_id=?", (s["id"], q["region_id"])).fetchone():
            continue
        tg.send(s["tg_id"], text)


def notify_decision(tg_id: str, facility_id: int, approved: bool, note: str = "") -> None:
    c = connect()
    try:
        u = c.execute("SELECT * FROM tg_users WHERE tg_id=?", (tg_id,)).fetchone()
        f = c.execute("SELECT name_ru, name_uz FROM facilities WHERE id=?", (facility_id,)).fetchone()
        if not u or not f:
            return
        lang = u["lang"]
        has = bool(reports.user_facilities(c, tg_id))
        text = t(lang, "approved", fac=esc(nm(f, lang))) if approved else t(lang, "rejected", fac=esc(nm(f, lang)), note=("\n" + esc(note)) if note else "")
        tg.send(tg_id, text, main_kb(lang, has))
    finally:
        c.close()
