"""Broadcasts: a message written on the site goes to the people of the bot (everyone with access, chosen regions, or those who have not reported today).
It is sent in the background at a gentle pace (Telegram allows about 30 messages a second); every person's result is kept, a stopped run can be resumed."""
import threading
import time

from . import auth, bot, notify, tg
from .db import all_settings, audit, connect, now, today, tx

MAX_LEN = 3500
PACE = 0.06                     # seconds between messages
HEADER = {"ru": "📢 <b>Объявление</b>\n\n", "uz": "📢 <b>E’lon</b>\n\n"}
RUNNING: dict[int, threading.Thread] = {}
ALIVE_SEC = 120                 # a sending broadcast that has not made a move for this long is taken as interrupted (the service runs in several processes: only the database knows)


class BroadcastError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message, self.status = message, status


def texts(ru, uz) -> tuple[str, str]:
    ru, uz = str(ru or "").strip(), str(uz or "").strip()
    if not ru and not uz:
        raise BroadcastError("Напишите текст рассылки (хотя бы на одном языке)")
    if len(ru) > MAX_LEN or len(uz) > MAX_LEN:
        raise BroadcastError(f"Текст длиннее {MAX_LEN} знаков: Telegram не примет")
    return ru, uz


def body_for(lang: str, ru: str, uz: str) -> tuple[str, bool]:
    """The text for a person and whether it is a fallback (the person's own language was left empty)."""
    own, other = (uz, ru) if lang == "uz" else (ru, uz)
    use = own or other
    return HEADER["uz" if (lang == "uz" and own) or (lang != "uz" and not own) else "ru"] + bot.esc(use), not own


def norm_spec(spec: dict) -> dict:
    """The audience as {roles: all|heads|responsibles, regions: [ids], report: any|unsent|sent}. The older form {mode: all|regions|unsent|heads|responsibles} still works."""
    spec = spec or {}
    regions = [int(x) for x in (spec.get("regions") or []) if str(x).isdigit()]
    if "roles" in spec or "report" in spec:
        roles = spec.get("roles") if spec.get("roles") in ("heads", "responsibles") else "all"
        report = spec.get("report") if spec.get("report") in ("unsent", "sent") else "any"
        return {"roles": roles, "regions": regions, "report": report}
    mode = spec.get("mode") or "all"
    return {"roles": mode if mode in ("heads", "responsibles") else "all", "regions": regions, "report": "unsent" if mode == "unsent" else "any", "need_regions": mode == "regions"}


