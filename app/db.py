"""SQLite storage (WAL): territories, staff, Telegram users and their assignments, access requests, configurable
indicators and validation rules, reports with immutable versions, settings, audit log.

What the database itself enforces, because the technical requirements ask for it: report versions and the audit
log are append-only (§11), one report per facility and date (§4.5, §13.3)."""
import contextlib
import json
import os
import sqlite3
from contextlib import contextmanager
from .translit import lat
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
    can_manage_territories INTEGER NOT NULL DEFAULT 0,
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

-- the head of the health department of a region (and a reserve one): full name and phone, like the responsible person of a facility
CREATE TABLE IF NOT EXISTS region_contacts (
    id INTEGER PRIMARY KEY,
    region_id INTEGER NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'main',
    fio TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT ''
);
-- the person responsible for a facility (the head physician or whoever the administrator names): full name and phone, whether or not he is already in the bot
CREATE TABLE IF NOT EXISTS facility_contacts (
    id INTEGER PRIMARY KEY,
    facility_id INTEGER NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'main',                        -- main | reserve
    fio TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '',   -- phone: digits only, 998XXXXXXXXX (several numbers: separated by a comma)
    created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT ''
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
-- people the administrator registered by @username before they ever wrote to the bot: the access is given when they do
CREATE TABLE IF NOT EXISTS preapproved (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    region_id INTEGER NOT NULL REFERENCES regions(id),
    facility_id INTEGER REFERENCES facilities(id),
    kind TEXT NOT NULL DEFAULT 'primary', fio TEXT NOT NULL DEFAULT '',
    created_by INTEGER, created_at TEXT NOT NULL,
    used_at TEXT NOT NULL DEFAULT '', used_tg_id TEXT NOT NULL DEFAULT ''
);
-- the last, optional question of the bot: a confidential message for the Ministry of Health. Only the super administrator reads it (never regional staff), it is not part of
-- the report, not in exports and not in the audit log.
CREATE TABLE IF NOT EXISTS ministry_messages (
    id INTEGER PRIMARY KEY,
    facility_id INTEGER NOT NULL REFERENCES facilities(id),
    report_date TEXT NOT NULL,
    tg_id TEXT NOT NULL, sender TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL, created_at TEXT NOT NULL,
    read_at TEXT NOT NULL DEFAULT '', read_by INTEGER,
    thread_id INTEGER, direction TEXT NOT NULL DEFAULT 'in', staff_id INTEGER, error TEXT NOT NULL DEFAULT ''
);
-- proposals of the people of the bot to add or to remove a facility; nothing changes until a person with the section «Территории» of that region decides on the site
CREATE TABLE IF NOT EXISTS facility_proposals (
    id INTEGER PRIMARY KEY,
    region_id INTEGER NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,                                       -- add | remove
    name TEXT NOT NULL,                                       -- the proposed name (add) or the name of the facility when it was proposed (remove)
    facility_id INTEGER,                                      -- remove: the facility; add: the facility created when the proposal was accepted
    comment TEXT NOT NULL DEFAULT '',
    tg_id TEXT NOT NULL, created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',                       -- new | done | rejected
    handled_by INTEGER, handled_at TEXT NOT NULL DEFAULT '', handled_comment TEXT NOT NULL DEFAULT ''
);
-- broadcasts written on the site and sent to the people of the bot; one log row per recipient
CREATE TABLE IF NOT EXISTS broadcasts (
    id INTEGER PRIMARY KEY, created_by INTEGER, created_at TEXT NOT NULL,
    text_ru TEXT NOT NULL DEFAULT '', text_uz TEXT NOT NULL DEFAULT '', audience TEXT NOT NULL DEFAULT '{}',
    total INTEGER NOT NULL DEFAULT 0, sent INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'sending', finished_at TEXT NOT NULL DEFAULT '', heartbeat TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS broadcast_log (
    broadcast_id INTEGER NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE, tg_id TEXT NOT NULL, lang TEXT NOT NULL DEFAULT 'uz',
    status TEXT NOT NULL DEFAULT 'queued', error TEXT NOT NULL DEFAULT '', at TEXT NOT NULL DEFAULT '', PRIMARY KEY (broadcast_id, tg_id)
);
-- texts of broadcasts that people saved to use again (with the audience they were written for); the ready-made ones live in the code (app/broadcast.py)
CREATE TABLE IF NOT EXISTS broadcast_templates (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, text_ru TEXT NOT NULL DEFAULT '', text_uz TEXT NOT NULL DEFAULT '', audience TEXT NOT NULL DEFAULT '{}',
    created_by INTEGER, created_at TEXT NOT NULL
);
-- broadcasts that go by themselves: once, every day or on weekdays at a time; the audience and the figures in the text are taken at the moment of sending
CREATE TABLE IF NOT EXISTS broadcast_schedules (
    id INTEGER PRIMARY KEY, title TEXT NOT NULL DEFAULT '', created_by INTEGER, created_at TEXT NOT NULL,
    audience TEXT NOT NULL DEFAULT '{}', text_ru TEXT NOT NULL DEFAULT '', text_uz TEXT NOT NULL DEFAULT '',
    repeat TEXT NOT NULL DEFAULT 'once', at_time TEXT NOT NULL DEFAULT '18:00', run_date TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1, last_run_date TEXT NOT NULL DEFAULT '', last_broadcast_id INTEGER, last_result TEXT NOT NULL DEFAULT ''
);
-- profile photos fetched from Telegram (the bot token never leaves the server): found=0 means the person has none or hides it
CREATE TABLE IF NOT EXISTS tg_avatars (tg_id TEXT PRIMARY KEY, data BLOB, fetched_at TEXT NOT NULL, found INTEGER NOT NULL DEFAULT 0);
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
    core INTEGER NOT NULL DEFAULT 0,
    required INTEGER NOT NULL DEFAULT 1,
    parent_code TEXT NOT NULL DEFAULT ''                      -- «of them»: the question this one is an addition to (its answer cannot be larger); shown with it in the bot
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
CREATE UNIQUE INDEX IF NOT EXISTS idx_preapp ON preapproved(username, region_id, ifnull(facility_id, 0)) WHERE used_at = '';
CREATE INDEX IF NOT EXISTS idx_assign_fac ON assignments(facility_id);
CREATE INDEX IF NOT EXISTS idx_regacc_tg ON region_access(tg_id);
CREATE INDEX IF NOT EXISTS idx_versions_report ON report_versions(report_id, id);
CREATE INDEX IF NOT EXISTS idx_rcontacts ON region_contacts(region_id);
CREATE INDEX IF NOT EXISTS idx_fcontacts ON facility_contacts(facility_id);
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

# The questionnaire (the order is the order of the questions in the bot). code, group, name_ru, name_uz, hint_ru, hint_uz, aggregation
# (sum = a flow added over days, last = a state taken on the latest day). The Uzbek text is the official wording of the questions, in Latin.
INDICATORS = [
    ('beds_total', 'beds', 'Общее количество коек', 'Jami o‘rinlar soni',
     'Все койки учреждения, в том числе не отведённые под грипп и ОРВИ.', 'Muassasadagi barcha o‘rinlar (koykalar) soni, gripp va ORVI uchun ajratilmaganlari ham.', 'last'),
    ('beds_flu', 'beds', 'Из них выделено для больных гриппом и ОРВИ', 'Shundan gripp va ORVI bilan kasallangan bemorlar uchun ajratilgan o‘rinlar soni',
     'Из общего числа коек — те, что отведены больным гриппом и ОРВИ.', 'Jami o‘rinlardan gripp va ORVI bilan kasallangan bemorlar uchun ajratilganlari.', 'last'),
    ('visits', 'visits', 'Общее количество обращений', 'Jami murojaatlar soni',
     'Сколько всего человек обратились за отчётный день.', 'Hisobot kuni davomida murojaat qilgan bemorlarning umumiy soni.', 'sum'),
    ('visits_flu', 'visits', 'Из них обращений больных гриппом и ОРВИ', 'Shundan gripp va ORVI bilan kasallangan bemorlar murojaatlari soni',
     'Из общего числа обращений — обращения больных гриппом и ОРВИ.', 'Jami murojaatlardan gripp va ORVI bilan kasallangan bemorlar murojaatlari.', 'sum'),
    ('hosp', 'hosp', 'Количество пациентов, госпитализированных за отчётный день', 'Hisobot kuni davomida shifoxonaga yotqizilgan bemorlar soni',
     'Сколько пациентов поступило в стационар за отчётный день.', 'Hisobot kuni davomida shifoxonaga yangi yotqizilgan bemorlar.', 'sum'),
    ('hosp_flu', 'hosp', 'Из них больных гриппом и ОРВИ', 'Shundan gripp va ORVI bilan kasallangan bemorlar soni',
     'Из госпитализированных за отчётный день — больные гриппом и ОРВИ.', 'Hisobot kuni yotqizilganlardan gripp va ORVI bilan kasallangan bemorlar.', 'sum'),
    ('occ_pregnant', 'hosp', 'Из них беременные женщины', 'Shundan homilador ayollar',
     'Из госпитализированных с гриппом и ОРВИ — беременные женщины.', 'Gripp va ORVI bilan yotqizilganlardan homilador ayollar.', 'sum'),
    ('occ_children', 'hosp', 'Из них дети', 'Shundan bolalar',
     'Из госпитализированных с гриппом и ОРВИ — дети.', 'Gripp va ORVI bilan yotqizilganlardan bolalar.', 'sum'),
    ('severe', 'visits', 'Количество пациентов в тяжёлом состоянии', 'Og‘ir ahvoldagi bemorlar soni',
     'Сколько пациентов в тяжёлом состоянии.', 'Og‘ir ahvoldagi bemorlar soni.', 'last'),
    ('extreme', 'visits', 'Количество пациентов в крайне тяжёлом состоянии', 'O‘ta og‘ir ahvoldagi bemorlar soni',
     'Сколько пациентов в крайне тяжёлом состоянии.', 'O‘ta og‘ir ahvoldagi bemorlar soni.', 'last'),
    ('extreme_pregnant', 'visits', 'Из них беременные в крайне тяжёлом состоянии', 'Shundan o‘ta og‘ir ahvoldagi homilador ayollar',
     'Из крайне тяжёлых — беременные женщины.', 'O‘ta og‘ir ahvoldagi bemorlardan homilador ayollar.', 'last'),
    ('extreme_children', 'visits', 'Из них дети в крайне тяжёлом состоянии', 'Shundan o‘ta og‘ir ahvoldagi bolalar',
     'Из крайне тяжёлых — дети.', 'O‘ta og‘ir ahvoldagi bemorlardan bolalar.', 'last'),
    ('disch', 'hosp', 'Количество пациентов, выписанных из стационара за отчётный день', 'Hisobot kuni davomida shifoxonadan chiqarilgan bemorlar soni',
     'Сколько пациентов выписано из стационара за отчётный день.', 'Hisobot kuni davomida shifoxonadan chiqarilgan bemorlar.', 'sum'),
]
RETIRED = ("severe_pregnant", "severe_children")   # asked before the questionnaire of v2; kept (hidden) so that the old reports still show them

RULES = [
    ("error", "beds_flu <= beds_total", "Коек для больных гриппом и ОРВИ ({beds_flu}) больше общего числа коек ({beds_total}).", "Грипп ва ОРВИ учун ажратилган ўринлар ({beds_flu}) жами ўринлардан ({beds_total}) кўп."),
    ("error", "visits_flu <= visits", "Обращений больных гриппом и ОРВИ ({visits_flu}) больше, чем всего обращений ({visits}).", "Gripp va ORVI bilan kasallangan bemorlar murojaatlari ({visits_flu}) jami murojaatlardan ({visits}) ko‘p."),
    ("error", "hosp_flu <= hosp", "Госпитализированных с гриппом и ОРВИ ({hosp_flu}) больше, чем всего госпитализированных ({hosp}).", "Gripp va ORVI bilan yotqizilganlar ({hosp_flu}) jami yotqizilganlardan ({hosp}) ko‘p."),
    ("error", "occ_pregnant <= hosp_flu", "Беременных ({occ_pregnant}) больше, чем госпитализированных с гриппом и ОРВИ ({hosp_flu}).", "Homilador ayollar ({occ_pregnant}) gripp va ORVI bilan yotqizilganlardan ({hosp_flu}) ko‘p."),
    ("error", "occ_children <= hosp_flu", "Детей ({occ_children}) больше, чем госпитализированных с гриппом и ОРВИ ({hosp_flu}).", "Bolalar ({occ_children}) gripp va ORVI bilan yotqizilganlardan ({hosp_flu}) ko‘p."),
    ("error", "severe <= visits", "Тяжёлых пациентов ({severe}) больше, чем обращений ({visits}).", "Оғир беморлар ({severe}) мурожаатлардан ({visits}) кўп."),
    ("error", "extreme <= visits", "Крайне тяжёлых пациентов ({extreme}) больше, чем обращений ({visits}).", "Ўта оғир беморлар ({extreme}) мурожаатлардан ({visits}) кўп."),
    ("error", "extreme_pregnant <= extreme", "Беременных в крайне тяжёлом состоянии ({extreme_pregnant}) больше, чем крайне тяжёлых ({extreme}).", "Ўта оғир аҳволдаги ҳомиладорлар ({extreme_pregnant}) ўта оғир беморлардан ({extreme}) кўп."),
    ("error", "extreme_children <= extreme", "Детей в крайне тяжёлом состоянии ({extreme_children}) больше, чем крайне тяжёлых ({extreme}).", "Ўта оғир аҳволдаги болалар ({extreme_children}) ўта оғир беморлардан ({extreme}) кўп."),
    ("warning", "hosp <= visits", "Госпитализаций ({hosp}) больше, чем обращений ({visits}). Проверьте данные.", "Ётқизилганлар ({hosp}) мурожаатлардан ({visits}) кўп. Маълумотларни текширинг."),
    ("warning", "severe + extreme <= visits", "Тяжёлых и крайне тяжёлых вместе ({severe} + {extreme}) больше, чем обращений ({visits}).", "Оғир ва ўта оғир беморлар биргаликда ({severe} + {extreme}) мурожаатлардан ({visits}) кўп."),
]
SETTINGS = {
    "deadline_time": "18:00", "deadline_day_offset": "0", "backfill_days": "2",
    "remind_enabled": "1", "remind_times": "15:00,17:30", "remind_weekdays": "1,2,3,4,5,6,7", "admin_summary_time": "18:30", "admin_overdue_time": "20:00",
    "allow_user_edit": "1", "edit_window_hours": "24", "lock_after_days": "3",
    "occ_elevated": "70", "occ_critical": "85", "fac_occ_warn": "90",
    "growth_warn_pct": "30", "growth_crit_pct": "60", "severe_growth_pct": "25", "hosp_growth_pct": "30",
    "note_enabled": "1", "q_hints": "0", "default_lang": "uz", "org_title": "Министерство здравоохранения Республики Узбекистан",
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
                c.execute("INSERT INTO regions(id, name_ru, name_uz, sort) VALUES (?,?,?,?)", (i, ru, lat(uz), i))
        if not c.execute("SELECT 1 FROM indicators LIMIT 1").fetchone():
            for i, (code, grp, ru, uz, hru, huz, agg) in enumerate(INDICATORS, 1):
                c.execute("INSERT INTO indicators(code, grp, name_ru, name_uz, hint_ru, hint_uz, agg, sort, core) VALUES (?,?,?,?,?,?,?,?,1)", (code, grp, ru, uz, hru, huz, agg, i))
        if not c.execute("SELECT 1 FROM rules LIMIT 1").fetchone():
            for i, (kind, expr, ru, uz) in enumerate(RULES, 1):
                c.execute("INSERT INTO rules(kind, expr, message_ru, message_uz, sort, core) VALUES (?,?,?,?,?,1)", (kind, expr, ru, lat(uz), i))
        for k, v in SETTINGS.items():
            c.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?,?)", (k, v))
        for col, ddl in (("thread_id", "INTEGER"), ("direction", "TEXT NOT NULL DEFAULT 'in'"), ("staff_id", "INTEGER"), ("error", "TEXT NOT NULL DEFAULT ''")):     # a database made before the dialogues
            if col not in {r["name"] for r in c.execute("PRAGMA table_info(ministry_messages)")}:
                c.execute(f"ALTER TABLE ministry_messages ADD COLUMN {col} {ddl}")
        c.execute("UPDATE ministry_messages SET thread_id=id WHERE thread_id IS NULL")
        if "can_manage_territories" not in {r["name"] for r in c.execute("PRAGMA table_info(staff)")}:      # a database made before the territories of the administrators
            c.execute("ALTER TABLE staff ADD COLUMN can_manage_territories INTEGER NOT NULL DEFAULT 0")
        if "required" not in {r["name"] for r in c.execute("PRAGMA table_info(indicators)")}:                # a database made before the editor of the questionnaire
            c.execute("ALTER TABLE indicators ADD COLUMN required INTEGER NOT NULL DEFAULT 1")
        if "parent_code" not in {r["name"] for r in c.execute("PRAGMA table_info(indicators)")}:
            c.execute("ALTER TABLE indicators ADD COLUMN parent_code TEXT NOT NULL DEFAULT ''")
        if "beds" not in {r["name"] for r in c.execute("PRAGMA table_info(facilities)")}:                  # a database made before the editor of territories
            c.execute("ALTER TABLE facilities ADD COLUMN beds INTEGER")
        if "heartbeat" not in {r["name"] for r in c.execute("PRAGMA table_info(broadcasts)")}:
            c.execute("ALTER TABLE broadcasts ADD COLUMN heartbeat TEXT NOT NULL DEFAULT ''")
        questionnaire_v2(c)
        region_heads_v1(c)
        questionnaire_texts_v3(c)
        questionnaire_v4(c)
        occupied_unbounded_v4(c)
        if not c.execute("SELECT 1 FROM settings WHERE key='default_lang_uz_v1'").fetchone():     # one time: a database made earlier still has the old default
            c.execute("UPDATE settings SET value='uz' WHERE key='default_lang'")
            c.execute("INSERT INTO settings(key, value) VALUES ('default_lang_uz_v1', ?)", (now(),))
        auth.ensure_admin(c)


def questionnaire_v2(c) -> None:
    """One time, for a database made before the new questionnaire: the twelve questions in the new order and wording (Uzbek in Latin), the two new
    questions about pregnant women and children among the occupied beds, the old «severe: pregnant / children» hidden (their reports stay), the rules and
    the Uzbek names of the regions in Latin."""
    if c.execute("SELECT 1 FROM settings WHERE key='questionnaire_v2'").fetchone():
        return
    for i, (code, grp, ru, uz, hru, huz, agg) in enumerate(INDICATORS, 1):
        if c.execute("SELECT 1 FROM indicators WHERE code=?", (code,)).fetchone():
            c.execute("UPDATE indicators SET grp=?, name_ru=?, name_uz=?, hint_ru=?, hint_uz=?, agg=?, sort=?, active=1, core=1 WHERE code=?", (grp, ru, uz, hru, huz, agg, i, code))
        else:
            c.execute("INSERT INTO indicators(code, grp, name_ru, name_uz, hint_ru, hint_uz, agg, sort, core) VALUES (?,?,?,?,?,?,?,?,1)", (code, grp, ru, uz, hru, huz, agg, i))
    for code in RETIRED:
        c.execute("UPDATE indicators SET active=0, sort=?, core=0 WHERE code=?", (900 + RETIRED.index(code), code))
    for r in c.execute("SELECT id, expr FROM rules WHERE core=1").fetchall():
        if any(x in r["expr"] for x in RETIRED):
            c.execute("DELETE FROM rules WHERE id=?", (r["id"],))
    have = {r["expr"] for r in c.execute("SELECT expr FROM rules")}
    mx = c.execute("SELECT COALESCE(MAX(sort),0) FROM rules").fetchone()[0]
    for kind, expr, ru, uz in RULES:
        if expr in have:
            c.execute("UPDATE rules SET message_uz=? WHERE expr=? AND core=1", (lat(uz), expr))
        else:
            mx += 1
            c.execute("INSERT INTO rules(kind, expr, message_ru, message_uz, sort, core) VALUES (?,?,?,?,?,1)", (kind, expr, ru, lat(uz), mx))
    for ru, uz in REGIONS:
        c.execute("UPDATE regions SET name_uz=? WHERE name_ru=? AND name_uz=?", (lat(uz), ru, uz))
    c.execute("INSERT INTO settings(key, value) VALUES ('questionnaire_v2', ?)", (now(),))


def questionnaire_texts_v3(c) -> None:
    """One time: the wording «gripp va ORVI» (flu and acute respiratory infections) in the names and hints of the questions and in the messages of the rules."""
    if c.execute("SELECT 1 FROM settings WHERE key='questionnaire_v3'").fetchone():
        return
    for code, grp, ru, uz, hru, huz, agg in INDICATORS:
        c.execute("UPDATE indicators SET name_ru=?, name_uz=?, hint_ru=?, hint_uz=? WHERE code=? AND core=1", (ru, uz, hru, huz, code))
    for kind, expr, ru, uz in RULES:
        c.execute("UPDATE rules SET message_ru=?, message_uz=? WHERE expr=? AND core=1", (ru, lat(uz), expr))
    c.execute("INSERT INTO settings(key, value) VALUES ('questionnaire_v3', ?)", (now(),))


def occupied_unbounded_v4(c) -> None:
    """One time: the rule «occupied beds <= beds for flu and ARVI» is removed (the number of the occupied beds is no longer limited by the number of the beds)."""
    if c.execute("SELECT 1 FROM settings WHERE key='occupied_unbounded_v4'").fetchone():
        return
    c.execute("DELETE FROM rules WHERE core=1 AND expr='beds_occupied <= beds_flu'")
    c.execute("INSERT INTO settings(key, value) VALUES ('occupied_unbounded_v4', ?)", (now(),))


# the heads of the regional health departments (ССБ), as the administrator gave them: the region (as written in the list), the full name, the phones
REGION_HEADS = [
    ("Қорақалпоғистон Республикаси", "Курбанов Мурад Исмайлович", "97-789-70-77"),
    ("Андижон вилояти", "Умиджон", "90-380-55-90"),
    ("Бухоро вилояти", "Ражабов Мухсин Мансурович", "97-301-25-00"),
    ("Жиззах вилояти", "Умаров Мамарасул Дўстматович", "94-449-44-15"),
    ("Қашқадарё вилояти", "в.в.б. Қурбонов Низом Азизович", "90-195-07-18"),
    ("Навоий вилояти", "Сафоев Нурали Неъматуллоевич", "94-372-30-00"),
    ("Наманган вилояти", "Алижанов Аброр Алижанович", "91-293-05-55"),
    ("Самарқанд вилояти", "Зайниев Сухроб Собирович", "91-535-51-56"),
    ("Сурхондарё вилояти", "Абдувохидов Комил Муртазаевич", "91-574-44-43"),
    ("Сирдарё вилояти", "Вохид Ёрқулович", "97-394-22-99"),
    ("Тошкент вилояти", "Арзикулов Тўрақул Содиқович", "95-833-44-45\n94-612-46-37"),
    ("Фарғона вилояти", "Анвар Азимжонович", "975950528"),
    ("Хоразм вилояти", "Тангрибердиев Кўпалбай Раимбердиевич", "99-601-80-75"),
    ("Тошкент шаҳар", "Исабеков Ботирбек Абдуллаевич", "99-811-54-55"),
]


def region_heads_v1(c) -> None:
    """One time: the heads of the regional health departments are attached to their regions (only to a region that has no head yet)."""
    if c.execute("SELECT 1 FROM settings WHERE key='region_heads_v1'").fetchone():
        return
    from . import editor
    regions = [dict(r) for r in c.execute("SELECT id, name_ru, name_uz FROM regions")]
    for text, fio, phone in REGION_HEADS:
        reg = editor.match_region(regions, text)
        if reg and not c.execute("SELECT 1 FROM region_contacts WHERE region_id=?", (reg["id"],)).fetchone():
            c.execute("INSERT INTO region_contacts(region_id, kind, fio, phone, created_at, updated_at) VALUES (?,?,?,?,?,?)", (reg["id"], "main", fio, ",".join(editor.phones(phone)), now(), now()))
    c.execute("INSERT INTO settings(key, value) VALUES ('region_heads_v1', ?)", (now(),))


# The questionnaire of the Ministry (13 questions): two new ones (flu visits, flu hospitalized), the discharged moved to the end, «of them» questions tied to the one they add to;
# the question about the occupied beds is no longer asked (it stays, switched off, with its figures).
PARENT = {"beds_flu": "beds_total", "visits_flu": "visits", "hosp_flu": "hosp", "occ_pregnant": "hosp_flu", "occ_children": "hosp_flu", "extreme_pregnant": "extreme", "extreme_children": "extreme"}
OCCUPIED = ("beds_occupied", "beds", "Количество коек, занятых больными гриппом и ОРВИ на конец отчётного дня",
            "Hisobot kuni yakunida gripp va ORVI bilan kasallangan bemorlar band qilgan o‘rinlar soni", "Сколько коек занято больными гриппом и ОРВИ на конец дня.",
            "Hisobot kuni oxirida gripp va ORVI bilan kasallangan bemorlar yotgan o‘rinlar.", "last")


def questionnaire_v4(c) -> None:
    """One time: the questionnaire of the Ministry (see INDICATORS): texts, order, the «of them» links, the new questions, the rules; the occupied beds switched off."""
    if c.execute("SELECT 1 FROM settings WHERE key='questionnaire_v4'").fetchone():
        return
    for i, (code, grp, ru, uz, hru, huz, agg) in enumerate(INDICATORS, 1):
        if c.execute("SELECT 1 FROM indicators WHERE code=?", (code,)).fetchone():
            c.execute("UPDATE indicators SET grp=?, name_ru=?, name_uz=?, hint_ru=?, hint_uz=?, agg=?, sort=?, active=1, core=1, required=1, parent_code=? WHERE code=?",
                      (grp, ru, uz, hru, huz, agg, i, PARENT.get(code, ""), code))
        else:
            c.execute("INSERT INTO indicators(code, grp, name_ru, name_uz, hint_ru, hint_uz, agg, sort, core, required, parent_code) VALUES (?,?,?,?,?,?,?,?,1,1,?)", (code, grp, ru, uz, hru, huz, agg, i, PARENT.get(code, "")))
    code, grp, ru, uz, hru, huz, agg = OCCUPIED
    if c.execute("SELECT 1 FROM indicators WHERE code=?", (code,)).fetchone():
        c.execute("UPDATE indicators SET active=0, sort=900, parent_code='' WHERE code=?", (code,))
    else:
        c.execute("INSERT INTO indicators(code, grp, name_ru, name_uz, hint_ru, hint_uz, agg, sort, active, core, required) VALUES (?,?,?,?,?,?,?,900,0,1,1)", (code, grp, ru, uz, hru, huz, agg))
    for r in c.execute("SELECT id, expr FROM rules WHERE core=1").fetchall():                  # the rules about the occupied beds go
        if "beds_occupied" in r["expr"]:
            c.execute("DELETE FROM rules WHERE id=?", (r["id"],))
    have = {r["expr"] for r in c.execute("SELECT expr FROM rules")}
    mx = c.execute("SELECT COALESCE(MAX(sort),0) FROM rules").fetchone()[0]
    for kind, expr, ru, uz in RULES:
        if expr not in have:
            mx += 1
            c.execute("INSERT INTO rules(kind, expr, message_ru, message_uz, sort, core) VALUES (?,?,?,?,?,1)", (kind, expr, ru, lat(uz), mx))
    c.execute("INSERT INTO settings(key, value) VALUES ('questionnaire_v4', ?)", (now(),))


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


@contextlib.contextmanager
def history_unlocked(c):
    """Deleting a report has to remove its immutable version history: the guard triggers are dropped and put back inside the same transaction (DDL is transactional in SQLite)."""
    sqls = [r["sql"] for r in c.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name IN ('versions_no_delete','versions_no_update')")]
    c.execute("DROP TRIGGER IF EXISTS versions_no_delete")
    c.execute("DROP TRIGGER IF EXISTS versions_no_update")
    try:
        yield
    finally:
        for q in sqls:
            c.execute(q)


def delete_reports(c, ids: list[int], reason: str = "") -> int:
    """Removes reports with values and versions; the audit log keeps a snapshot of each (who, where, which date, the figures)."""
    n = 0
    with history_unlocked(c):
        for rid in ids:
            r = c.execute("""SELECT rep.id, rep.report_date, rep.version, f.name_ru AS facility, d.name_ru AS district, rg.name_ru AS region FROM reports rep JOIN facilities f ON f.id=rep.facility_id
                             JOIN districts d ON d.id=f.district_id JOIN regions rg ON rg.id=d.region_id WHERE rep.id=?""", (rid,)).fetchone()
            if not r:
                continue
            vals = {v["code"]: v["value"] for v in c.execute("SELECT code, value FROM report_values WHERE report_id=?", (rid,))}
            audit(c, "report.delete", "report", rid, {"facility": r["facility"], "district": r["district"], "region": r["region"], "date": r["report_date"], "version": r["version"], "values": vals, "reason": reason})
            c.execute("DELETE FROM report_versions WHERE report_id=?", (rid,))
            c.execute("DELETE FROM report_values WHERE report_id=?", (rid,))
            c.execute("DELETE FROM reports WHERE id=?", (rid,))
            n += 1
    return n


def delete_facilities(c, ids: list[int], reason: str = "") -> dict:
    """Removes facilities with their reports and the links of responsible people (the people themselves stay in the bot)."""
    rep = [r["id"] for i in ids for r in c.execute("SELECT id FROM reports WHERE facility_id=?", (i,))]
    nrep = delete_reports(c, rep, reason or "удаление учреждения")
    for i in ids:
        f = c.execute("SELECT name_ru FROM facilities WHERE id=?", (i,)).fetchone()
        if not f:
            continue
        c.execute("DELETE FROM assignments WHERE facility_id=?", (i,))
        c.execute("DELETE FROM facility_contacts WHERE facility_id=?", (i,))
        c.execute("UPDATE access_requests SET facility_id=NULL WHERE facility_id=?", (i,))
        c.execute("DELETE FROM preapproved WHERE facility_id=?", (i,))
        c.execute("DELETE FROM ministry_messages WHERE facility_id=?", (i,))
        c.execute("DELETE FROM facilities WHERE id=?", (i,))
        audit(c, "facility.delete", "facility", i, {"name": f["name_ru"], "reports_removed": len(rep)})
    return {"reports": nrep, "facilities": len(ids)}
