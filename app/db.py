"""SQLite storage (WAL): territories, staff, Telegram users and their assignments, access requests, configurable
indicators and validation rules, reports with immutable versions, settings, audit log.

What the database itself enforces, because the technical requirements ask for it: report versions and the audit
log are append-only (§11), one report per facility and date (§4.5, §13.3)."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))
DB_PATH = os.path.join(DATA_DIR, "flu.db")
TZ = timezone(timedelta(hours=5))   # Asia/Tashkent has no daylight saving time


def now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def today() -> date:
    """Today in Tashkent. FLU_TODAY=YYYY-MM-DD pins the date (tests, demos)."""
    pinned = os.environ.get("FLU_TODAY")
    return date.fromisoformat(pinned) if pinned else datetime.now(TZ).date()


def now_dt() -> datetime:
    """The current moment in Tashkent; with FLU_TODAY pinned, that day at the time FLU_NOW (default 12:00)."""
    pinned = os.environ.get("FLU_TODAY")
    if pinned:
        hh, mm = (os.environ.get("FLU_NOW", "12:00").split(":") + ["0"])[:2]
        return datetime.fromisoformat(pinned).replace(hour=int(hh), minute=int(mm), tzinfo=TZ)
    return datetime.now(TZ)


TABLES = """
CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY,
    login TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('super_admin','admin','viewer')),
    active INTEGER NOT NULL DEFAULT 1,
    tg_id TEXT NOT NULL DEFAULT '',
    can_manage_users INTEGER NOT NULL DEFAULT 0,
    can_edit_reports INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS staff_scope (staff_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE CASCADE, region_id INTEGER NOT NULL, PRIMARY KEY (staff_id, region_id));
CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, staff_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE CASCADE, expires_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS regions (id INTEGER PRIMARY KEY, name_ru TEXT NOT NULL, name_uz TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS districts (id INTEGER PRIMARY KEY, region_id INTEGER NOT NULL REFERENCES regions(id), name_ru TEXT NOT NULL, name_uz TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS facilities (
    id INTEGER PRIMARY KEY,
    district_id INTEGER NOT NULL REFERENCES districts(id),
    name_ru TEXT NOT NULL, name_uz TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    contact TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS tg_users (
    tg_id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL DEFAULT '', last_name TEXT NOT NULL DEFAULT '', username TEXT NOT NULL DEFAULT '',
    lang TEXT NOT NULL DEFAULT 'ru',
    phone TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT '', last_seen TEXT NOT NULL DEFAULT ''
);
-- who may report for which facility: the primary responsible person and, if the administrator wishes, a reserve one
CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY,
    tg_id TEXT NOT NULL REFERENCES tg_users(tg_id),
    facility_id INTEGER NOT NULL REFERENCES facilities(id),
    kind TEXT NOT NULL DEFAULT 'primary' CHECK (kind IN ('primary','reserve')),
    fio TEXT NOT NULL DEFAULT '', contact TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER, created_at TEXT NOT NULL DEFAULT '',
    UNIQUE (tg_id, facility_id)
);
-- access to a whole region: the person reports for any facility of it (any district)
CREATE TABLE IF NOT EXISTS region_access (
    id INTEGER PRIMARY KEY,
    tg_id TEXT NOT NULL REFERENCES tg_users(tg_id),
    region_id INTEGER NOT NULL REFERENCES regions(id),
    kind TEXT NOT NULL DEFAULT 'primary' CHECK (kind IN ('primary','reserve')),
    fio TEXT NOT NULL DEFAULT '', contact TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER, created_at TEXT NOT NULL DEFAULT '',
    UNIQUE (tg_id, region_id)
);
CREATE TABLE IF NOT EXISTS access_requests (
    id INTEGER PRIMARY KEY,
    tg_id TEXT NOT NULL REFERENCES tg_users(tg_id),
    region_id INTEGER, district_id INTEGER, facility_id INTEGER REFERENCES facilities(id),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    created_at TEXT NOT NULL, decided_by INTEGER, decided_at TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT ''
);

-- the list of reported figures is data, not code (§5.5)
CREATE TABLE IF NOT EXISTS indicators (
    code TEXT PRIMARY KEY,
    grp TEXT NOT NULL DEFAULT 'extra',
    name_ru TEXT NOT NULL, name_uz TEXT NOT NULL DEFAULT '',
    hint_ru TEXT NOT NULL DEFAULT '', hint_uz TEXT NOT NULL DEFAULT '',
    agg TEXT NOT NULL DEFAULT 'sum' CHECK (agg IN ('sum','last','max')),
    sort INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    core INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL DEFAULT 'error' CHECK (kind IN ('error','warning')),
    expr TEXT NOT NULL,
    message_ru TEXT NOT NULL, message_uz TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0, core INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY,
    facility_id INTEGER NOT NULL REFERENCES facilities(id),
    report_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'sent' CHECK (status IN ('sent','returned')),
    version INTEGER NOT NULL DEFAULT 1,
    corrected INTEGER NOT NULL DEFAULT 0,
    locked INTEGER NOT NULL DEFAULT 0,
    late INTEGER NOT NULL DEFAULT 0,
    submitted_by TEXT NOT NULL DEFAULT '',
    submitted_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    return_reason TEXT NOT NULL DEFAULT '',
    UNIQUE (facility_id, report_date)
);
CREATE TABLE IF NOT EXISTS report_values (report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE, code TEXT NOT NULL, value INTEGER NOT NULL, PRIMARY KEY (report_id, code));
CREATE TABLE IF NOT EXISTS report_versions (
    id INTEGER PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES reports(id),
    version INTEGER NOT NULL,
    action TEXT NOT NULL,
    by_kind TEXT NOT NULL DEFAULT 'system',
    by_id TEXT NOT NULL DEFAULT '',
    by_name TEXT NOT NULL DEFAULT '',
    at TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    vals TEXT NOT NULL DEFAULT '{}',
    changes TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notify_log (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, tg_id TEXT NOT NULL DEFAULT '', day TEXT NOT NULL DEFAULT '', slot TEXT NOT NULL DEFAULT '',
    ok INTEGER NOT NULL DEFAULT 1, detail TEXT NOT NULL DEFAULT '', at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bot_state (tg_id TEXT PRIMARY KEY, state TEXT NOT NULL DEFAULT '', data TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY, staff_id INTEGER, actor TEXT NOT NULL DEFAULT '', action TEXT NOT NULL, entity TEXT NOT NULL DEFAULT '', entity_id TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT '{}', ip TEXT NOT NULL DEFAULT '', at TEXT NOT NULL
);
"""
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_reports_date ON reports(report_date);
CREATE INDEX IF NOT EXISTS idx_reports_fac ON reports(facility_id, report_date);
CREATE INDEX IF NOT EXISTS idx_vals_report ON report_values(report_id);
CREATE INDEX IF NOT EXISTS idx_fac_district ON facilities(district_id);
CREATE INDEX IF NOT EXISTS idx_dist_region ON districts(region_id);
CREATE INDEX IF NOT EXISTS idx_assign_fac ON assignments(facility_id);
CREATE INDEX IF NOT EXISTS idx_regacc_tg ON region_access(tg_id);
CREATE INDEX IF NOT EXISTS idx_versions_report ON report_versions(report_id, id);
CREATE INDEX IF NOT EXISTS idx_notify ON notify_log(kind, day, tg_id, slot);
"""
TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS versions_no_update BEFORE UPDATE ON report_versions BEGIN SELECT RAISE(ABORT, 'История версий неизменяема'); END;
CREATE TRIGGER IF NOT EXISTS versions_no_delete BEFORE DELETE ON report_versions BEGIN SELECT RAISE(ABORT, 'История версий неизменяема'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT, 'Журнал неизменяем'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT, 'Журнал неизменяем'); END;
"""

REGIONS = [("Республика Каракалпакстан", "Қорақалпоғистон Республикаси"), ("Андижанская область", "Андижон вилояти"), ("Бухарская область", "Бухоро вилояти"),
           ("Джизакская область", "Жиззах вилояти"), ("Кашкадарьинская область", "Қашқадарё вилояти"), ("Навоийская область", "Навоий вилояти"),
           ("Наманганская область", "Наманган вилояти"), ("Самаркандская область", "Самарқанд вилояти"), ("Сурхандарьинская область", "Сурхондарё вилояти"),
           ("Сырдарьинская область", "Сирдарё вилояти"), ("Ташкентская область", "Тошкент вилояти"), ("Ферганская область", "Фарғона вилояти"),
           ("Хорезмская область", "Хоразм вилояти"), ("город Ташкент", "Тошкент шаҳри")]

# code, group, name_ru, name_uz, aggregation (sum = a flow added over days, last = a state taken on the latest day)
INDICATORS = [
    ("beds_total", "beds", "Общее количество коек", "Жами ўринлар сони", "last"),
    ("beds_flu", "beds", "Из них выделено для больных гриппом", "Шундан грипп беморлари учун ажратилган", "last"),
    ("beds_occupied", "beds", "Занято коек для больных гриппом на конец отчётного дня", "Ҳисобот куни охирида грипп беморлари билан банд ўринлар", "last"),
    ("visits", "visits", "Общее количество обращений", "Мурожаатлар умумий сони", "sum"),
    ("severe", "visits", "Количество пациентов в тяжёлом состоянии", "Оғир аҳволдаги беморлар сони", "last"),
    ("severe_pregnant", "visits", "Из них беременные в тяжёлом состоянии", "Шундан оғир аҳволдаги ҳомиладорлар", "last"),
    ("severe_children", "visits", "Из них дети в тяжёлом состоянии", "Шундан оғир аҳволдаги болалар", "last"),
    ("extreme", "visits", "Количество пациентов в крайне тяжёлом состоянии", "Ўта оғир аҳволдаги беморлар сони", "last"),
    ("extreme_pregnant", "visits", "Из них беременные в крайне тяжёлом состоянии", "Шундан ўта оғир аҳволдаги ҳомиладорлар", "last"),
    ("extreme_children", "visits", "Из них дети в крайне тяжёлом состоянии", "Шундан ўта оғир аҳволдаги болалар", "last"),
    ("hosp", "hosp", "Количество госпитализаций за отчётный день", "Ҳисобот куни ётқизилганлар сони", "sum"),
    ("disch", "hosp", "Количество выписанных пациентов за отчётный день", "Ҳисобот куни чиқарилганлар сони", "sum"),
]
# kind, expression, message (a {code} is replaced by the entered value)
RULES = [
    ("error", "beds_flu <= beds_total", "Коек для больных гриппом ({beds_flu}) больше общего числа коек ({beds_total}).", "Грипп учун ажратилган ўринлар ({beds_flu}) жами ўринлардан ({beds_total}) кўп."),
    ("error", "beds_occupied <= beds_flu", "Занятых коек ({beds_occupied}) больше, чем выделено для гриппа ({beds_flu}).", "Банд ўринлар ({beds_occupied}) грипп учун ажратилганлардан ({beds_flu}) кўп."),
    ("error", "severe <= visits", "Тяжёлых пациентов ({severe}) больше, чем обращений ({visits}).", "Оғир беморлар ({severe}) мурожаатлардан ({visits}) кўп."),
    ("error", "extreme <= visits", "Крайне тяжёлых пациентов ({extreme}) больше, чем обращений ({visits}).", "Ўта оғир беморлар ({extreme}) мурожаатлардан ({visits}) кўп."),
    ("error", "severe_pregnant <= severe", "Беременных в тяжёлом состоянии ({severe_pregnant}) больше, чем тяжёлых пациентов ({severe}).", "Оғир аҳволдаги ҳомиладорлар ({severe_pregnant}) оғир беморлардан ({severe}) кўп."),
    ("error", "severe_children <= severe", "Детей в тяжёлом состоянии ({severe_children}) больше, чем тяжёлых пациентов ({severe}).", "Оғир аҳволдаги болалар ({severe_children}) оғир беморлардан ({severe}) кўп."),
    ("error", "extreme_pregnant <= extreme", "Беременных в крайне тяжёлом состоянии ({extreme_pregnant}) больше, чем крайне тяжёлых ({extreme}).", "Ўта оғир аҳволдаги ҳомиладорлар ({extreme_pregnant}) ўта оғир беморлардан ({extreme}) кўп."),
    ("error", "extreme_children <= extreme", "Детей в крайне тяжёлом состоянии ({extreme_children}) больше, чем крайне тяжёлых ({extreme}).", "Ўта оғир аҳволдаги болалар ({extreme_children}) ўта оғир беморлардан ({extreme}) кўп."),
    ("warning", "hosp <= visits", "Госпитализаций ({hosp}) больше, чем обращений ({visits}). Проверьте данные.", "Ётқизилганлар ({hosp}) мурожаатлардан ({visits}) кўп. Маълумотларни текширинг."),
    ("warning", "disch <= beds_occupied + hosp", "Выписано ({disch}) больше, чем было занято и поступило ({beds_occupied} + {hosp}). Проверьте данные.", "Чиқарилганлар ({disch}) банд ва ётқизилганлардан ({beds_occupied} + {hosp}) кўп. Маълумотларни текширинг."),
    ("warning", "severe + extreme <= visits", "Тяжёлых и крайне тяжёлых вместе ({severe} + {extreme}) больше, чем обращений ({visits}).", "Оғир ва ўта оғир беморлар биргаликда ({severe} + {extreme}) мурожаатлардан ({visits}) кўп."),
]
SETTINGS = {
    "deadline_time": "18:00", "deadline_day_offset": "0", "backfill_days": "2",
    "remind_enabled": "1", "remind_times": "15:00,17:30", "remind_weekdays": "1,2,3,4,5,6,7", "admin_summary_time": "18:30", "admin_overdue_time": "20:00",
    "allow_user_edit": "1", "edit_window_hours": "24", "lock_after_days": "3",
    "occ_elevated": "70", "occ_critical": "85", "fac_occ_warn": "90",
    "growth_warn_pct": "30", "growth_crit_pct": "60", "severe_growth_pct": "25", "hosp_growth_pct": "30",
    "default_lang": "ru", "org_title": "Министерство здравоохранения Республики Узбекистан",
}


def connect() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    return c


@contextmanager
def tx():
    c = connect()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init_db() -> None:
    from . import auth

    with tx() as c:
        c.executescript(TABLES)
        c.executescript(INDEXES)
        c.executescript(TRIGGERS)
        if not c.execute("SELECT 1 FROM regions LIMIT 1").fetchone():
            for i, (ru, uz) in enumerate(REGIONS, 1):
                c.execute("INSERT INTO regions(id, name_ru, name_uz, sort) VALUES (?,?,?,?)", (i, ru, uz, i))
        if not c.execute("SELECT 1 FROM indicators LIMIT 1").fetchone():
            for i, (code, grp, ru, uz, agg) in enumerate(INDICATORS, 1):
                c.execute("INSERT INTO indicators(code, grp, name_ru, name_uz, agg, sort, core) VALUES (?,?,?,?,?,?,1)", (code, grp, ru, uz, agg, i))
        if not c.execute("SELECT 1 FROM rules LIMIT 1").fetchone():
            for i, (kind, expr, ru, uz) in enumerate(RULES, 1):
                c.execute("INSERT INTO rules(kind, expr, message_ru, message_uz, sort, core) VALUES (?,?,?,?,?,1)", (kind, expr, ru, uz, i))
        for k, v in SETTINGS.items():
            c.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?,?)", (k, v))
        auth.ensure_admin(c)


def all_settings(c=None) -> dict:
    own = c is None
    c = c or connect()
    try:
        out = dict(SETTINGS)
        out.update({r["key"]: r["value"] for r in c.execute("SELECT key, value FROM settings")})
        return out
    finally:
        if own:
            c.close()


def audit(c, action: str, entity: str = "", entity_id="", details: dict | None = None, actor: str = "") -> None:
    from . import auth

    u = auth.CURRENT.get()
    c.execute("INSERT INTO audit(staff_id, actor, action, entity, entity_id, details, ip, at) VALUES (?,?,?,?,?,?,?,?)",
              (u["id"] if u else None, actor or (u["name"] or u["login"] if u else "система"), action, entity, str(entity_id),
               json.dumps(details or {}, ensure_ascii=False), auth.CURRENT_IP.get(), now()))
