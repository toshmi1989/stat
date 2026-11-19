"""Web accounts (staff) and their rights.

super_admin — everything: users, territories, settings, all regions
admin       — works with the regions given by the super administrator: control of reporting, reports, statistics,
              and (if allowed) Telegram users and access requests inside those regions
viewer      — read-only statistics and dashboards of the regions given to them
Rights are checked here and in the API, never only in the interface."""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from contextvars import ContextVar

from .db import connect, now, tx

SESSION_DAYS = 14
ROLES = {"super_admin": "Главный администратор", "admin": "Администратор", "viewer": "Просмотр"}
CURRENT: ContextVar[dict | None] = ContextVar("current_user", default=None)
CURRENT_IP: ContextVar[str] = ContextVar("current_ip", default="")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(got.hex(), digest)
    except (ValueError, TypeError):
        return False


def generate_password() -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(10))


def ensure_admin(c: sqlite3.Connection) -> None:
    if c.execute("SELECT 1 FROM staff LIMIT 1").fetchone():
        return
    password = os.environ.get("APP_PASSWORD")
    generated = not password
    if generated:
        password = generate_password()
    c.execute("INSERT INTO staff(login, name, password_hash, role, can_manage_users, created_at) VALUES ('admin', 'Главный администратор', ?, 'super_admin', 1, ?)",
              (hash_password(password), now()))
    if generated:
        print(f'Создан главный администратор: логин "admin", пароль "{password}". Запишите его и смените в разделе «Пользователи».', flush=True)


# ---------------------------------------------------------------- sessions
def _new_session(staff_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with tx() as c:
        c.execute("DELETE FROM sessions WHERE expires_at < datetime('now')")
        c.execute(f"INSERT INTO sessions(token, staff_id, expires_at) VALUES (?,?, datetime('now', '+{SESSION_DAYS} days'))", (token, staff_id))
    return token


def login(login_name: str, password: str) -> dict | None:
    c = connect()
    u = c.execute("SELECT * FROM staff WHERE login=? AND active=1", (login_name.strip(),)).fetchone()
    c.close()
    if not u or not verify_password(password, u["password_hash"]):
        return None
    return {"token": _new_session(u["id"]), "staff_id": u["id"]}


def user_from_token(token: str | None) -> dict | None:
    if not token:
        return None
    c = connect()
    try:
        row = c.execute("""SELECT s.id, s.login, s.name, s.role, s.tg_id, s.can_manage_users, s.can_manage_territories, s.can_edit_reports FROM sessions t JOIN staff s ON s.id=t.staff_id
                           WHERE t.token=? AND t.expires_at > datetime('now') AND s.active=1""", (token,)).fetchone()
        if not row:
            return None
        u = dict(row)
        u["regions"] = None if u["role"] == "super_admin" else [r["region_id"] for r in c.execute("SELECT region_id FROM staff_scope WHERE staff_id=?", (u["id"],))]
        return u
    finally:
        c.close()


def logout(token: str | None) -> None:
    if token:
        with tx() as c:
            c.execute("DELETE FROM sessions WHERE token=?", (token,))


MAX_FAILS, WINDOW = 10, 15 * 60
_fails: dict[str, list[float]] = {}


def too_many_fails(ip: str) -> bool:
    t = time.time()
    _fails[ip] = [x for x in _fails.get(ip, []) if t - x < WINDOW]
    return len(_fails[ip]) >= MAX_FAILS


def record_fail(ip: str) -> None:
    _fails.setdefault(ip, []).append(time.time())


def clear_fails(ip: str) -> None:
    _fails.pop(ip, None)


# ---------------------------------------------------------------- what a person may see and do
def is_super(u) -> bool:
    return bool(u) and u["role"] == "super_admin"


def can_write(u) -> bool:
    return bool(u) and u["role"] in ("super_admin", "admin")


def can_territories(u) -> bool:
    """The super administrator, or an administrator who was given the section «Территории» (only for his own regions)."""
    return bool(u) and (u["role"] == "super_admin" or (u["role"] == "admin" and bool(u["can_manage_territories"])))


def sees_region(u, region_id: int) -> bool:
    return bool(u) and (u["regions"] is None or region_id in u["regions"])


def region_filter_sql(u, col: str = "d.region_id") -> tuple[str, list]:
    """SQL fragment limiting rows to the regions of the person: ('', []) for everyone, ('1=0', []) for nobody."""
    if u["regions"] is None:
        return "", []
    if not u["regions"]:
        return "1=0", []
    return f"{col} IN ({','.join('?' * len(u['regions']))})", list(u["regions"])


def norm_login(s: str) -> str:
    return re.sub(r"[^a-z0-9._-]", "", s.strip().lower())
