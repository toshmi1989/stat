"""Reminders and summaries (§6): the times, repeats and weekdays are settings; one message per person per slot per day is
guaranteed by the log, and a facility that has already reported is never reminded."""
from datetime import timedelta

from . import auth, bot, reports, tg
from .db import all_settings, connect, now, now_dt, today

WINDOW_MIN = 180   # a slot still counts for this long after its time (the server may have been restarted)


def _slot_due(slot: str, at) -> bool:
    hh, mm = (slot.split(":") + ["0"])[:2]
    start = at.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    return start <= at <= start + timedelta(minutes=WINDOW_MIN)


def _logged(c, kind: str, tg_id: str, day: str, slot: str) -> bool:
    return bool(c.execute("SELECT 1 FROM notify_log WHERE kind=? AND tg_id=? AND day=? AND slot=?", (kind, tg_id, day, slot)).fetchone())


def _log(c, kind, tg_id, day, slot, ok, detail="") -> None:
    c.execute("INSERT INTO notify_log(kind, tg_id, day, slot, ok, detail, at) VALUES (?,?,?,?,?,?,?)", (kind, str(tg_id), day, slot, int(ok), detail[:200], now()))
    c.commit()


def unsent_by_person(c, d: str, st: dict) -> dict:
    """{tg_id: [facility rows]} — active responsible people with the facilities that have no (or a returned) report for the date."""
    out: dict = {}
    for r in c.execute("""SELECT a.tg_id, f.id AS fid, f.name_ru, f.name_uz, u.lang FROM assignments a JOIN tg_users u ON u.tg_id=a.tg_id JOIN facilities f ON f.id=a.facility_id
                          JOIN districts dd ON dd.id=f.district_id JOIN regions r ON r.id=dd.region_id
                          LEFT JOIN reports rep ON rep.facility_id=f.id AND rep.report_date=?
                          WHERE a.active=1 AND u.active=1 AND f.active=1 AND dd.active=1 AND r.active=1 AND (rep.id IS NULL OR rep.status='returned') ORDER BY f.name_ru""", (d,)):
        out.setdefault(r["tg_id"], []).append(r)
    return out


def run_due(at=None, force: bool = False, dry: bool = False) -> list[dict]:
    """Sends what is due now. force: ignore time and the once-a-day guard (manual run). dry: only report who would get what."""
    at = at or now_dt()
    c = connect()
    res: list[dict] = []
    try:
        st = all_settings(c)
        d = at.date().isoformat()
        if st["remind_enabled"] != "1" and not (force or dry):
            return []
        weekday_ok = str(at.isoweekday()) in st["remind_weekdays"].split(",")
        slots = [s.strip() for s in st["remind_times"].split(",") if s.strip()]
        if weekday_ok or force or dry:
            unsent = unsent_by_person(c, d, st)
            for n, slot in enumerate(slots):
                if not (force or dry or _slot_due(slot, at)):
                    continue
                for tid, facs in unsent.items():
                    kind = "remind"
                    rec = {"kind": kind, "slot": slot, "tg_id": tid, "facilities": [f["name_ru"] for f in facs], "status": ""}
                    if _logged(c, kind, tid, d, slot) and not force:
                        rec["status"] = "already"
                        res.append(rec)
                        continue
                    lang = facs[0]["lang"]
                    items = "\n".join(f"🏥 {bot.esc(bot.nm(f, lang))}" for f in facs)
                    text = bot.t(lang, "remind" if n == 0 else "remind_late", date=d, items=items)
                    if dry:
                        rec["status"] = "would_send"
                        res.append(rec)
                        continue
                    ok, err = tg.send(tid, text, bot.ik([[bot.btn(bot.t(lang, "go"), "sub")]]))
                    rec["status"] = "sent" if ok else "error"
                    rec["detail"] = err
                    _log(c, kind, tid, d, slot, ok, err)
                    res.append(rec)
        for slot_key, kind in (("admin_summary_time", "admin_summary"), ("admin_overdue_time", "admin_overdue")):
            slot = st[slot_key]
            if not (force or dry or (weekday_ok and _slot_due(slot, at))):
                continue
            for s in c.execute("SELECT * FROM staff WHERE active=1 AND tg_id != '' AND role IN ('super_admin','admin')").fetchall():
                user = {"id": s["id"], "role": s["role"], "regions": None if s["role"] == "super_admin" else [r["region_id"] for r in c.execute("SELECT region_id FROM staff_scope WHERE staff_id=?", (s["id"],))]}
                rec = {"kind": kind, "slot": slot, "tg_id": s["tg_id"], "status": ""}
                if _logged(c, kind, s["tg_id"], d, slot) and not force:
                    rec["status"] = "already"
                    res.append(rec)
                    continue
                text = admin_text(c, user, d, st, overdue=(kind == "admin_overdue"))
                if text is None:
                    rec["status"] = "nothing"
                    res.append(rec)
                    continue
                if dry:
                    rec["status"] = "would_send"
                    rec["text"] = text
                    res.append(rec)
                    continue
                ok, err = tg.send(s["tg_id"], text)
                rec["status"] = "sent" if ok else "error"
                _log(c, kind, s["tg_id"], d, slot, ok, err)
                res.append(rec)
    finally:
        c.close()
    return res


def admin_text(c, user, d: str, st: dict, overdue: bool) -> str | None:
    """The summary for an administrator: how many facilities of their regions have reported and where reports are missing."""
    ctl = reports.control(c, user, d, st=st)
    k = ctl["counts"]
    if k["total"] == 0:
        return None
    missing = [r for r in ctl["rows"] if r["state"] in ("not_sent", "overdue")]
    if overdue and not ctl["overdue"]:
        return None
    if overdue and not missing:
        return None
    by: dict = {}
    for r in missing:
        by.setdefault(r["region"], []).append(r["facility"])
    head = "⚠️ <b>Просрочена отчётность</b>" if overdue else "📋 <b>Сводка по отчётности</b>"
    lines = [f"{head} за {d}", f"Отправили: <b>{k['sent'] + k['returned']}</b> из {k['total']}; не отправили: <b>{len(missing)}</b>"]
    for reg, facs in sorted(by.items(), key=lambda x: -len(x[1]))[:12]:
        lines.append(f"• {bot.esc(reg)}: {len(facs)}" + (" (" + ", ".join(bot.esc(f) for f in facs[:3]) + ("…" if len(facs) > 3 else "") + ")" if len(facs) <= 6 else ""))
    return "\n".join(lines)