def recipients(c, user, spec: dict) -> list[dict]:
    """The people of the bot the sender may write to: active, with access in the regions of the sender (and in the chosen ones), by role (heads of regions: the main person of the list of
    a region, confirmed by his phone; responsible: everybody else with access) and by today's report (still owe it / have sent it)."""
    sp = norm_spec(spec)
    mine = user["regions"]                                         # None = every region
    chosen = sp["regions"]
    if sp.get("need_regions") and not chosen:
        raise BroadcastError("Выберите хотя бы один регион")
    if chosen:
        regions = [r for r in chosen if mine is None or r in mine]
        if not regions:
            raise BroadcastError("Эти регионы вам недоступны", 403)
    else:
        regions = None if mine is None else list(mine)
    if regions is not None and not regions:
        return []
    # The heads of regions are the people whose verified phone is the phone of the head of a region in the list (one main person per region); they are not everyone who has the access to a
    # region: in this system many responsible people hold the access to a whole region. All the others with the access (to a region or to facilities) are the responsible ones.
    q = ",".join("?" * len(regions)) if regions is not None else ""
    head_any = "EXISTS (SELECT 1 FROM region_contacts k WHERE k.kind='main' AND u.phone!='' AND (',' || k.phone || ',') LIKE '%,' || u.phone || ',%')"
    head_in = "EXISTS (SELECT 1 FROM region_contacts k WHERE k.kind='main' AND u.phone!='' AND (',' || k.phone || ',') LIKE '%,' || u.phone || ',%'" + (f" AND k.region_id IN ({q})" if regions is not None else "") + ")"
    acc_r = "EXISTS (SELECT 1 FROM region_access ra WHERE ra.tg_id=u.tg_id AND ra.active=1" + (f" AND ra.region_id IN ({q})" if regions is not None else "") + ")"
    acc_f = ("EXISTS (SELECT 1 FROM assignments a JOIN facilities f ON f.id=a.facility_id JOIN districts d ON d.id=f.district_id WHERE a.tg_id=u.tg_id AND a.active=1"
             + (f" AND d.region_id IN ({q})" if regions is not None else "") + ")")
    rg = list(regions) if regions is not None else []
    resp = f"(({acc_r} OR {acc_f}) AND NOT {head_any})"
    if sp["roles"] == "heads":
        who, args = head_in, rg
    elif sp["roles"] == "responsibles":
        who, args = resp, rg + rg
    else:
        who, args = f"({head_in} OR {resp})", rg + rg + rg
    rows = c.execute(f"SELECT u.tg_id, u.lang, u.first_name, u.last_name, u.username FROM tg_users u WHERE u.active=1 AND {who} ORDER BY u.first_name, u.last_name", args).fetchall()
    if sp["report"] != "any":
        owe = notify.unsent_by_person(c, today().isoformat(), all_settings(c))     # who still owes today's report (a returned one counts as not sent)
        rows = [r for r in rows if (r["tg_id"] in owe) == (sp["report"] == "unsent")]
    return [{"tg_id": r["tg_id"], "lang": r["lang"] or "uz", "name": " ".join(x for x in (r["first_name"], r["last_name"]) if x) or r["username"] or r["tg_id"]} for r in rows]


# ---------------------------------------------------------------- the figures in the text: {name} {region} {facility} {sent} {total} {unsent} {percent} {unsent_list} {status} {date} {deadline}
PLACEHOLDERS = ["name", "facility", "region", "date", "deadline", "sent", "total", "unsent", "percent", "unsent_list", "status"]
LBL = {"ru": {"sent": "✅ сдан", "none": "❌ не сдан", "more": "…и ещё {n}", "none_all": "все сдали"}, "uz": {"sent": "✅ topshirilgan", "none": "❌ topshirilmagan", "more": "…yana {n} ta", "none_all": "hammasi topshirgan"}}
LIST_MAX = 40


