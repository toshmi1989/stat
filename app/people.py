"""Territories (import), Telegram users, who is responsible for which facility, and the requests for access (§2, §3, §4.2)."""
import csv
import io
import re

import openpyxl

from . import auth
from .db import audit, now


class PeopleError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message, self.status = message, status


def norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().casefold()


# ---------------------------------------------------------------- Telegram users
def touch(c, frm: dict, default_lang: str = "ru") -> dict:
    """Creates or updates the person that wrote to the bot from what Telegram tells us (id, name, username)."""
    tid = str(frm["id"])
    row = c.execute("SELECT * FROM tg_users WHERE tg_id=?", (tid,)).fetchone()
    if row is None:
        c.execute("INSERT INTO tg_users(tg_id, first_name, last_name, username, lang, created_at, last_seen) VALUES (?,?,?,?,?,?,?)",
                  (tid, frm.get("first_name", ""), frm.get("last_name", ""), frm.get("username", ""), default_lang, now(), now()))
    else:
        c.execute("UPDATE tg_users SET first_name=?, last_name=?, username=?, last_seen=? WHERE tg_id=?", (frm.get("first_name", ""), frm.get("last_name", ""), frm.get("username", ""), now(), tid))
    return c.execute("SELECT * FROM tg_users WHERE tg_id=?", (tid,)).fetchone()


def add_tg_user(c, tg_id: str, name: str = "", by=None) -> None:
    """The administrator adds a person by their Telegram id without waiting for a request."""
    tg_id = str(tg_id).strip()
    if not re.fullmatch(r"\d{4,15}", tg_id):
        raise PeopleError("Telegram ID — это число (его показывает бот @userinfobot)")
    parts = name.strip().split(" ", 1)
    if c.execute("SELECT 1 FROM tg_users WHERE tg_id=?", (tg_id,)).fetchone():
        if name.strip():
            c.execute("UPDATE tg_users SET first_name=?, last_name=? WHERE tg_id=?", (parts[0], parts[1] if len(parts) > 1 else "", tg_id))
        return
    c.execute("INSERT INTO tg_users(tg_id, first_name, last_name, created_at) VALUES (?,?,?,?)", (tg_id, parts[0], parts[1] if len(parts) > 1 else "", now()))
    audit(c, "tguser.add", "tg_user", tg_id, {"name": name})


# ---------------------------------------------------------------- assignments
def can_manage_facility(user, c, facility_id: int) -> bool:
    if not user:
        return False
    if auth.is_super(user):
        return True
    if user["role"] != "admin" or not user["can_manage_users"]:
        return False
    r = c.execute("SELECT d.region_id FROM facilities f JOIN districts d ON d.id=f.district_id WHERE f.id=?", (facility_id,)).fetchone()
    return bool(r) and auth.sees_region(user, r["region_id"])


def assign(c, user, tg_id: str, facility_id: int, kind: str = "primary", fio: str = "", contact: str = "") -> int:
    """Makes the person responsible for the facility. A new primary person replaces the previous primary one; reserves add up."""
    if kind not in ("primary", "reserve"):
        raise PeopleError("Вид назначения: основной или резервный")
    if not can_manage_facility(user, c, facility_id):
        raise PeopleError("Недостаточно прав для этого учреждения", 403)
    if not c.execute("SELECT 1 FROM tg_users WHERE tg_id=?", (str(tg_id),)).fetchone():
        raise PeopleError("Пользователь Telegram не найден: сначала добавьте его", 404)
    if not c.execute("SELECT 1 FROM facilities WHERE id=?", (facility_id,)).fetchone():
        raise PeopleError("Учреждение не найдено", 404)
    if kind == "primary":
        c.execute("UPDATE assignments SET active=0 WHERE facility_id=? AND kind='primary' AND tg_id != ? AND active=1", (facility_id, str(tg_id)))
    c.execute("""INSERT INTO assignments(tg_id, facility_id, kind, fio, contact, active, created_by, created_at) VALUES (?,?,?,?,?,1,?,?)
                 ON CONFLICT(tg_id, facility_id) DO UPDATE SET kind=excluded.kind, fio=excluded.fio, contact=excluded.contact, active=1""",
              (str(tg_id), facility_id, kind, fio.strip(), contact.strip(), user["id"], now()))
    audit(c, "assignment.set", "facility", facility_id, {"tg_id": str(tg_id), "kind": kind})
    return c.execute("SELECT id FROM assignments WHERE tg_id=? AND facility_id=?", (str(tg_id), facility_id)).fetchone()["id"]


