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


_QUOTES = str.maketrans({"‘": "'", "’": "'", "ʻ": "'", "ʼ": "'", "`": "'"})     # the Uzbek o‘ g‘ ’ may be typed with any of these


def norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").translate(_QUOTES)).strip().casefold()


# ---------------------------------------------------------------- Telegram users
def touch(c, frm: dict, default_lang: str = "uz") -> dict:
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


def can_manage_region(user, region_id: int) -> bool:
    if not user:
        return False
    if auth.is_super(user):
        return True
    return user["role"] == "admin" and bool(user["can_manage_users"]) and auth.sees_region(user, region_id)


def assign_region(c, user, tg_id: str, region_id: int, kind: str = "primary", fio: str = "", contact: str = "") -> int:
    """Access to a whole region: the person may send the summary for any facility of it."""
    if kind not in ("primary", "reserve"):
        raise PeopleError("Вид назначения: основной или резервный")
    if not can_manage_region(user, region_id):
        raise PeopleError("Недостаточно прав для этого региона", 403)
    if not c.execute("SELECT 1 FROM tg_users WHERE tg_id=?", (str(tg_id),)).fetchone():
        raise PeopleError("Пользователь Telegram не найден: сначала добавьте его", 404)
    if not c.execute("SELECT 1 FROM regions WHERE id=?", (region_id,)).fetchone():
        raise PeopleError("Регион не найден", 404)
    c.execute("""INSERT INTO region_access(tg_id, region_id, kind, fio, contact, active, created_by, created_at) VALUES (?,?,?,?,?,1,?,?)
                 ON CONFLICT(tg_id, region_id) DO UPDATE SET kind=excluded.kind, fio=excluded.fio, contact=excluded.contact, active=1""",
              (str(tg_id), region_id, kind, fio.strip(), contact.strip(), user["id"], now()))
    audit(c, "region_access.set", "region", region_id, {"tg_id": str(tg_id), "kind": kind})
    return c.execute("SELECT id FROM region_access WHERE tg_id=? AND region_id=?", (str(tg_id), region_id)).fetchone()["id"]


def unassign_region(c, user, access_id: int) -> None:
    a = c.execute("SELECT * FROM region_access WHERE id=?", (access_id,)).fetchone()
    if not a:
        raise PeopleError("Назначение не найдено", 404)
    if not can_manage_region(user, a["region_id"]):
        raise PeopleError("Недостаточно прав для этого региона", 403)
    c.execute("UPDATE region_access SET active=0 WHERE id=?", (access_id,))
    audit(c, "region_access.remove", "region", a["region_id"], {"tg_id": a["tg_id"]})


def unassign(c, user, assignment_id: int) -> None:
    a = c.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone()
    if not a:
        raise PeopleError("Назначение не найдено", 404)
    if not can_manage_facility(user, c, a["facility_id"]):
        raise PeopleError("Недостаточно прав для этого учреждения", 403)
    c.execute("UPDATE assignments SET active=0 WHERE id=?", (assignment_id,))
    audit(c, "assignment.remove", "facility", a["facility_id"], {"tg_id": a["tg_id"]})


# ---------------------------------------------------------------- registered in advance by @username
USERNAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{4,31}")


def clean_username(raw) -> str:
    u = re.sub(r"^(https?://)?(t\.me|telegram\.me)/", "", str(raw or "").strip()).lstrip("@").strip().rstrip("/")
    if not USERNAME_RE.fullmatch(u):
        raise PeopleError("Имя в Telegram (@username): латиница, цифры и «_», от 5 знаков. Если у человека его нет, используйте числовой Telegram ID.")
    return u


def preapprove(c, user, raw_username, region_id: int, facility_id=None, kind: str = "primary", fio: str = "") -> dict:
    """Access by @username before the person writes to the bot: it is given at their first message. A person who is already in the bot gets it at once."""
    name = clean_username(raw_username)
    if kind not in ("primary", "reserve"):
        raise PeopleError("Вид назначения: основной или резервный")
    if facility_id:
        r = c.execute("SELECT d.region_id FROM facilities f JOIN districts d ON d.id=f.district_id WHERE f.id=?", (facility_id,)).fetchone()
        if not r:
            raise PeopleError("Учреждение не найдено", 404)
        region_id = r["region_id"]
        if not can_manage_facility(user, c, facility_id):
            raise PeopleError("Недостаточно прав для этого учреждения", 403)
    elif not can_manage_region(user, region_id):
        raise PeopleError("Недостаточно прав для этого региона", 403)
    if not c.execute("SELECT 1 FROM regions WHERE id=?", (region_id,)).fetchone():
        raise PeopleError("Регион не найден", 404)
    known = c.execute("SELECT tg_id FROM tg_users WHERE lower(username)=lower(?)", (name,)).fetchone()
    if known:                                                           # already wrote to the bot: no need to wait
        if facility_id:
            assign(c, user, known["tg_id"], facility_id, kind, fio)
        else:
            assign_region(c, user, known["tg_id"], region_id, kind, fio)
        return {"claimed": known["tg_id"]}
    c.execute("DELETE FROM preapproved WHERE lower(username)=lower(?) AND region_id=? AND ifnull(facility_id,0)=? AND used_at=''", (name, region_id, facility_id or 0))
    cur = c.execute("INSERT INTO preapproved(username, region_id, facility_id, kind, fio, created_by, created_at) VALUES (?,?,?,?,?,?,?)", (name, region_id, facility_id or None, kind, fio.strip(), user["id"], now()))
    audit(c, "preapproved.add", "region", region_id, {"username": name, "facility": facility_id, "kind": kind})
    return {"id": cur.lastrowid}