def personalize(c, text: str, tg_id: str, lang: str, d: str | None = None, st: dict | None = None) -> str:
    """The text for one person with the figures filled in from the database at this moment: his facilities (and, for the head of a region, all of the region) and today's reports.
    A text without {…} is returned as it is; an unknown {word} stays as written."""
    if "{" not in text:
        return text
    import re
    st = st or all_settings(c)
    d = d or today().isoformat()
    lang = "uz" if lang == "uz" else "ru"
    u = c.execute("SELECT first_name, last_name, username FROM tg_users WHERE tg_id=?", (str(tg_id),)).fetchone()
    name = (" ".join(x for x in (u["first_name"], u["last_name"]) if x) or u["username"] or str(tg_id)) if u else str(tg_id)
    sel = """SELECT f.id, f.name_ru, f.name_uz, r.id AS rid, r.name_ru AS rname_ru, r.name_uz AS rname_uz FROM facilities f JOIN districts d ON d.id=f.district_id JOIN regions r ON r.id=d.region_id
             WHERE f.active=1 AND d.active=1 AND r.active=1 AND """
    own = c.execute(sel + "f.id IN (SELECT facility_id FROM assignments WHERE tg_id=? AND active=1) ORDER BY f.name_ru", (str(tg_id),)).fetchall()
    reg = c.execute(sel + "r.id IN (SELECT region_id FROM region_access WHERE tg_id=? AND active=1) ORDER BY f.name_ru", (str(tg_id),)).fetchall()
    scope = {f["id"]: f for f in list(own) + list(reg)}
    ids = list(scope)
    got = {}
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        for r in c.execute(f"SELECT facility_id, status FROM reports WHERE report_date=? AND facility_id IN ({','.join('?' * len(part))})", [d] + part):
            got[r["facility_id"]] = r["status"]
    sent_ids = {i for i in ids if i in got and got[i] != "returned"}
    unsent = [scope[i] for i in sorted(ids, key=lambda i: scope[i]["name_ru"]) if i not in sent_ids]
    nmf = lambda f: bot.esc(bot.nm({"name_ru": f["name_ru"], "name_uz": f["name_uz"]}, lang))
    nmr = lambda f: bot.esc(bot.nm({"name_ru": f["rname_ru"], "name_uz": f["rname_uz"]}, lang))
    lab = LBL[lang]
    regions = list(dict.fromkeys(nmr(f) for f in (reg or own)))
    base = list(own) or list(reg)                                       # the facilities the person answers for: his own, or (access to a region only) those of the region
    shown = [f for f in base if f["id"] not in sent_ids] or base         # a reminder is about the ones that have not sent (about all of them when everything is sent)
    own_names = [nmf(f) for f in shown]
    contacts = bot.contact_lines(c, [f["id"] for f in unsent[:LIST_MAX]]) if reg else {}
    lines = [f"{k}. {nmf(f)}" + (f" — {contacts[f['id']]}" if f["id"] in contacts else "") for k, f in enumerate(unsent[:LIST_MAX], 1)]
    if len(unsent) > LIST_MAX:
        lines.append(lab["more"].format(n=len(unsent) - LIST_MAX))
    status = [f"• {nmf(f)} — {lab['sent'] if f['id'] in sent_ids else lab['none']}" for f in own]
    deadline = st.get("deadline_time", "18:00")
    vals = {"name": bot.esc(name), "date": f"{d[8:10]}.{d[5:7]}.{d[:4]}", "deadline": deadline, "region": ", ".join(regions), "facility": (", ".join(own_names[:3]) + (f" (+{len(own_names) - 3})" if len(own_names) > 3 else "")) or ", ".join(regions) or "—",
            "sent": str(len(sent_ids)), "total": str(len(ids)), "unsent": str(len(unsent)), "percent": str(round(100 * len(sent_ids) / len(ids))) if ids else "0",
            "unsent_list": "\n".join(lines) if lines else lab["none_all"], "status": "\n".join(status)}
    out = re.sub(r"\{(\w+)\}", lambda m: vals.get(m.group(1), m.group(0)) if m.group(1) in PLACEHOLDERS else m.group(0), text)
    return out[:3900]


def preview(c, user, spec: dict, ru, uz, sample_tg_id: str = "") -> dict:
    ru, uz = texts(ru, uz)
    people = recipients(c, user, spec)
    fallback = sum(1 for p in people if body_for(p["lang"], ru, uz)[1])
    pick = next((p for p in people if p["tg_id"] == str(sample_tg_id)), people[0] if people else None)
    sample = {"tg_id": pick["tg_id"], "name": pick["name"], "lang": pick["lang"], "text": personalize(c, body_for(pick["lang"], ru, uz)[0], pick["tg_id"], pick["lang"])} if pick else None
    return {"total": len(people), "uz": sum(1 for p in people if p["lang"] == "uz"), "ru": sum(1 for p in people if p["lang"] != "uz"), "fallback": fallback,
            "people": [p["name"] for p in people[:40]], "list": [{"tg_id": p["tg_id"], "name": p["name"], "lang": p["lang"]} for p in people[:200]],
            "sample": sample, "sample_ru": body_for("ru", ru, uz)[0], "sample_uz": body_for("uz", ru, uz)[0]}