def unassign(c, user, assignment_id: int) -> None:
    a = c.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone()
    if not a:
        raise PeopleError("Назначение не найдено", 404)
    if not can_manage_facility(user, c, a["facility_id"]):
        raise PeopleError("Недостаточно прав для этого учреждения", 403)
    c.execute("UPDATE assignments SET active=0 WHERE id=?", (assignment_id,))
    audit(c, "assignment.remove", "facility", a["facility_id"], {"tg_id": a["tg_id"]})


# ---------------------------------------------------------------- requests for access
def create_request(c, tg_id: str, facility_id: int) -> int:
    f = c.execute("""SELECT f.id, d.id AS did, r.id AS rid FROM facilities f JOIN districts d ON d.id=f.district_id JOIN regions r ON r.id=d.region_id
                     WHERE f.id=? AND f.active=1 AND d.active=1 AND r.active=1""", (facility_id,)).fetchone()
    if not f:
        raise PeopleError("Учреждение не найдено или отключено", 404)
    if c.execute("SELECT 1 FROM assignments WHERE tg_id=? AND facility_id=? AND active=1", (str(tg_id), facility_id)).fetchone():
        raise PeopleError("У вас уже есть доступ к этому учреждению")
    if c.execute("SELECT 1 FROM access_requests WHERE tg_id=? AND facility_id=? AND status='pending'", (str(tg_id), facility_id)).fetchone():
        raise PeopleError("Запрос на это учреждение уже ожидает рассмотрения")
    cur = c.execute("INSERT INTO access_requests(tg_id, region_id, district_id, facility_id, created_at) VALUES (?,?,?,?,?)", (str(tg_id), f["rid"], f["did"], facility_id, now()))
    audit(c, "request.create", "request", cur.lastrowid, {"tg_id": str(tg_id), "facility": facility_id}, actor="telegram " + str(tg_id))
    return cur.lastrowid


def list_requests(c, user, status: str | None = None) -> list[dict]:
    sql = """SELECT q.*, u.first_name, u.last_name, u.username, r.name_ru AS region, d.name_ru AS district, f.name_ru AS facility
             FROM access_requests q JOIN tg_users u ON u.tg_id=q.tg_id LEFT JOIN regions r ON r.id=q.region_id LEFT JOIN districts d ON d.id=q.district_id LEFT JOIN facilities f ON f.id=q.facility_id"""
    where, args = [], []
    if status:
        where.append("q.status=?"); args.append(status)
    s, a = auth.region_filter_sql(user, "q.region_id")
    if s:
        where.append(s); args += a
    rows = c.execute(sql + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY (q.status='pending') DESC, q.id DESC LIMIT 500", args).fetchall()
    return [dict(r) for r in rows]


def decide(c, user, request_id: int, approve: bool, kind: str = "primary", fio: str = "", note: str = "") -> dict:
    q = c.execute("SELECT * FROM access_requests WHERE id=?", (request_id,)).fetchone()
    if not q:
        raise PeopleError("Запрос не найден", 404)
    if q["status"] != "pending":
        raise PeopleError("Запрос уже рассмотрен")
    if not can_manage_facility(user, c, q["facility_id"]):
        raise PeopleError("Недостаточно прав для этого учреждения", 403)
    if approve:
        u = c.execute("SELECT * FROM tg_users WHERE tg_id=?", (q["tg_id"],)).fetchone()
        assign(c, user, q["tg_id"], q["facility_id"], kind, fio or " ".join(x for x in (u["first_name"], u["last_name"]) if x))
    c.execute("UPDATE access_requests SET status=?, decided_by=?, decided_at=?, note=? WHERE id=?", ("approved" if approve else "rejected", user["id"], now(), note.strip(), request_id))
    audit(c, "request.approve" if approve else "request.reject", "request", request_id, {"tg_id": q["tg_id"], "facility": q["facility_id"], "note": note})
    return {"tg_id": q["tg_id"], "facility_id": q["facility_id"], "approved": approve, "note": note}


# ---------------------------------------------------------------- import of territories from Excel / CSV
HEAD = {"регион": "region", "вилоят": "region", "район": "district", "туман": "district", "учреждение": "facility", "муассаса": "facility",
        "район (узб)": "district_uz", "учреждение (узб)": "facility_uz", "название района (узб)": "district_uz", "название учреждения (узб)": "facility_uz"}


def read_table(data: bytes, filename: str) -> list[list]:
    if filename.lower().endswith(".csv"):
        text = data.decode("utf-8-sig", errors="replace")
        dialect = csv.Sniffer().sniff(text[:2000], delimiters=";,\t") if text.strip() else csv.excel
        return [row for row in csv.reader(io.StringIO(text), dialect)]
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise PeopleError("Файл не читается: нужен Excel (.xlsx) или CSV")
    return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]


