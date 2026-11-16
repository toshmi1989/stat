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
    # access to a whole region: every facility of the region that has not reported
    seen = {(tid, r["fid"]) for tid, rows in out.items() for r in rows}
    for r in c.execute("""SELECT ra.tg_id, f.id AS fid, f.name_ru, f.name_uz, u.lang FROM region_access ra JOIN tg_users u ON u.tg_id=ra.tg_id JOIN regions r ON r.id=ra.region_id
                          JOIN districts dd ON dd.region_id=r.id JOIN facilities f ON f.district_id=dd.id
                          LEFT JOIN reports rep ON rep.facility_id=f.id AND rep.report_date=?
                          WHERE ra.active=1 AND u.active=1 AND f.active=1 AND dd.active=1 AND r.active=1 AND (rep.id IS NULL OR rep.status='returned') ORDER BY f.name_ru""", (d,)):
        if (r["tg_id"], r["fid"]) not in seen:
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
                    items = "\n".join(f"🏥 {bot.esc(bot.nm(f, lang))}" for f in facs[:20])
                    if len(facs) > 20:
                        items += "\n" + bot.t(lang, "and_more", n=len(facs) - 20)
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


MANUAL_PAUSE_MIN = 60   # the same person is not nagged again within this time by the button


def remind_now(c, user, d: str, region_id=None, dry: bool = False) -> dict:
    """The 'remind those who have not reported' button: a message to every responsible person (and region manager) who still owes a
    report for the date. Limited to the regions of the administrator; a person reminded less than an hour ago is skipped."""
    st = all_settings(c)
    ctl = reports.control(c, user, d, region_id=region_id, st=st)
    missing = {r["facility_id"]: r for r in ctl["rows"] if r["state"] in ("not_sent", "overdue")}
    orphans = [f"{r['region']} — {r['facility']}" for r in missing.values() if not r["has_responsible"]]
    people: dict = {}
    for tid, facs in unsent_by_person(c, d, st).items():
        mine = [f for f in facs if f["fid"] in missing]
        if mine:
            people[tid] = mine
    names = {u["tg_id"]: (" ".join(x for x in (u["first_name"], u["last_name"]) if x) or u["username"] or u["tg_id"]) for u in c.execute("SELECT * FROM tg_users")}
    cutoff = (now_dt() - timedelta(minutes=MANUAL_PAUSE_MIN)).strftime("%Y-%m-%d %H:%M:%S")
    res = {"date": d, "missing": len(missing), "people": len(people), "sent": 0, "skipped": 0, "errors": 0, "no_responsible": orphans[:50], "no_responsible_total": len(orphans), "items": [], "dry": dry}
    for tid, facs in people.items():
        lang = facs[0]["lang"]
        rec = {"tg_id": tid, "name": names.get(tid, tid), "facilities": len(facs), "status": ""}
        recent = c.execute("SELECT 1 FROM notify_log WHERE kind='remind_manual' AND tg_id=? AND day=? AND ok=1 AND at>=?", (tid, d, cutoff)).fetchone()
        if recent:
            rec["status"] = "skipped"
            res["skipped"] += 1
        elif dry:
            rec["status"] = "would_send"
        else:
            items = "\n".join(f"🏥 {bot.esc(bot.nm(f, lang))}" for f in facs[:20]) + (("\n" + bot.t(lang, "and_more", n=len(facs) - 20)) if len(facs) > 20 else "")
            ok, err = tg.send(tid, bot.t(lang, "remind", date=d, items=items), bot.ik([[bot.btn(bot.t(lang, "go"), "sub")]]))
            rec["status"] = "sent" if ok else "error"
            rec["detail"] = err
            res["sent" if ok else "errors"] += 1
            _log(c, "remind_manual", tid, d, "manual", ok, err)
        res["items"].append(rec)
    if not dry:
        from .db import audit
        audit(c, "notify.manual", "notify", d, {"sent": res["sent"], "skipped": res["skipped"], "errors": res["errors"], "region": region_id})
        c.commit()
    return res