def audience(c, user, spec: dict) -> dict:
    """Only the number and the names of the people the audience reaches (for the counter that follows the choice on the page)."""
    people = recipients(c, user, spec)
    return {"total": len(people), "uz": sum(1 for p in people if p["lang"] == "uz"), "ru": sum(1 for p in people if p["lang"] != "uz"), "list": [{"tg_id": p["tg_id"], "name": p["name"], "lang": p["lang"]} for p in people[:200]],
            "unlinked_heads": unlinked_heads(c, user, spec) if norm_spec(spec)["roles"] in ("heads", "all") else []}


def unlinked_heads(c, user, spec: dict) -> list[dict]:
    """The heads of the regions of the audience that nobody in the bot has confirmed yet (no person of the bot has their phone): they cannot get a broadcast until they write to the bot
    and send their number."""
    from . import editor
    sp = norm_spec(spec)
    mine = user["regions"]
    out = []
    known = {r["phone"] for r in c.execute("SELECT phone FROM tg_users WHERE phone!='' AND active=1")}
    for k in c.execute("SELECT k.region_id, k.fio, k.phone, r.name_ru, r.name_uz FROM region_contacts k JOIN regions r ON r.id=k.region_id WHERE k.kind='main' AND r.active=1 ORDER BY r.sort").fetchall():
        if (mine is not None and k["region_id"] not in mine) or (sp["regions"] and k["region_id"] not in sp["regions"]):
            continue
        if not any(p in known for p in editor.phones(k["phone"])):
            out.append({"region_id": k["region_id"], "region": k["name_ru"], "region_uz": k["name_uz"], "fio": k["fio"], "phone": k["phone"]})
    return out


def start(c, user, spec: dict, ru, uz) -> int:
    ru, uz = texts(ru, uz)
    people = recipients(c, user, spec)
    if not people:
        raise BroadcastError("Получателей нет: никто не подходит под выбранных")
    import json
    cur = c.execute("INSERT INTO broadcasts(created_by, created_at, text_ru, text_uz, audience, total) VALUES (?,?,?,?,?,?)", (user["id"], now(), ru, uz, json.dumps(spec, ensure_ascii=False), len(people)))
    bid = cur.lastrowid
    c.executemany("INSERT INTO broadcast_log(broadcast_id, tg_id, lang, status) VALUES (?,?,?, 'queued')", [(bid, p["tg_id"], p["lang"]) for p in people])
    audit(c, "broadcast.start", "broadcast", bid, {"total": len(people), "audience": norm_spec(spec)})
    return bid


def launch(bid: int) -> None:
    """Starts (or restarts) the background sending of the queued messages of a broadcast."""
    if bid in RUNNING and RUNNING[bid].is_alive():
        return
    th = threading.Thread(target=_run, args=(bid,), name=f"broadcast-{bid}", daemon=True)
    RUNNING[bid] = th
    th.start()


def _run(bid: int) -> None:
    try:
        c = connect()
        try:
            b = c.execute("SELECT text_ru, text_uz FROM broadcasts WHERE id=?", (bid,)).fetchone()
            c.execute("UPDATE broadcasts SET status='sending', heartbeat=? WHERE id=?", (now(), bid))
            c.commit()
            queue = [(r["tg_id"], r["lang"]) for r in c.execute("SELECT tg_id, lang FROM broadcast_log WHERE broadcast_id=? AND status='queued' ORDER BY rowid", (bid,))]
        finally:
            c.close()
        for tid, lang in queue:
            with tx() as c:                                    # a row is taken by exactly one sender, even if two of them run (several processes, a restart)
                took = c.execute("UPDATE broadcast_log SET status='sending' WHERE broadcast_id=? AND tg_id=? AND status='queued'", (bid, tid)).rowcount
                c.execute("UPDATE broadcasts SET heartbeat=? WHERE id=?", (now(), bid))
            if not took:
                continue
            text, _ = body_for(lang, b["text_ru"], b["text_uz"])
            with tx() as c:                                    # the figures of this person at this moment (a long run has fresh ones for the last person too)
                text = personalize(c, text, tid, lang)
            ok, err = tg.send(tid, text)                       # the network call: no transaction is open
            with tx() as c:
                c.execute("UPDATE broadcast_log SET status=?, error=?, at=? WHERE broadcast_id=? AND tg_id=?", ("sent" if ok else "failed", "" if ok else err[:200], now(), bid, tid))
                c.execute("UPDATE broadcasts SET sent=sent+?, failed=failed+?, heartbeat=? WHERE id=?", (1 if ok else 0, 0 if ok else 1, now(), bid))
            time.sleep(PACE)
        with tx() as c:
            c.execute("UPDATE broadcasts SET status='done', finished_at=? WHERE id=?", (now(), bid))
    except Exception as e:      # the sender must never die silently: the broadcast is marked and can be resumed
        with tx() as c:
            c.execute("UPDATE broadcasts SET status='interrupted' WHERE id=?", (bid,))
        raise e
    finally:
        RUNNING.pop(bid, None)


