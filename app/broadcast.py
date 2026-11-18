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


def recipients(c, user, spec: dict) -> list[dict]:
    """The people of the bot the sender may write to: active, with access in the regions of the sender (and in the chosen ones)."""
    mode = spec.get("mode") or "all"
    mine = user["regions"]                                         # None = every region
    chosen = [int(x) for x in (spec.get("regions") or []) if str(x).isdigit()]
    if mode == "regions":
        if not chosen:
            raise BroadcastError("Выберите хотя бы один регион")
        regions = [r for r in chosen if mine is None or r in mine]
        if not regions:
            raise BroadcastError("Эти регионы вам недоступны", 403)
    else:
        regions = None if mine is None else list(mine)
    cond_r = cond_a = ""
    args: list = []
    if regions is not None:
        if not regions:
            return []
        q = ",".join("?" * len(regions))
        cond_r, cond_a = f" AND ra.region_id IN ({q})", f" AND d.region_id IN ({q})"
        args = regions + regions
    rows = c.execute(f"""SELECT u.tg_id, u.lang, u.first_name, u.last_name, u.username FROM tg_users u WHERE u.active=1 AND (
                           EXISTS (SELECT 1 FROM region_access ra WHERE ra.tg_id=u.tg_id AND ra.active=1{cond_r})
                           OR EXISTS (SELECT 1 FROM assignments a JOIN facilities f ON f.id=a.facility_id JOIN districts d ON d.id=f.district_id WHERE a.tg_id=u.tg_id AND a.active=1{cond_a}))
                         ORDER BY u.first_name, u.last_name""", args).fetchall()
    if mode == "unsent":                                           # only those who still owe today's report
        owe = notify.unsent_by_person(c, today().isoformat(), all_settings(c))
        rows = [r for r in rows if r["tg_id"] in owe]
    return [{"tg_id": r["tg_id"], "lang": r["lang"] or "uz", "name": " ".join(x for x in (r["first_name"], r["last_name"]) if x) or r["username"] or r["tg_id"]} for r in rows]


def preview(c, user, spec: dict, ru, uz) -> dict:
    ru, uz = texts(ru, uz)
    people = recipients(c, user, spec)
    fallback = sum(1 for p in people if body_for(p["lang"], ru, uz)[1])
    return {"total": len(people), "uz": sum(1 for p in people if p["lang"] == "uz"), "ru": sum(1 for p in people if p["lang"] != "uz"), "fallback": fallback,
            "people": [p["name"] for p in people[:40]], "sample_ru": body_for("ru", ru, uz)[0], "sample_uz": body_for("uz", ru, uz)[0]}


def start(c, user, spec: dict, ru, uz) -> int:
    ru, uz = texts(ru, uz)
    people = recipients(c, user, spec)
    if not people:
        raise BroadcastError("Получателей нет: никто не подходит под выбранных")
    import json
    cur = c.execute("INSERT INTO broadcasts(created_by, created_at, text_ru, text_uz, audience, total) VALUES (?,?,?,?,?,?)", (user["id"], now(), ru, uz, json.dumps(spec, ensure_ascii=False), len(people)))
    bid = cur.lastrowid
    c.executemany("INSERT INTO broadcast_log(broadcast_id, tg_id, lang, status) VALUES (?,?,?, 'queued')", [(bid, p["tg_id"], p["lang"]) for p in people])
    audit(c, "broadcast.start", "broadcast", bid, {"total": len(people), "mode": spec.get("mode") or "all"})
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
    ok, err = tg.send(tid, "🧪 <i>тест</i>\n\n" + text)
    if not ok:
        raise BroadcastError("Telegram не принял тест: " + err)
    return tid