def list_preapproved(c, user) -> list[dict]:
    s, a = auth.region_filter_sql(user, "p.region_id")
    return [dict(r) for r in c.execute(f"""SELECT p.id, p.username, p.kind, p.fio, p.created_at, r.name_ru AS region, f.name_ru AS facility FROM preapproved p JOIN regions r ON r.id=p.region_id
                                          LEFT JOIN facilities f ON f.id=p.facility_id WHERE p.used_at='' {('AND ' + s) if s else ''} ORDER BY p.id DESC""", a)]


def delete_preapproved(c, user, pid: int) -> None:
    r = c.execute("SELECT * FROM preapproved WHERE id=? AND used_at=''", (pid,)).fetchone()
    if not r:
        raise PeopleError("Запись не найдена", 404)
    if not can_manage_region(user, r["region_id"]):
        raise PeopleError("Недостаточно прав для этого региона", 403)
    c.execute("DELETE FROM preapproved WHERE id=?", (pid,))
    audit(c, "preapproved.remove", "region", r["region_id"], {"username": r["username"]})


def claim_preapproved(c, tg_row) -> list[dict]:
    """The person has written to the bot: what was registered for their @username becomes their access. Returns what was given (for the welcome message)."""
    if not tg_row["username"]:
        return []
    rows = c.execute("SELECT * FROM preapproved WHERE lower(username)=lower(?) AND used_at=''", (tg_row["username"],)).fetchall()
    given = []
    for r in rows:
        who = {"id": r["created_by"], "role": "super_admin", "regions": None}          # it was the administrator's decision when it was written down
        name = r["fio"] or " ".join(x for x in (tg_row["first_name"], tg_row["last_name"]) if x)
        if r["facility_id"]:
            assign(c, who, tg_row["tg_id"], r["facility_id"], r["kind"], name)
        else:
            assign_region(c, who, tg_row["tg_id"], r["region_id"], r["kind"], name)
        c.execute("UPDATE preapproved SET used_at=?, used_tg_id=? WHERE id=?", (now(), tg_row["tg_id"], r["id"]))
        given.append({"region_id": r["region_id"], "facility_id": r["facility_id"]})
        audit(c, "preapproved.claimed", "tg_user", tg_row["tg_id"], {"username": r["username"], "region": r["region_id"], "facility": r["facility_id"]}, actor="telegram " + str(tg_row["tg_id"]))
    return given


# ---------------------------------------------------------------- requests for access
def create_request(c, tg_id: str, region_id: int, district_id: int | None = None) -> int:
    """A request for access to a region. The district, if given, only tells the administrator where the person works."""
    r = c.execute("SELECT id FROM regions WHERE id=? AND active=1", (region_id,)).fetchone()
    if not r:
        raise PeopleError("Регион не найден или отключён", 404)
    if district_id and not c.execute("SELECT 1 FROM districts WHERE id=? AND region_id=? AND active=1", (district_id, region_id)).fetchone():
        district_id = None
    if c.execute("SELECT 1 FROM region_access WHERE tg_id=? AND region_id=? AND active=1", (str(tg_id), region_id)).fetchone():
        raise PeopleError("У вас уже есть доступ к этому региону")
    if c.execute("SELECT 1 FROM access_requests WHERE tg_id=? AND region_id=? AND facility_id IS NULL AND status='pending'", (str(tg_id), region_id)).fetchone():
        raise PeopleError("Запрос на этот регион уже ожидает рассмотрения")
    cur = c.execute("INSERT INTO access_requests(tg_id, region_id, district_id, facility_id, created_at) VALUES (?,?,?,NULL,?)", (str(tg_id), region_id, district_id, now()))
    audit(c, "request.create", "request", cur.lastrowid, {"tg_id": str(tg_id), "region": region_id}, actor="telegram " + str(tg_id))
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
    by_facility = q["facility_id"] is not None
    if not (can_manage_facility(user, c, q["facility_id"]) if by_facility else can_manage_region(user, q["region_id"])):
        raise PeopleError("Недостаточно прав для этого региона", 403)
    if approve:
        u = c.execute("SELECT * FROM tg_users WHERE tg_id=?", (q["tg_id"],)).fetchone()
        name = fio or " ".join(x for x in (u["first_name"], u["last_name"]) if x)
        if by_facility:
            assign(c, user, q["tg_id"], q["facility_id"], kind, name)
        else:
            assign_region(c, user, q["tg_id"], q["region_id"], kind, name)
    c.execute("UPDATE access_requests SET status=?, decided_by=?, decided_at=?, note=? WHERE id=?", ("approved" if approve else "rejected", user["id"], now(), note.strip(), request_id))
    audit(c, "request.approve" if approve else "request.reject", "request", request_id, {"tg_id": q["tg_id"], "facility": q["facility_id"], "note": note})
    return {"tg_id": q["tg_id"], "facility_id": q["facility_id"], "region_id": q["region_id"], "approved": approve, "note": note}


# ---------------------------------------------------------------- import of territories from Excel / CSV
HEAD = {"регион": "region", "вилоят": "region", "район": "district", "туман": "district", "учреждение": "facility", "муассаса": "facility",
        "район (узб)": "district_uz", "учреждение (узб)": "facility_uz", "название района (узб)": "district_uz", "название учреждения (узб)": "facility_uz",
        # the same headers in Uzbek (Latin), as the interface now writes them
        "viloyat": "region", "tuman": "district", "muassasa": "facility", "tuman (uz)": "district_uz", "muassasa (uz)": "facility_uz", "tuman nomi (uz)": "district_uz", "muassasa nomi (uz)": "facility_uz"}


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