def listing(c, user) -> list[dict]:
    from datetime import datetime, timedelta
    limit = (datetime.strptime(now(), "%Y-%m-%d %H:%M:%S") - timedelta(seconds=ALIVE_SEC)).strftime("%Y-%m-%d %H:%M:%S")
    for r in c.execute("SELECT id, created_at, heartbeat FROM broadcasts WHERE status='sending'").fetchall():
        if (r["heartbeat"] or r["created_at"]) < limit:                          # nobody has touched it for two minutes: the sender is gone (a restart)
            c.execute("UPDATE broadcasts SET status='interrupted' WHERE id=?", (r["id"],))
    sql = """SELECT b.id, b.created_at, b.finished_at, b.text_ru, b.text_uz, b.audience, b.total, b.sent, b.failed, b.status, COALESCE(s.name, s.login, '') AS by_name,
                    (SELECT COUNT(*) FROM broadcast_log l WHERE l.broadcast_id=b.id AND l.status='queued') AS queued
             FROM broadcasts b LEFT JOIN staff s ON s.id=b.created_by"""
    rows = c.execute(sql + ("" if auth.is_super(user) else " WHERE b.created_by=?") + " ORDER BY b.id DESC LIMIT 100", () if auth.is_super(user) else (user["id"],)).fetchall()
    return [dict(r) for r in rows]


def failures(c, user, bid: int) -> list[dict]:
    b = c.execute("SELECT created_by FROM broadcasts WHERE id=?", (bid,)).fetchone()
    if not b or (not auth.is_super(user) and b["created_by"] != user["id"]):
        raise BroadcastError("Рассылка не найдена", 404)
    return [dict(r) for r in c.execute("""SELECT l.tg_id, l.error, TRIM(COALESCE(u.first_name,'') || ' ' || COALESCE(u.last_name,'')) AS name, u.username FROM broadcast_log l
                                          LEFT JOIN tg_users u ON u.tg_id=l.tg_id WHERE l.broadcast_id=? AND l.status='failed' LIMIT 200""", (bid,))]


def resume(c, user, bid: int) -> None:
    b = c.execute("SELECT created_by, status FROM broadcasts WHERE id=?", (bid,)).fetchone()
    if not b or (not auth.is_super(user) and b["created_by"] != user["id"]):
        raise BroadcastError("Рассылка не найдена", 404)
    if b["status"] == "sending":                                     # the sender is alive (the list calls a silent one interrupted): nothing to resume
        return
    c.execute("UPDATE broadcast_log SET status='queued', error='' WHERE broadcast_id=? AND status IN ('failed','sending')", (bid,))      # failed ones are tried again too
    c.execute("UPDATE broadcasts SET failed=0, status='sending', heartbeat=? WHERE id=?", (now(), bid))
    c.execute("UPDATE broadcasts SET sent=(SELECT COUNT(*) FROM broadcast_log WHERE broadcast_id=? AND status='sent') WHERE id=?", (bid, bid))


