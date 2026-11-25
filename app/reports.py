"""Daily reports: who may send what, the one report per facility and date, corrections with a reason, immutable versions,
locking, and the control table of who has reported (§4, §6.3, §9.1, §11)."""
import json
from datetime import date, datetime, timedelta

from . import rules
from .db import TZ, all_settings, audit, now, now_dt, today


class ReportError(Exception):
    def __init__(self, message: str, status: int = 400, details: dict | None = None):
        super().__init__(message)
        self.message, self.status, self.details = message, status, details or {}


def parse_date(s) -> date:
    try:
        return date.fromisoformat(str(s))
    except ValueError:
        raise ReportError("Дата должна быть в формате ГГГГ-ММ-ДД")


def deadline(st: dict, d: date) -> datetime:
    """The moment after which the report for the date d is overdue."""
    hh, mm = (st["deadline_time"].split(":") + ["0"])[:2]
    return datetime.combine(d + timedelta(days=int(st["deadline_day_offset"])), datetime.min.time()).replace(hour=int(hh), minute=int(mm), tzinfo=TZ)


def allowed_dates(st: dict, ref: date | None = None) -> list[date]:
    ref = ref or today()
    return [ref - timedelta(days=i) for i in range(0, int(st["backfill_days"]) + 1)]


def by_tg(u) -> dict:
    return {"kind": "tg", "id": str(u["tg_id"]), "name": " ".join(x for x in (u["first_name"], u["last_name"]) if x) or (u["username"] or str(u["tg_id"]))}


def by_staff(u) -> dict:
    return {"kind": "staff", "id": str(u["id"]), "name": u["name"] or u["login"]}


# ---------------------------------------------------------------- who may report for what
def facility_info(c, fid: int):
    return c.execute("""SELECT f.id, f.name_ru, f.name_uz, f.active, f.contact, d.id AS district_id, d.name_ru AS district_ru, d.name_uz AS district_uz,
                               r.id AS region_id, r.name_ru AS region_ru, r.name_uz AS region_uz, (f.active AND d.active AND r.active) AS live
                        FROM facilities f JOIN districts d ON d.id=f.district_id JOIN regions r ON r.id=d.region_id WHERE f.id=?""", (fid,)).fetchone()


def access(c, tg_id: str, facility_id: int):
    """The active right of this Telegram user to report for this facility, or None: a direct assignment, or access to the whole
    region the facility belongs to. The server decides, whatever the bot shows."""
    direct = _direct_access(c, tg_id, facility_id)
    if direct:
        return direct
    return c.execute("""SELECT ra.* FROM region_access ra JOIN tg_users u ON u.tg_id=ra.tg_id JOIN regions r ON r.id=ra.region_id
                        JOIN districts d ON d.region_id=r.id JOIN facilities f ON f.district_id=d.id
                        WHERE ra.tg_id=? AND f.id=? AND ra.active=1 AND u.active=1 AND f.active=1 AND d.active=1 AND r.active=1""", (str(tg_id), facility_id)).fetchone()


def user_regions(c, tg_id: str) -> list:
    return c.execute("""SELECT r.id, r.name_ru, r.name_uz, ra.kind FROM region_access ra JOIN tg_users u ON u.tg_id=ra.tg_id JOIN regions r ON r.id=ra.region_id
                        WHERE ra.tg_id=? AND ra.active=1 AND u.active=1 AND r.active=1 ORDER BY r.sort""", (str(tg_id),)).fetchall()


def has_access(c, tg_id: str) -> bool:
    return bool(user_facilities(c, tg_id) or user_regions(c, tg_id))


def _direct_access(c, tg_id: str, facility_id: int):
    return c.execute("""SELECT a.* FROM assignments a JOIN tg_users u ON u.tg_id=a.tg_id JOIN facilities f ON f.id=a.facility_id
                        JOIN districts d ON d.id=f.district_id JOIN regions r ON r.id=d.region_id
                        WHERE a.tg_id=? AND a.facility_id=? AND a.active=1 AND u.active=1 AND f.active=1 AND d.active=1 AND r.active=1""", (str(tg_id), facility_id)).fetchone()


def user_facilities(c, tg_id: str) -> list:
    return c.execute("""SELECT f.id, f.name_ru, f.name_uz, d.name_ru AS district_ru, d.name_uz AS district_uz, r.name_ru AS region_ru, r.name_uz AS region_uz, a.kind
                        FROM assignments a JOIN tg_users u ON u.tg_id=a.tg_id JOIN facilities f ON f.id=a.facility_id JOIN districts d ON d.id=f.district_id JOIN regions r ON r.id=d.region_id
                        WHERE a.tg_id=? AND a.active=1 AND u.active=1 AND f.active=1 AND d.active=1 AND r.active=1 ORDER BY r.sort, d.name_ru, f.name_ru""", (str(tg_id),)).fetchall()