def import_territories(c, data: bytes, filename: str, dry: bool, user) -> dict:
    """Region | District | Facility (| district Uz | facility Uz). Existing rows are matched by name and kept; the rest is created."""
    table = read_table(data, filename)
    head, cols = None, {}
    for i, row in enumerate(table[:10]):
        m = {HEAD[norm(v)]: j for j, v in enumerate(row) if v is not None and norm(v) in HEAD}
        if {"region", "district"} <= set(m):
            head, cols = i, m
            break
    if head is None:
        raise PeopleError("Не нашёл заголовок: нужны колонки «Регион» и «Район» (и, по желанию, «Учреждение»)")
    regions = {norm(r["name_ru"]): r["id"] for r in c.execute("SELECT id, name_ru FROM regions")}
    regions.update({norm(r["name_uz"]): r["id"] for r in c.execute("SELECT id, name_uz FROM regions") if r["name_uz"]})
    dist = {(r["region_id"], norm(r["name_ru"])): r["id"] for r in c.execute("SELECT id, region_id, name_ru FROM districts")}
    fac = {(r["district_id"], norm(r["name_ru"])): r["id"] for r in c.execute("SELECT id, district_id, name_ru FROM facilities")}
    new_d, new_f, errors = 0, 0, []
    for n, row in enumerate(table[head + 1:], head + 2):
        def cell(k):
            j = cols.get(k)
            return str(row[j]).strip() if j is not None and j < len(row) and row[j] is not None else ""
        if not any(cell(k) for k in ("region", "district", "facility")):
            continue
        rid = regions.get(norm(cell("region")))
        if not rid:
            errors.append(f"строка {n}: неизвестный регион «{cell('region')}»")
            continue
        if not auth.sees_region(user, rid):
            errors.append(f"строка {n}: нет доступа к региону «{cell('region')}»")
            continue
        if not cell("district"):
            errors.append(f"строка {n}: не указан район")
            continue
        key = (rid, norm(cell("district")))
        did = dist.get(key)
        if did is None:
            new_d += 1
            if not dry:
                did = c.execute("INSERT INTO districts(region_id, name_ru, name_uz) VALUES (?,?,?)", (rid, cell("district"), cell("district_uz"))).lastrowid
            else:
                did = -new_d
            dist[key] = did
        if cell("facility"):
            fkey = (did, norm(cell("facility")))
            if fkey not in fac:
                new_f += 1
                if not dry:
                    fac[fkey] = c.execute("INSERT INTO facilities(district_id, name_ru, name_uz, created_at) VALUES (?,?,?,?)", (did, cell("facility"), cell("facility_uz"), now())).lastrowid
                else:
                    fac[fkey] = -new_f
    if not dry:
        audit(c, "territory.import", "territory", "", {"file": filename[:100], "districts": new_d, "facilities": new_f})
    return {"districts": new_d, "facilities": new_f, "errors": errors[:50], "errors_total": len(errors), "dry": dry}