def send_test(c, user, ru, uz, tg_id: str = "") -> str:
    """The text as it will look, to the sender's own Telegram (or to a known person of the bot): nothing is recorded."""
    ru, uz = texts(ru, uz)
    tid = str(tg_id or "").strip() or (c.execute("SELECT tg_id FROM staff WHERE id=?", (user["id"],)).fetchone() or {"tg_id": ""})["tg_id"]
    if not tid:
        raise BroadcastError("Укажите Telegram ID для теста (свой: его показывает @userinfobot) или заполните его в профиле сотрудника")
    row = c.execute("SELECT lang FROM tg_users WHERE tg_id=?", (tid,)).fetchone()
    if not row:
        raise BroadcastError("Этот Telegram ID не пользуется ботом: откройте бота и нажмите Start, потом повторите")
    text, _ = body_for(row["lang"] or "uz", ru, uz)
    text = personalize(c, text, tid, row["lang"] or "uz")
    ok, err = tg.send(tid, "🧪 <i>тест</i>\n\n" + text)
    if not ok:
        raise BroadcastError("Telegram не принял тест: " + err)
    return tid


# ---------------------------------------------------------------- ready-made texts and saved ones
def _aud(roles="all", report="any"):
    return {"roles": roles, "regions": [], "report": report}


BUILTIN = [
    {"id": "remind", "name_ru": "Напоминание: сдайте сводку", "name_uz": "Eslatma: hisobotni topshiring", "audience": _aud("responsibles", "unsent"),
     "text_ru": "Здравствуйте, {name}! Сводка за {date} по «{facility}» пока не получена. Срок сдачи — {deadline}. Отправьте её в боте: «Отправить ежедневную сводку».",
     "text_uz": "Assalomu alaykum, {name}! {date} sanasi uchun «{facility}» bo‘yicha hisobot hali kelib tushmadi. Topshirish muddati — {deadline}. Uni botda yuboring: «Kundalik ma’lumot yuborish»."},
    {"id": "head_summary", "name_ru": "Сводка региона для руководителя", "name_uz": "Rahbar uchun viloyat hisoboti", "audience": _aud("heads"),
     "text_ru": "{region}: за {date} сдали {sent} из {total} учреждений ({percent}%).\nНе сдали ({unsent}):\n{unsent_list}",
     "text_uz": "{region}: {date} sanasi uchun {total} ta muassasadan {sent} tasi hisobot topshirdi ({percent}%).\nTopshirmaganlar ({unsent}):\n{unsent_list}"},
    {"id": "head_remind", "name_ru": "Руководителям: напомнить не сдавшим", "name_uz": "Rahbarlarga: topshirmaganlarga eslatish", "audience": _aud("heads", "unsent"),
     "text_ru": "{name}, по региону «{region}» не сдали сводку за {date} ({unsent} из {total}):\n{unsent_list}\nПожалуйста, свяжитесь с ответственными: срок — {deadline}.",
     "text_uz": "{name}, «{region}» bo‘yicha {date} sanasi uchun hisobot topshirmaganlar ({total} tadan {unsent} ta):\n{unsent_list}\nIltimos, mas’ul shaxslar bilan bog‘laning: muddat — {deadline}."},
    {"id": "resp_status", "name_ru": "Ответственным: итоги по их учреждениям", "name_uz": "Mas’ullarga: muassasalari bo‘yicha natijalar", "audience": _aud("responsibles"),
     "text_ru": "{name}, ваши учреждения за {date}:\n{status}",
     "text_uz": "{name}, {date} sanasi uchun muassasalaringiz:\n{status}"},
    {"id": "thanks", "name_ru": "Благодарность сдавшим", "name_uz": "Topshirganlarga minnatdorchilik", "audience": _aud("responsibles", "sent"),
     "text_ru": "{name}, спасибо! Сводка за {date} получена. Хорошего дня.", "text_uz": "{name}, rahmat! {date} sanasi uchun hisobot qabul qilindi. Yaxshi kun tilaymiz."},
    {"id": "free", "name_ru": "Свободный текст", "name_uz": "Erkin matn", "audience": _aud(), "text_ru": "Уважаемый(ая) {name}! ", "text_uz": "Hurmatli {name}! "},
]