# ---------------------------------------------------------------- locking and editing windows
def effective_locked(rep, st: dict, ref: datetime | None = None) -> bool:
    if rep["locked"]:
        return True
    n = int(st["lock_after_days"])
    return bool(n and rep["status"] != "returned" and (ref or now_dt()).date() > date.fromisoformat(rep["report_date"]) + timedelta(days=n))


def user_can_edit(rep, st: dict, ref: datetime | None = None) -> bool:
    ref = ref or now_dt()
    if st["allow_user_edit"] != "1" or effective_locked(rep, st, ref):
        return False
    if rep["status"] == "returned":
        return True
    return ref <= datetime.fromisoformat(rep["submitted_at"]).replace(tzinfo=TZ) + timedelta(hours=int(st["edit_window_hours"]))


# ---------------------------------------------------------------- reading
def values_of(c, report_id: int) -> dict:
    return {r["code"]: r["value"] for r in c.execute("SELECT code, value FROM report_values WHERE report_id=?", (report_id,))}


def find(c, facility_id: int, d: str):
    return c.execute("SELECT * FROM reports WHERE facility_id=? AND report_date=?", (facility_id, d)).fetchone()


def get_report(c, report_id: int) -> dict:
    r = c.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
    if not r:
        raise ReportError("Отчёт не найден", 404)
    f = facility_info(c, r["facility_id"])
    st = all_settings(c)
    out = dict(r) | {"values": values_of(c, report_id), "facility": f["name_ru"], "facility_uz": f["name_uz"], "district": f["district_ru"], "region": f["region_ru"],
                     "region_id": f["region_id"], "district_id": f["district_id"], "locked_now": effective_locked(r, st)}
    out["versions"] = [dict(v) | {"vals": json.loads(v["vals"]), "changes": json.loads(v["changes"])} for v in
                       c.execute("SELECT * FROM report_versions WHERE report_id=? ORDER BY id DESC", (report_id,))]
    return out


# ---------------------------------------------------------------- writing
def _version(c, rid: int, version: int, action: str, by: dict, reason: str, vals: dict, changes: dict) -> None:
    c.execute("INSERT INTO report_versions(report_id, version, action, by_kind, by_id, by_name, at, reason, vals, changes) VALUES (?,?,?,?,?,?,?,?,?,?)",
              (rid, version, action, by["kind"], by["id"], by["name"], now(), reason, json.dumps(vals, ensure_ascii=False), json.dumps(changes, ensure_ascii=False)))


def _clean(c, values: dict) -> dict:
    codes = {r["code"] for r in c.execute("SELECT code FROM indicators")}
    return {k: v for k, v in values.items() if k in codes}


def _check(c, facility_id, d, values, lang, partial=False):
    res = rules.validate(c, values, lang, facility_id, d, partial)
    if res["errors"]:
        raise ReportError(res["errors"][0], 422, res)
    return res