def templates(c, user) -> list[dict]:
    """The ready-made texts and the ones people saved (everyone sees the ready-made ones and their own; the super administrator sees all)."""
    import json
    rows = c.execute("SELECT t.*, COALESCE(s.name, s.login, '') AS by_name FROM broadcast_templates t LEFT JOIN staff s ON s.id=t.created_by ORDER BY t.id DESC").fetchall()
    mine = [dict(r) | {"audience": json.loads(r["audience"] or "{}"), "builtin": False, "id": r["id"]} for r in rows if auth.is_super(user) or r["created_by"] == user["id"]]
    return [dict(b, builtin=True) for b in BUILTIN] + mine


def template_save(c, user, name: str, ru, uz, spec: dict) -> int:
    import json
    name = " ".join(str(name or "").split())[:80]
    if len(name) < 2:
        raise BroadcastError("Дайте шаблону название")
    ru, uz = texts(ru, uz)
    cur = c.execute("INSERT INTO broadcast_templates(name, text_ru, text_uz, audience, created_by, created_at) VALUES (?,?,?,?,?,?)", (name, ru, uz, json.dumps(norm_spec(spec) | {}, ensure_ascii=False), user["id"], now()))
    return cur.lastrowid


def template_delete(c, user, tid: int) -> None:
    r = c.execute("SELECT created_by FROM broadcast_templates WHERE id=?", (tid,)).fetchone()
    if not r or (not auth.is_super(user) and r["created_by"] != user["id"]):
        raise BroadcastError("Шаблон не найден", 404)
    c.execute("DELETE FROM broadcast_templates WHERE id=?", (tid,))


# ---------------------------------------------------------------- broadcasts on a schedule
REPEATS = ("once", "daily", "weekdays")


def schedules(c, user) -> list[dict]:
    import json
    rows = c.execute("SELECT x.*, COALESCE(s.name, s.login, '') AS by_name FROM broadcast_schedules x LEFT JOIN staff s ON s.id=x.created_by ORDER BY x.active DESC, x.id DESC").fetchall()
    return [dict(r) | {"audience": json.loads(r["audience"] or "{}")} for r in rows if auth.is_super(user) or r["created_by"] == user["id"]]


def schedule_save(c, user, data: dict) -> int:
    """A broadcast that goes by itself: once (a date and a time), every day or on weekdays (Mon–Fri) at a time. The audience and the figures are taken when it goes."""
    import json
    import re
    ru, uz = texts(data.get("text_ru"), data.get("text_uz"))
    repeat, at_time, run_date = str(data.get("repeat") or "once"), str(data.get("at_time") or ""), str(data.get("run_date") or "")
    if repeat not in REPEATS:
        raise BroadcastError("Повтор: один раз, каждый день или по будням")
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", at_time):
        raise BroadcastError("Время отправки в виде ЧЧ:ММ")
    if repeat == "once" and (not re.fullmatch(r"\d{4}-\d{2}-\d{2}", run_date) or run_date < today().isoformat()):
        raise BroadcastError("Укажите дату отправки: сегодня или позже")
    spec = norm_spec(data.get("audience") or {})
    recipients(c, user, spec)                                       # the rights of the sender over the chosen regions are checked now, and again when it goes
    title = " ".join(str(data.get("title") or "").split())[:80]
    if data.get("id"):
        r = c.execute("SELECT created_by FROM broadcast_schedules WHERE id=?", (int(data["id"]),)).fetchone()
        if not r or (not auth.is_super(user) and r["created_by"] != user["id"]):
            raise BroadcastError("Расписание не найдено", 404)
        c.execute("UPDATE broadcast_schedules SET title=?, audience=?, text_ru=?, text_uz=?, repeat=?, at_time=?, run_date=?, active=1, last_result='' WHERE id=?",
                  (title, json.dumps(spec, ensure_ascii=False), ru, uz, repeat, at_time, run_date if repeat == "once" else "", int(data["id"])))
        sid = int(data["id"])
    else:
        sid = c.execute("INSERT INTO broadcast_schedules(title, created_by, created_at, audience, text_ru, text_uz, repeat, at_time, run_date) VALUES (?,?,?,?,?,?,?,?,?)",
                        (title, user["id"], now(), json.dumps(spec, ensure_ascii=False), ru, uz, repeat, at_time, run_date if repeat == "once" else "")).lastrowid
    audit(c, "broadcast.schedule", "broadcast_schedule", sid, {"repeat": repeat, "at": at_time, "audience": spec})
    return sid


def schedule_set(c, user, sid: int, active: bool | None = None, delete: bool = False) -> None:
    r = c.execute("SELECT created_by FROM broadcast_schedules WHERE id=?", (sid,)).fetchone()
    if not r or (not auth.is_super(user) and r["created_by"] != user["id"]):
        raise BroadcastError("Расписание не найдено", 404)
    if delete:
        c.execute("DELETE FROM broadcast_schedules WHERE id=?", (sid,))
    elif active is not None:
        c.execute("UPDATE broadcast_schedules SET active=? WHERE id=?", (1 if active else 0, sid))
    audit(c, "broadcast.schedule", "broadcast_schedule", sid, {"delete": delete, "active": active})


def _staff_user(c, staff_id) -> dict | None:
    r = c.execute("SELECT id, login, name, role, tg_id, can_manage_users FROM staff WHERE id=? AND active=1", (staff_id,)).fetchone()
    if not r:
        return None
    u = dict(r)
    u["regions"] = None if u["role"] == "super_admin" else [x["region_id"] for x in c.execute("SELECT region_id FROM staff_scope WHERE staff_id=?", (u["id"],))]
    return u


def run_due(at=None) -> list[dict]:
    """Starts what is due now (called every half a minute with the reminders): a schedule whose time has come and that has not gone today. A one-time broadcast of a past day that
    was never sent (the service was off) is closed as missed, not sent late."""
    from . import db
    import json
    at = at or db.now_dt()
    d, hm = at.date().isoformat(), at.strftime("%H:%M")
    out, launch_ids = [], []
    with tx() as c:
        for x in c.execute("SELECT * FROM broadcast_schedules WHERE active=1 AND last_run_date!=?", (d,)).fetchall():
            if x["repeat"] == "once" and x["run_date"] < d:
                c.execute("UPDATE broadcast_schedules SET active=0, last_result=? WHERE id=?", ("пропущено: сервис был выключен", x["id"])); continue
            if (x["repeat"] == "once" and x["run_date"] != d) or (x["repeat"] == "weekdays" and at.isoweekday() > 5) or hm < x["at_time"]:
                continue
            user = _staff_user(c, x["created_by"])
            res, bid = "", None
            if not user:
                res = "отправитель отключён"
            else:
                try:
                    bid = start(c, user, json.loads(x["audience"] or "{}"), x["text_ru"], x["text_uz"])
                    launch_ids.append(bid)
                    res = "отправлено"
                except BroadcastError as e:
                    res = e.message
            c.execute("UPDATE broadcast_schedules SET last_run_date=?, last_broadcast_id=?, last_result=?, active=? WHERE id=?", (d, bid, res, 0 if x["repeat"] == "once" else 1, x["id"]))
            out.append({"id": x["id"], "broadcast": bid, "result": res})
    for bid in launch_ids:
        launch(bid)
    return out