def submit(c, facility_id: int, d: str, values: dict, by: dict, lang: str = "ru", force_warnings: bool = True) -> dict:
    """A responsible person sends (or, inside the allowed window, corrects) the report of a facility for a date."""
    st = all_settings(c)
    dd = parse_date(d)
    f = facility_info(c, facility_id)
    if not f or not f["live"]:
        raise ReportError("Учреждение не найдено или отключено", 404)
    if by["kind"] == "tg" and not access(c, by["id"], facility_id):
        raise ReportError("У вас нет прав отправлять отчёт за это учреждение", 403)
    values = _clean(c, values)
    existing = find(c, facility_id, d)
    if existing is None and by["kind"] == "tg" and dd not in allowed_dates(st):
        raise ReportError("За эту дату отчёт отправить нельзя", 422)
    res = _check(c, facility_id, d, values, lang)
    if existing is None:
        late = now_dt() > deadline(st, dd)
        cur = c.execute("INSERT INTO reports(facility_id, report_date, status, version, late, submitted_by, submitted_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                        (facility_id, d, "sent", 1, int(late), by["name"], now(), now()))
        rid = cur.lastrowid
        c.executemany("INSERT INTO report_values(report_id, code, value) VALUES (?,?,?)", [(rid, k, v) for k, v in values.items()])
        _version(c, rid, 1, "submit", by, "", values, {})
        audit(c, "report.submit", "report", rid, {"facility": facility_id, "date": d}, actor=by["name"])
        return {"id": rid, "version": 1, "late": late, "warnings": res["warnings"], "created": True}
    if by["kind"] == "tg" and not user_can_edit(existing, st):
        raise ReportError("Отчёт за эту дату уже отправлен, исправление недоступно. Обратитесь к администратору.", 409)
    return _edit(c, existing, values, by, "edit", "", res["warnings"])


def _edit(c, rep, values: dict, by: dict, action: str, reason: str, warnings: list) -> dict:
    rid = rep["id"]
    old = values_of(c, rid)
    new = dict(old) | values
    changes = {k: [old.get(k), v] for k, v in new.items() if old.get(k) != v}
    if not changes and action in ("edit", "admin_edit") and rep["status"] != "returned":
        return {"id": rid, "version": rep["version"], "late": bool(rep["late"]), "warnings": warnings, "created": False, "changed": False}
    ver = rep["version"] + 1
    c.execute("DELETE FROM report_values WHERE report_id=?", (rid,))
    c.executemany("INSERT INTO report_values(report_id, code, value) VALUES (?,?,?)", [(rid, k, v) for k, v in new.items()])
    c.execute("UPDATE reports SET version=?, corrected=1, status='sent', return_reason='', updated_at=? WHERE id=?", (ver, now(), rid))
    _version(c, rid, ver, action, by, reason, new, changes)
    audit(c, "report." + action, "report", rid, {"changes": changes, "reason": reason}, actor=by["name"])
    return {"id": rid, "version": ver, "late": bool(rep["late"]), "warnings": warnings, "created": False, "changed": True}


def admin_save(c, facility_id: int, d: str, values: dict, reason: str, by: dict, lang: str = "ru", partial: bool = False) -> dict:
    """An administrator fixes (or adds a missing) report. A reason is always required and kept."""
    if not reason.strip():
        raise ReportError("Укажите причину изменения")
    f = facility_info(c, facility_id)
    if not f:
        raise ReportError("Учреждение не найдено", 404)
    parse_date(d)
    values = _clean(c, values)
    rep = find(c, facility_id, d)
    merged = (values_of(c, rep["id"]) if rep else {}) | values
    res = _check(c, facility_id, d, merged, lang, partial)
    if rep is None:
        out = submit_new_by_admin(c, facility_id, d, merged, by, reason)
        out["warnings"] = res["warnings"]
        return out
    return _edit(c, rep, values, by, "admin_edit", reason.strip(), res["warnings"])


def submit_new_by_admin(c, facility_id, d, values, by, reason) -> dict:
    st = all_settings(c)
    late = now_dt() > deadline(st, date.fromisoformat(d))
    cur = c.execute("INSERT INTO reports(facility_id, report_date, status, version, late, submitted_by, submitted_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                    (facility_id, d, "sent", 1, int(late), by["name"], now(), now()))
    rid = cur.lastrowid
    c.executemany("INSERT INTO report_values(report_id, code, value) VALUES (?,?,?)", [(rid, k, v) for k, v in values.items()])
    _version(c, rid, 1, "submit", by, reason, values, {})
    audit(c, "report.submit_by_admin", "report", rid, {"facility": facility_id, "date": d, "reason": reason}, actor=by["name"])
    return {"id": rid, "version": 1, "late": late, "created": True}


def return_for_correction(c, report_id: int, reason: str, by: dict) -> None:
    rep = c.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
    if not rep:
        raise ReportError("Отчёт не найден", 404)
    if not reason.strip():
        raise ReportError("Укажите, что нужно исправить")
    c.execute("UPDATE reports SET status='returned', return_reason=?, locked=0, updated_at=? WHERE id=?", (reason.strip(), now(), report_id))
    _version(c, report_id, rep["version"], "return", by, reason.strip(), values_of(c, report_id), {})
    audit(c, "report.return", "report", report_id, {"reason": reason}, actor=by["name"])


def set_lock(c, report_id: int, locked: bool, by: dict, reason: str = "") -> None:
    rep = c.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
    if not rep:
        raise ReportError("Отчёт не найден", 404)
    c.execute("UPDATE reports SET locked=?, updated_at=? WHERE id=?", (int(locked), now(), report_id))
    _version(c, report_id, rep["version"], "lock" if locked else "unlock", by, reason, values_of(c, report_id), {})
    audit(c, "report.lock" if locked else "report.unlock", "report", report_id, {"reason": reason}, actor=by["name"])


def restore_version(c, report_id: int, version: int, reason: str, by: dict, lang: str = "ru") -> dict:
    """Puts the figures of an earlier version back. The restore is itself a new version: nothing is ever deleted."""
    rep = c.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
    old = c.execute("SELECT vals FROM report_versions WHERE report_id=? AND version=? AND action NOT IN ('return','lock','unlock') ORDER BY id DESC LIMIT 1", (report_id, version)).fetchone()
    if not rep or not old:
        raise ReportError("Версия не найдена", 404)
    if not reason.strip():
        raise ReportError("Укажите причину восстановления")
    vals = _clean(c, json.loads(old["vals"]))
    res = _check(c, rep["facility_id"], rep["report_date"], values_of(c, report_id) | vals, lang)
    return _edit(c, rep, vals, by, "restore", reason.strip(), res["warnings"]) | {"restored_from": version}


# ---------------------------------------------------------------- the control table (§6.3)
def control(c, user, d: str, region_id=None, district_id=None, facility_id=None, st: dict | None = None, lang: str = "ru") -> dict:
    """Every active facility with the state of its report for the date: sent / sent late / corrected / returned / not sent / overdue."""
    from . import auth
    st = st or all_settings(c)
    uz = lang == "uz"
    dd = parse_date(d)
    where, args = ["f.active=1", "d.active=1", "r.active=1"], []
    sql, a = auth.region_filter_sql(user, "r.id")
    if sql:
        where.append(sql); args += a
    for col, v in (("r.id", region_id), ("d.id", district_id), ("f.id", facility_id)):
        if v:
            where.append(f"{col}=?"); args.append(int(v))
    rows = c.execute(f"""SELECT r.id AS region_id, r.name_ru AS region, d.id AS district_id, d.name_ru AS district, f.id AS facility_id, f.name_ru AS facility,
                                rep.id AS report_id, rep.status, rep.corrected, rep.late, rep.version, rep.submitted_at, rep.locked
                         FROM facilities f JOIN districts d ON d.id=f.district_id JOIN regions r ON r.id=d.region_id
                         LEFT JOIN reports rep ON rep.facility_id=f.id AND rep.report_date=?
                         WHERE {' AND '.join(where)} ORDER BY r.sort, d.name_ru, f.name_ru""", [d] + args).fetchall()
    reg_resp: dict[int, list] = {}
    for a_ in c.execute("""SELECT ra.region_id, ra.kind, ra.fio, u.first_name, u.last_name, u.username, ra.tg_id FROM region_access ra JOIN tg_users u ON u.tg_id=ra.tg_id
                           WHERE ra.active=1 AND u.active=1"""):
        reg_resp.setdefault(a_["region_id"], []).append((a_["fio"] or " ".join(x for x in (a_["first_name"], a_["last_name"]) if x) or a_["username"] or a_["tg_id"]) + ((" (viloyat, zaxira)" if uz else " (регион, резерв)") if a_["kind"] == "reserve" else (" (viloyat)" if uz else " (регион)")))
    resp: dict[int, list] = {}
    for a_ in c.execute("""SELECT a.facility_id, a.kind, a.fio, u.first_name, u.last_name, u.username, a.tg_id FROM assignments a JOIN tg_users u ON u.tg_id=a.tg_id
                           WHERE a.active=1 AND u.active=1"""):
        resp.setdefault(a_["facility_id"], []).append((a_["fio"] or " ".join(x for x in (a_["first_name"], a_["last_name"]) if x) or a_["username"] or a_["tg_id"]) + ((" (zaxira)" if uz else " (резерв)") if a_["kind"] == "reserve" else ""))
    overdue = now_dt() > deadline(st, dd)
    out, counts = [], {"total": 0, "sent": 0, "not_sent": 0, "overdue": 0, "corrected": 0, "returned": 0, "no_responsible": 0}
    for r in rows:
        if r["report_id"]:
            status = "returned" if r["status"] == "returned" else "corrected" if r["corrected"] else "sent"
        else:
            status = "overdue" if overdue else "not_sent"
        has_resp = r["facility_id"] in resp or r["region_id"] in reg_resp
        counts["total"] += 1
        if status in ("sent", "corrected"):
            counts["sent"] += 1
            counts["corrected"] += status == "corrected"
        else:
            counts[status] += 1
        if not has_resp:
            counts["no_responsible"] += 1
        out.append({**dict(r), "state": status, "responsible": ", ".join(resp.get(r["facility_id"], []) + reg_resp.get(r["region_id"], [])), "has_responsible": has_resp, "late": bool(r["late"]),
                    "time": (r["submitted_at"] or "")[11:16]})
    counts["reported"] = counts["sent"] + counts["returned"]
    return {"date": d, "deadline": deadline(st, dd).strftime("%Y-%m-%d %H:%M"), "overdue": overdue, "counts": counts, "rows": out}
