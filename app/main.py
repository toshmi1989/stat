"""Flu Monitoring: Telegram bot + web platform on one database. JSON API for the single-page interface; rights are checked here."""
import io
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import date, timedelta
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import auth, backup, bot, broadcast, exports, forecast, notify, people, reports, rules, stats, tg, xlsx_import
from .db import all_settings, audit, connect, delete_facilities, delete_reports, init_db, now, now_dt, today, tx

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(BASE, "static")


@asynccontextmanager
async def lifespan(_app):
    init_db()
    if os.environ.get("FLU_NO_BACKUP") != "1":
        backup.start()
    tg.start(bot.handle_update)
    yield


app = FastAPI(title="Flu Monitoring", lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
OPEN_PATHS = ("/healthz", "/login")
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
                               "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
}


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[-1].strip() if fwd else (request.client.host if request.client else "")


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    ip_token = auth.CURRENT_IP.set(client_ip(request))
    try:
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin != "null":
            host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
            if urlparse(origin).netloc != host:
                return JSONResponse({"error": "Запрос с чужого сайта отклонён"}, 403)
        user = auth.user_from_token(request.cookies.get("sid"))
        request.state.user = user
        resp = None
        if not user and path not in OPEN_PATHS and not path.startswith("/static/"):
            resp = JSONResponse({"error": "Требуется вход"}, 401) if path.startswith("/api/") else RedirectResponse("/login", 303)
        if resp is None:
            token = auth.CURRENT.set(user)
            try:
                resp = await call_next(request)
            finally:
                auth.CURRENT.reset(token)
        for k, v in SECURITY_HEADERS.items():
            resp.headers.setdefault(k, v)
        if path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        elif path.startswith("/static/"):
            resp.headers["Cache-Control"] = "no-cache"
        return resp
    finally:
        auth.CURRENT_IP.reset(ip_token)


@app.exception_handler(reports.ReportError)
async def report_error(_r, e: reports.ReportError):
    return JSONResponse({"error": e.message, **({"details": e.details} if e.details else {})}, e.status)


@app.exception_handler(people.PeopleError)
async def people_error(_r, e: people.PeopleError):
    return JSONResponse({"error": e.message}, e.status)


@app.exception_handler(HTTPException)
async def http_error(_r, e: HTTPException):
    return JSONResponse({"error": e.detail}, e.status_code)


def me(request: Request) -> dict:
    return request.state.user


def bad(message: str, status: int = 400):
    raise HTTPException(status, message)


def need_super(request: Request) -> dict:
    if not auth.is_super(me(request)):
        bad("Раздел доступен главному администратору", 403)
    return me(request)


def need_write(request: Request) -> dict:
    if not auth.can_write(me(request)):
        bad("Недостаточно прав", 403)
    return me(request)


async def jbody(request: Request) -> dict:
    try:
        b = await request.json()
    except ValueError:
        bad("Ожидался JSON")
    if not isinstance(b, dict):
        bad("Ожидался объект JSON")
    return b


def q_int(v):
    return int(v) if v not in (None, "", "0") and str(v).isdigit() else None


def period(request: Request, c=None) -> tuple[str, str]:
    """[d1, d2] from ?d1&d2, or the single day ?date, or today."""
    p = request.query_params
    d1 = p.get("d1") or p.get("date") or today().isoformat()
    d2 = p.get("d2") or p.get("date") or d1
    try:
        a, b = date.fromisoformat(d1), date.fromisoformat(d2)
    except ValueError:
        bad("Дата должна быть в формате ГГГГ-ММ-ДД")
    if b < a:
        bad("Конец периода раньше начала")
    if (b - a).days > 800:
        bad("Период не больше 800 дней")
    return d1, d2


def filters(request: Request) -> dict:
    p = request.query_params
    return {"region_id": q_int(p.get("region_id")), "district_id": q_int(p.get("district_id")), "facility_id": q_int(p.get("facility_id"))}


def check_region(user, region_id):
    if region_id and not auth.sees_region(user, region_id):
        bad("Нет доступа к этому региону", 403)


def check_scope_filters(user, f: dict) -> None:
    c = connect()
    try:
        if f["facility_id"]:
            r = c.execute("SELECT d.region_id FROM facilities f JOIN districts d ON d.id=f.district_id WHERE f.id=?", (f["facility_id"],)).fetchone()
            check_region(user, r["region_id"] if r else -1)
        elif f["district_id"]:
            r = c.execute("SELECT region_id FROM districts WHERE id=?", (f["district_id"],)).fetchone()
            check_region(user, r["region_id"] if r else -1)
        else:
            check_region(user, f["region_id"])
    finally:
        c.close()


# ---------------------------------------------------------------- pages and login
@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(os.path.join(STATIC, "index.html"), headers={"Cache-Control": "no-cache"})


LOGIN_HTML = open(os.path.join(STATIC, "login.html"), encoding="utf-8").read()


def login_page(error: str = "", status: int = 200, login: str = ""):
    import html
    return HTMLResponse(LOGIN_HTML.replace("{{error}}", html.escape(error)).replace("{{login}}", html.escape(login[:60])), status, headers={"Cache-Control": "no-store"})


@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    return RedirectResponse("/", 303) if request.state.user else login_page()


@app.post("/login")
def login_post(request: Request, login: str = Form(...), password: str = Form(...)):
    ip = client_ip(request)
    if auth.too_many_fails(ip):
        return login_page("Слишком много попыток. Подождите 15 минут.", 429, login)
    res = auth.login(login, password)
    if not res:
        auth.record_fail(ip)
        with tx() as c:
            audit(c, "login.fail", "staff", "", {"login": login[:60]}, actor="—")
        return login_page("Неверный логин или пароль.", 401, login)
    auth.clear_fails(ip)
    with tx() as c:
        audit(c, "login.ok", "staff", res["staff_id"], {}, actor=login[:60])
    resp = RedirectResponse("/", 303)
    resp.set_cookie("sid", res["token"], httponly=True, samesite="lax", max_age=auth.SESSION_DAYS * 86400,
                    secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https")
    return resp


@app.post("/logout")
def logout(request: Request):
    auth.logout(request.cookies.get("sid"))
    resp = RedirectResponse("/login", 303)
    resp.delete_cookie("sid")
    return resp


@app.get("/api/me")
def api_me(request: Request):
    u = me(request)
    c = connect()
    try:
        st = all_settings(c)
        return {"id": u["id"], "login": u["login"], "name": u["name"], "role": u["role"], "role_label": auth.ROLES[u["role"]], "regions": u["regions"],
                "can_manage_users": bool(u["can_manage_users"]) or auth.is_super(u), "can_edit_reports": bool(u["can_edit_reports"]) and auth.can_write(u),
                "today": today().isoformat(), "bot": tg.bot_username() if tg.configured() else "", "bot_configured": tg.configured(),
                "thresholds": {"elevated": float(st["occ_elevated"]), "critical": float(st["occ_critical"])}, "org": st["org_title"],
                "messages_unread": c.execute("SELECT COUNT(*) FROM ministry_messages WHERE read_at='' AND direction='in'").fetchone()[0] if auth.is_super(u) else 0}
    finally:
        c.close()


@app.get("/api/meta")
def api_meta(request: Request):
    """Regions the person may see, the indicators, the check settings: what every filter needs."""
    u = me(request)
    c = connect()
    try:
        regs = [dict(r) for r in c.execute("SELECT id, name_ru, name_uz, active FROM regions ORDER BY sort") if auth.sees_region(u, r["id"])]
        return {"regions": regs, "indicators": [dict(r) for r in c.execute("SELECT code, grp, name_ru, name_uz, agg, sort, active, core FROM indicators ORDER BY sort")]}
    finally:
        c.close()


@app.get("/api/districts")
def api_districts(request: Request, region_id: int):
    check_region(me(request), region_id)
    c = connect()
    try:
        return {"items": [dict(r) for r in c.execute("SELECT id, region_id, name_ru, name_uz, active FROM districts WHERE region_id=? ORDER BY name_ru", (region_id,))]}
    finally:
        c.close()


@app.get("/api/facilities")
def api_facilities(request: Request, district_id: int | None = None, q: str = "", region_id: int | None = None, page: int = 1, size: int = 50):
    u = me(request)
    c = connect()
    try:
        w, a = ["1=1"], []
        s, args = auth.region_filter_sql(u, "d.region_id")
        if s:
            w.append(s); a += args
        if district_id:
            w.append("f.district_id=?"); a.append(district_id)
        if region_id:
            w.append("d.region_id=?"); a.append(region_id)
        if q.strip():
            w.append("(f.name_ru LIKE ? OR f.name_uz LIKE ?)"); a += [f"%{q.strip()}%"] * 2
        size = max(1, min(size, 200))
        total = c.execute(f"SELECT COUNT(*) FROM facilities f JOIN districts d ON d.id=f.district_id WHERE {' AND '.join(w)}", a).fetchone()[0]
        rows = c.execute(f"""SELECT f.id, f.name_ru, f.name_uz, f.active, f.contact, f.district_id, d.name_ru AS district, d.region_id, r.name_ru AS region,
                                    (SELECT COUNT(*) FROM reports x WHERE x.facility_id=f.id) AS reports
                             FROM facilities f JOIN districts d ON d.id=f.district_id JOIN regions r ON r.id=d.region_id WHERE {' AND '.join(w)}
                             ORDER BY r.sort, d.name_ru, f.name_ru LIMIT ? OFFSET ?""", a + [size, (max(page, 1) - 1) * size]).fetchall()
        resp = {}
        for x in c.execute("""SELECT a.facility_id, a.id, a.kind, a.tg_id, a.fio, a.contact, u.first_name, u.last_name, u.username FROM assignments a JOIN tg_users u ON u.tg_id=a.tg_id WHERE a.active=1"""):
            resp.setdefault(x["facility_id"], []).append(dict(x))
        return {"total": total, "items": [dict(r) | {"assignments": resp.get(r["id"], [])} for r in rows]}
    finally:
        c.close()


# ---------------------------------------------------------------- analytics
@app.get("/api/dashboard")
def api_dashboard(request: Request, fallback: int = 1):
    u = me(request)
    f = filters(request)
    check_scope_filters(u, f)
    d1, d2 = period(request)
    c = connect()
    try:
        asked = d2
        latest = stats.latest_date(c, u, d2)
        used = False
        if fallback and request.query_params.get("date") and latest and latest != d2 and not request.query_params.get("d1"):
            k0 = stats.kpis(c, u, d2, d2, **f)
            if k0["reported"] == 0:
                d1 = d2 = latest   # nothing yet for the chosen day: show the latest day that has data, and say so
                used = True
        k = stats.kpis(c, u, d1, d2, **f)
        ctl = reports.control(c, u, asked, f["region_id"], f["district_id"], f["facility_id"]) if auth.can_write(u) and (d1 == d2 or used) else None
        return {"kpis": k, "used_date": d2, "fallback": used, "requested": request.query_params.get("date") or d2, "latest": latest, "control": ctl["counts"] if ctl else None}
    finally:
        c.close()


@app.get("/api/pulse")
def api_pulse(request: Request):
    """A cheap token of the reports data: the page polls it and reloads itself when it changes (a summary arrived from the bot, a report was edited or deleted).
    Built from the database, not from memory: the service runs in several processes."""
    me(request)
    c = connect()
    try:
        r = c.execute("SELECT (SELECT COALESCE(MAX(id),0) FROM report_versions) AS v, (SELECT COUNT(*) FROM reports) AS n, (SELECT COUNT(*) FROM facilities) AS f, "
                        "(SELECT COALESCE(MAX(id),0) FROM ministry_messages) AS m").fetchone()
        unread = c.execute("SELECT COUNT(*) FROM ministry_messages WHERE read_at='' AND direction='in'").fetchone()[0] if auth.is_super(me(request)) else 0
        return {"token": f"{r['v']}.{r['n']}.{r['f']}.{r['m']}", "unread": unread}
    finally:
        c.close()


@app.get("/api/regions-table")
def api_regions_table(request: Request, level: str = "region", parent_id: int | None = None):
    u = me(request)
    d1, d2 = period(request)
    c = connect()
    try:
        return stats.regions_table(c, u, d1, d2, level if level in ("region", "district", "facility", "rfac") else "region", parent_id)
    finally:
        c.close()


@app.get("/api/dynamics")
def api_dynamics(request: Request, metrics: str = "visits", regions: str = ""):
    u = me(request)
    f = filters(request)
    check_scope_filters(u, f)
    d1, d2 = period(request)
    rids = [int(x) for x in regions.split(",") if x.isdigit()][:6]
    for r in rids:
        check_region(u, r)
    ms = [m for m in metrics.split(",") if re.fullmatch(r"[a-z0-9_]{1,40}", m)][:8]
    c = connect()
    try:
        return stats.dynamics(c, u, d1, d2, ms or ["visits"], rids or None, f["district_id"], f["facility_id"]) | {"region_id": f["region_id"]}
    finally:
        c.close()


@app.get("/api/beds")
def api_beds(request: Request, level: str = "region", parent_id: int | None = None):
    u = me(request)
    d1, d2 = period(request)
    c = connect()
    try:
        return stats.bed_balance(c, u, d1, d2, level if level in ("region", "district", "facility") else "region", parent_id)
    finally:
        c.close()


@app.get("/api/hosp-disch")
def api_hosp_disch(request: Request):
    u = me(request)
    f = filters(request)
    check_scope_filters(u, f)
    d1, d2 = period(request)
    c = connect()
    try:
        return stats.hosp_disch(c, u, d1, d2, **f)
    finally:
        c.close()


@app.get("/api/forecast")
def api_forecast(request: Request, ref: str | None = None):
    u = me(request)
    f = filters(request)
    check_scope_filters(u, f)
    c = connect()
    try:
        return forecast.overview(c, u, ref, **f)
    finally:
        c.close()


@app.get("/api/alerts")
def api_alerts(request: Request, ref: str | None = None):
    u = me(request)
    c = connect()
    try:
        out = forecast.alerts(c, u, ref)
        if auth.can_write(u):
            out += forecast.missing_reports_alerts(c, u, ref or today().isoformat())
        return {"items": out}
    finally:
        c.close()


@app.get("/api/control")
def api_control(request: Request, date_: str | None = None):
    u = need_write(request)
    f = filters(request)
    check_scope_filters(u, f)
    d = request.query_params.get("date") or today().isoformat()
    c = connect()
    try:
        return reports.control(c, u, d, **f)
    finally:
        c.close()


# ---------------------------------------------------------------- reports (administrators)
def scope_check_report(c, user, report_id: int) -> dict:
    r = reports.get_report(c, report_id)
    check_region(user, r["region_id"])
    return r


@app.get("/api/reports")
def api_reports(request: Request, q: str = "", status: str = "", page: int = 1, size: int = 50):
    u = need_write(request)
    f = filters(request)
    check_scope_filters(u, f)
    d1, d2 = period(request)
    c = connect()
    try:
        w, a = ["rep.report_date BETWEEN ? AND ?"], [d1, d2]
        s, args = auth.region_filter_sql(u, "r.id")
        if s:
            w.append(s); a += args
        for col, v in (("r.id", f["region_id"]), ("d.id", f["district_id"]), ("f.id", f["facility_id"])):
            if v:
                w.append(f"{col}=?"); a.append(v)
        if status in ("sent", "returned"):
            w.append("rep.status=?"); a.append(status)
        elif status == "corrected":
            w.append("rep.corrected=1")
        elif status == "late":
            w.append("rep.late=1")
        if q.strip():
            w.append("(f.name_ru LIKE ? OR d.name_ru LIKE ?)"); a += [f"%{q.strip()}%"] * 2
        size = max(1, min(size, 200))
        base = "FROM reports rep JOIN facilities f ON f.id=rep.facility_id JOIN districts d ON d.id=f.district_id JOIN regions r ON r.id=d.region_id WHERE " + " AND ".join(w)
        total = c.execute("SELECT COUNT(*) " + base, a).fetchone()[0]
        rows = c.execute("SELECT rep.id, rep.report_date, rep.status, rep.version, rep.corrected, rep.late, rep.locked, rep.submitted_by, rep.submitted_at, f.name_ru AS facility, d.name_ru AS district, r.name_ru AS region "
                         + base + " ORDER BY rep.report_date DESC, rep.id DESC LIMIT ? OFFSET ?", a + [size, (max(page, 1) - 1) * size]).fetchall()
        return {"total": total, "items": [dict(r) for r in rows]}
    finally:
        c.close()


@app.get("/api/reports/{report_id}")
def api_report(request: Request, report_id: int):
    u = need_write(request)
    c = connect()
    try:
        return scope_check_report(c, u, report_id)
    finally:
        c.close()


@app.put("/api/reports")
async def api_report_save(request: Request):
    u = need_write(request)
    if not u["can_edit_reports"]:
        bad("Вам не разрешено исправлять отчёты", 403)
    b = await jbody(request)
    vals = b.get("values")
    if not isinstance(vals, dict):
        bad("Нужны значения показателей")
    try:
        fid = int(b.get("facility_id"))
    except (TypeError, ValueError):
        bad("Не указано учреждение")
    with tx() as c:
        fi = reports.facility_info(c, fid)
        if not fi:
            bad("Учреждение не найдено", 404)
        check_region(u, fi["region_id"])
        out = reports.admin_save(c, fid, str(b.get("date") or ""), {k: v for k, v in vals.items()}, str(b.get("reason") or ""), reports.by_staff(u))
    return out


@app.post("/api/reports/delete")
async def api_reports_delete(request: Request):
    """Deleting reports (e.g. test ones) is the super administrator's; each one is kept in the audit log as a snapshot."""
    need_super(request)
    b = await jbody(request)
    ids = b.get("ids")
    if not isinstance(ids, list) or not ids or len(ids) > 1000 or not all(isinstance(i, int) for i in ids):
        bad("ids: список номеров отчётов (до 1000)")
    reason = str(b.get("reason") or "").strip()
    if not reason:
        bad("Укажите причину удаления")
    with tx() as c:
        n = delete_reports(c, ids, reason)
    return {"deleted": n}


@app.post("/api/reports/{report_id}/return")
async def api_report_return(request: Request, report_id: int):
    u = need_write(request)
    b = await jbody(request)
    with tx() as c:
        r = scope_check_report(c, u, report_id)
        reports.return_for_correction(c, report_id, str(b.get("reason") or ""), reports.by_staff(u))
        # tell the responsible person
        for a in c.execute("SELECT tg_id FROM assignments WHERE facility_id=? AND active=1", (r["facility_id"],)).fetchall():
            tg.send(a["tg_id"], f"↩️ Отчёт за {r['report_date']} ({bot.esc(r['facility'])}) возвращён на исправление: {bot.esc(str(b.get('reason') or ''))}")
    return {"ok": True}


@app.post("/api/reports/{report_id}/lock")
async def api_report_lock(request: Request, report_id: int):
    u = need_write(request)
    b = await jbody(request)
    with tx() as c:
        scope_check_report(c, u, report_id)
        reports.set_lock(c, report_id, bool(b.get("locked")), reports.by_staff(u), str(b.get("reason") or ""))
    return {"ok": True}


@app.post("/api/reports/{report_id}/restore")
async def api_report_restore(request: Request, report_id: int):
    u = need_write(request)
    if not u["can_edit_reports"]:
        bad("Вам не разрешено исправлять отчёты", 403)
    b = await jbody(request)
    with tx() as c:
        scope_check_report(c, u, report_id)
        return reports.restore_version(c, report_id, int(b.get("version") or 0), str(b.get("reason") or ""), reports.by_staff(u))


@app.post("/api/validate")
async def api_validate(request: Request):
    """Check figures against the rules without saving (used by the administrator's edit form)."""
    need_write(request)
    b = await jbody(request)
    c = connect()
    try:
        return rules.validate(c, b.get("values") or {}, "ru", b.get("facility_id"), b.get("date"))
    finally:
        c.close()


# ---------------------------------------------------------------- Telegram users, assignments, requests
def tg_users_scope(c, user) -> list:
    """Telegram users the person may see: all for the super administrator, otherwise those with access or a request in their regions."""
    base = """SELECT u.*, (SELECT COUNT(*) FROM assignments a WHERE a.tg_id=u.tg_id AND a.active=1) AS facilities,
                     (SELECT COUNT(*) FROM region_access ra WHERE ra.tg_id=u.tg_id AND ra.active=1) AS regions_count FROM tg_users u"""
    s, a = auth.region_filter_sql(user, "d.region_id")
    if auth.is_super(user) or not s:
        return c.execute(base + " ORDER BY u.created_at DESC LIMIT 1000").fetchall()
    s2, a2 = auth.region_filter_sql(user, "x.region_id")
    return c.execute(base + f""" WHERE u.tg_id IN (SELECT a.tg_id FROM assignments a JOIN facilities f ON f.id=a.facility_id JOIN districts d ON d.id=f.district_id WHERE {s})
                       OR u.tg_id IN (SELECT x.tg_id FROM region_access x WHERE {s2})
                       OR u.tg_id IN (SELECT x.tg_id FROM access_requests x WHERE {s2}) ORDER BY u.created_at DESC LIMIT 1000""", a + a2 + a2).fetchall()


def need_users(request: Request) -> dict:
    u = need_write(request)
    if not (auth.is_super(u) or u["can_manage_users"]):
        bad("Управление пользователями вам не разрешено", 403)
    return u


@app.get("/api/tg-users")
def api_tg_users(request: Request):
    u = need_users(request)
    c = connect()
    try:
        out = []
        for r in tg_users_scope(c, u):
            asg = [dict(x) for x in c.execute("""SELECT a.id, a.kind, a.fio, a.contact, f.id AS facility_id, f.name_ru AS facility, d.name_ru AS district, r.name_ru AS region, r.id AS region_id
                                                   FROM assignments a JOIN facilities f ON f.id=a.facility_id JOIN districts d ON d.id=f.district_id JOIN regions r ON r.id=d.region_id
                                                   WHERE a.tg_id=? AND a.active=1""", (r["tg_id"],)) if auth.sees_region(u, x["region_id"])]
            regs = [dict(x) for x in c.execute("""SELECT ra.id, ra.kind, ra.fio, ra.contact, r.id AS region_id, r.name_ru AS region FROM region_access ra JOIN regions r ON r.id=ra.region_id
                                                    WHERE ra.tg_id=? AND ra.active=1""", (r["tg_id"],)) if auth.sees_region(u, x["region_id"])]
            out.append(dict(r) | {"assignments": asg, "regions": regs})
        return {"items": out}
    finally:
        c.close()


@app.post("/api/tg-users")
async def api_tg_user_add(request: Request):
    u = need_users(request)
    b = await jbody(request)
    with tx() as c:
        people.add_tg_user(c, str(b.get("tg_id") or ""), str(b.get("name") or ""))
        if b.get("facility_id"):
            people.assign(c, u, str(b["tg_id"]), int(b["facility_id"]), b.get("kind") or "primary", str(b.get("fio") or ""), str(b.get("contact") or ""))
        elif b.get("region_id"):
            people.assign_region(c, u, str(b["tg_id"]), int(b["region_id"]), b.get("kind") or "primary", str(b.get("fio") or ""), str(b.get("contact") or ""))
    return {"ok": True}


AVATAR_FRESH_HOURS, AVATAR_NONE_HOURS = 12, 1


def _bc(fn):
    try:
        return fn()
    except broadcast.BroadcastError as e:
        bad(e.message, e.status)


@app.get("/api/broadcasts")
def api_broadcasts(request: Request):
    u = need_users(request)
    with tx() as c:
        return {"items": broadcast.listing(c, u)}


@app.post("/api/broadcasts/preview")
async def api_broadcast_preview(request: Request):
    u = need_users(request)
    b = await jbody(request)
    c = connect()
    try:
        return _bc(lambda: broadcast.preview(c, u, b.get("audience") or {}, b.get("text_ru"), b.get("text_uz")))
    finally:
        c.close()


@app.post("/api/broadcasts/test")
async def api_broadcast_test(request: Request):
    u = need_users(request)
    b = await jbody(request)
    c = connect()
    try:
        return {"sent_to": _bc(lambda: broadcast.send_test(c, u, b.get("text_ru"), b.get("text_uz"), str(b.get("tg_id") or "")))}
    finally:
        c.close()


@app.post("/api/broadcasts")
async def api_broadcast_send(request: Request):
    u = need_users(request)
    b = await jbody(request)
    if b.get("confirm") is not True:
        bad("Нужно подтверждение отправки")
    with tx() as c:
        bid = _bc(lambda: broadcast.start(c, u, b.get("audience") or {}, b.get("text_ru"), b.get("text_uz")))
    broadcast.launch(bid)
    return {"id": bid}


@app.post("/api/broadcasts/{bid}/resume")
def api_broadcast_resume(request: Request, bid: int):
    u = need_users(request)
    with tx() as c:
        _bc(lambda: broadcast.resume(c, u, bid))
    broadcast.launch(bid)
    return {"ok": True}


@app.get("/api/broadcasts/{bid}/failures")
def api_broadcast_failures(request: Request, bid: int):
    u = need_users(request)
    c = connect()
    try:
        return {"items": _bc(lambda: broadcast.failures(c, u, bid))}
    finally:
        c.close()


@app.get("/api/messages")
def api_messages(request: Request, unread: int = 0):
    """The dialogues of the facilities with the Ministry: the first message, the Ministry's answers and the person's replies. Only the super administrator sees them
    (not regional administrators, not viewers). A dialogue is unread while it has a message of the person that nobody has read."""
    need_super(request)
    c = connect()
    try:
        rows = c.execute("""SELECT m.id, m.thread_id, m.direction, m.text, m.created_at, m.read_at, m.error, m.sender, m.tg_id, m.report_date, COALESCE(st.name, st.login, '') AS staff_name,
                                   f.name_ru AS facility, d.name_ru AS district, r.name_ru AS region
                            FROM ministry_messages m JOIN facilities f ON f.id=m.facility_id JOIN districts d ON d.id=f.district_id JOIN regions r ON r.id=d.region_id
                            LEFT JOIN staff st ON st.id=m.staff_id ORDER BY m.id""").fetchall()
        threads: dict = {}
        for x in rows:
            t = threads.setdefault(x["thread_id"] or x["id"], {"thread_id": x["thread_id"] or x["id"], "messages": [], "unread": 0})
            if x["id"] == t["thread_id"]:
                t.update(region=x["region"], facility=x["facility"], report_date=x["report_date"], sender=x["sender"], tg_id=x["tg_id"])
            t["messages"].append({"id": x["id"], "direction": x["direction"], "text": x["text"], "at": x["created_at"], "error": x["error"], "by": x["staff_name"] if x["direction"] == "out" else x["sender"]})
            t["last_at"] = x["created_at"]
            if x["direction"] == "in" and not x["read_at"]:
                t["unread"] += 1
        items = [t for t in threads.values() if "facility" in t and not (unread and not t["unread"])]
        items.sort(key=lambda t: t["last_at"], reverse=True)
        return {"items": items[:300], "unread": sum(t["unread"] for t in threads.values())}
    finally:
        c.close()


@app.post("/api/messages/{tid}/read")
async def api_message_read(request: Request, tid: int):
    u = need_super(request)
    b = await jbody(request)
    with tx() as c:
        if not c.execute("SELECT 1 FROM ministry_messages WHERE thread_id=?", (tid,)).fetchone():
            bad("Диалог не найден", 404)
        c.execute("UPDATE ministry_messages SET read_at=?, read_by=? WHERE thread_id=? AND direction='in'", (now() if b.get("read", True) else "", u["id"] if b.get("read", True) else None, tid))
    return {"ok": True}


@app.post("/api/messages/{tid}/reply")
async def api_message_reply(request: Request, tid: int):
    """The Ministry's answer: kept in the dialogue and sent to the person in Telegram with a «Reply» button that continues the dialogue."""
    u = need_super(request)
    b = await jbody(request)
    text = str(b.get("text") or "").strip()
    if not text:
        bad("Напишите ответ")
    if len(text) > bot.NOTE_MAX:
        bad(f"Ответ длиннее {bot.NOTE_MAX} знаков")
    with tx() as c:
        root = c.execute("SELECT * FROM ministry_messages WHERE id=? AND (thread_id=id OR thread_id IS NULL)", (tid,)).fetchone()
        if not root:
            bad("Диалог не найден", 404)
        cur = c.execute("INSERT INTO ministry_messages(facility_id, report_date, tg_id, sender, text, created_at, direction, thread_id, staff_id, read_at) VALUES (?,?,?,?,?,?, 'out', ?, ?, ?)",
                        (root["facility_id"], root["report_date"], root["tg_id"], "", text, now(), tid, u["id"], now()))
        c.execute("UPDATE ministry_messages SET read_at=?, read_by=? WHERE thread_id=? AND direction='in' AND read_at=''", (now(), u["id"], tid))      # answering is reading
        ok, err = bot.send_ministry_reply(c, root, text)
        if not ok:
            c.execute("UPDATE ministry_messages SET error=? WHERE id=?", (err[:200] or "не доставлено", cur.lastrowid))
        audit(c, "message.reply", "message", tid, {"delivered": ok})
    return {"id": cur.lastrowid, "delivered": ok, "error": "" if ok else err}


@app.get("/api/tg-avatar/{tg_id}")
def api_tg_avatar(request: Request, tg_id: str):
    """The Telegram profile photo of a person the viewer may see. Fetched with the bot token (which never leaves the server) and kept for hours."""
    u = need_users(request)
    if not re.fullmatch(r"\d{4,15}", tg_id):
        bad("Неверный Telegram ID")
    from datetime import datetime, timedelta
    c = connect()
    try:
        if tg_id not in {r["tg_id"] for r in tg_users_scope(c, u)}:
            bad("Нет данных", 404)
        row = c.execute("SELECT data, found, fetched_at FROM tg_avatars WHERE tg_id=?", (tg_id,)).fetchone()
    finally:
        c.close()
    limit = timedelta(hours=AVATAR_FRESH_HOURS if row and row["found"] else AVATAR_NONE_HOURS)
    fresh = row and (datetime.strptime(now(), "%Y-%m-%d %H:%M:%S") - datetime.strptime(row["fetched_at"], "%Y-%m-%d %H:%M:%S")) < limit
    if not fresh:
        data = tg.profile_photo(tg_id) if tg.configured() else None          # the network call is made outside any transaction
        with tx() as c:
            c.execute("INSERT INTO tg_avatars(tg_id, data, fetched_at, found) VALUES (?,?,?,?) ON CONFLICT(tg_id) DO UPDATE SET data=excluded.data, fetched_at=excluded.fetched_at, found=excluded.found",
                      (tg_id, data, now(), 1 if data else 0))
        row = {"data": data, "found": 1 if data else 0}
    if not row["found"] or not row["data"]:
        bad("Фото нет", 404)
    return Response(bytes(row["data"]), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/preapproved")
def api_preapproved(request: Request):
    u = need_users(request)
    c = connect()
    try:
        return {"items": people.list_preapproved(c, u), "bot": tg.bot_username() if tg.configured() else ""}
    finally:
        c.close()


@app.post("/api/preapproved")
async def api_preapproved_add(request: Request):
    u = need_users(request)
    b = await jbody(request)
    with tx() as c:
        return people.preapprove(c, u, b.get("username"), q_int(b.get("region_id")) or 0, q_int(b.get("facility_id")), b.get("kind") or "primary", str(b.get("fio") or ""))


@app.delete("/api/preapproved/{pid}")
def api_preapproved_delete(request: Request, pid: int):
    u = need_users(request)
    with tx() as c:
        people.delete_preapproved(c, u, pid)
    return {"ok": True}


@app.patch("/api/tg-users/{tg_id}")
async def api_tg_user_update(request: Request, tg_id: str):
    need_users(request)
    b = await jbody(request)
    with tx() as c:
        if not c.execute("SELECT 1 FROM tg_users WHERE tg_id=?", (tg_id,)).fetchone():
            bad("Пользователь не найден", 404)
        if "active" in b:
            c.execute("UPDATE tg_users SET active=? WHERE tg_id=?", (int(bool(b["active"])), tg_id))
            audit(c, "tguser.active", "tg_user", tg_id, {"active": bool(b["active"])})
        if "name" in b:
            parts = str(b["name"]).strip().split(" ", 1)
            c.execute("UPDATE tg_users SET first_name=?, last_name=? WHERE tg_id=?", (parts[0], parts[1] if len(parts) > 1 else "", tg_id))
    return {"ok": True}


@app.post("/api/assignments")
async def api_assign(request: Request):
    u = need_users(request)
    b = await jbody(request)
    with tx() as c:
        if b.get("facility_id"):
            aid = people.assign(c, u, str(b.get("tg_id") or ""), int(b["facility_id"]), b.get("kind") or "primary", str(b.get("fio") or ""), str(b.get("contact") or ""))
        else:
            aid = people.assign_region(c, u, str(b.get("tg_id") or ""), int(b.get("region_id") or 0), b.get("kind") or "primary", str(b.get("fio") or ""), str(b.get("contact") or ""))
    return {"id": aid}


@app.delete("/api/region-access/{aid}")
def api_unassign_region(request: Request, aid: int):
    u = need_users(request)
    with tx() as c:
        people.unassign_region(c, u, aid)
    return {"ok": True}


@app.delete("/api/assignments/{aid}")
def api_unassign(request: Request, aid: int):
    u = need_users(request)
    with tx() as c:
        people.unassign(c, u, aid)
    return {"ok": True}


@app.get("/api/requests")
def api_requests(request: Request, status: str = ""):
    u = need_users(request)
    c = connect()
    try:
        return {"items": people.list_requests(c, u, status if status in ("pending", "approved", "rejected") else None)}
    finally:
        c.close()


@app.post("/api/requests/{rid}/decide")
async def api_request_decide(request: Request, rid: int):
    u = need_users(request)
    b = await jbody(request)
    with tx() as c:
        out = people.decide(c, u, rid, bool(b.get("approve")), b.get("kind") or "primary", str(b.get("fio") or ""), str(b.get("note") or ""))
    bot.notify_decision(out["tg_id"], out["facility_id"], out["approved"], out["note"], out["region_id"])
    return {"ok": True}


# ---------------------------------------------------------------- territories (super administrator)
@app.post("/api/regions")
async def api_region_create(request: Request):
    need_super(request)
    b = await jbody(request)
    name = str(b.get("name_ru") or "").strip()
    if not name:
        bad("Укажите название")
    with tx() as c:
        cur = c.execute("INSERT INTO regions(name_ru, name_uz, sort) VALUES (?,?,(SELECT COALESCE(MAX(sort),0)+1 FROM regions))", (name, str(b.get("name_uz") or "").strip()))
        audit(c, "region.create", "region", cur.lastrowid, {"name": name})
    return {"id": cur.lastrowid}


@app.patch("/api/regions/{rid}")
async def api_region_update(request: Request, rid: int):
    need_super(request)
    b = await jbody(request)
    with tx() as c:
        r = c.execute("SELECT * FROM regions WHERE id=?", (rid,)).fetchone()
        if not r:
            bad("Регион не найден", 404)
        c.execute("UPDATE regions SET name_ru=?, name_uz=?, active=? WHERE id=?", (str(b.get("name_ru", r["name_ru"])).strip() or r["name_ru"], str(b.get("name_uz", r["name_uz"])).strip(), int(bool(b.get("active", r["active"]))), rid))
        audit(c, "region.update", "region", rid, b)
    return {"ok": True}


@app.post("/api/districts")
async def api_district_create(request: Request):
    need_super(request)
    b = await jbody(request)
    name = str(b.get("name_ru") or "").strip()
    with tx() as c:
        if not name or not c.execute("SELECT 1 FROM regions WHERE id=?", (q_int(b.get("region_id")),)).fetchone():
            bad("Укажите регион и название района")
        cur = c.execute("INSERT INTO districts(region_id, name_ru, name_uz) VALUES (?,?,?)", (int(b["region_id"]), name, str(b.get("name_uz") or "").strip()))
        audit(c, "district.create", "district", cur.lastrowid, {"name": name})
    return {"id": cur.lastrowid}


@app.patch("/api/districts/{did}")
async def api_district_update(request: Request, did: int):
    need_super(request)
    b = await jbody(request)
    with tx() as c:
        r = c.execute("SELECT * FROM districts WHERE id=?", (did,)).fetchone()
        if not r:
            bad("Район не найден", 404)
        c.execute("UPDATE districts SET name_ru=?, name_uz=?, active=? WHERE id=?", (str(b.get("name_ru", r["name_ru"])).strip() or r["name_ru"], str(b.get("name_uz", r["name_uz"])).strip(), int(bool(b.get("active", r["active"]))), did))
        audit(c, "district.update", "district", did, b)
    return {"ok": True}


@app.post("/api/facilities")
async def api_facility_create(request: Request):
    need_super(request)
    b = await jbody(request)
    name = str(b.get("name_ru") or "").strip()
    with tx() as c:
        if not name or not c.execute("SELECT 1 FROM districts WHERE id=?", (q_int(b.get("district_id")),)).fetchone():
            bad("Укажите район и название учреждения")
        cur = c.execute("INSERT INTO facilities(district_id, name_ru, name_uz, contact, created_at) VALUES (?,?,?,?,?)", (int(b["district_id"]), name, str(b.get("name_uz") or "").strip(), str(b.get("contact") or "").strip(), now()))
        audit(c, "facility.create", "facility", cur.lastrowid, {"name": name})
    return {"id": cur.lastrowid}


@app.patch("/api/facilities/{fid}")
async def api_facility_update(request: Request, fid: int):
    need_super(request)
    b = await jbody(request)
    with tx() as c:
        r = c.execute("SELECT * FROM facilities WHERE id=?", (fid,)).fetchone()
        if not r:
            bad("Учреждение не найдено", 404)
        did = q_int(b.get("district_id")) or r["district_id"]
        c.execute("UPDATE facilities SET name_ru=?, name_uz=?, contact=?, active=?, district_id=? WHERE id=?",
                  (str(b.get("name_ru", r["name_ru"])).strip() or r["name_ru"], str(b.get("name_uz", r["name_uz"])).strip(), str(b.get("contact", r["contact"])).strip(), int(bool(b.get("active", r["active"]))), did, fid))
        audit(c, "facility.update", "facility", fid, b)
    return {"ok": True}


@app.delete("/api/facilities/{fid}")
def api_facility_delete(request: Request, fid: int, force: int = 0):
    need_super(request)
    with tx() as c:
        if not c.execute("SELECT 1 FROM facilities WHERE id=?", (fid,)).fetchone():
            bad("Учреждение не найдено", 404)
        n = c.execute("SELECT COUNT(*) FROM reports WHERE facility_id=?", (fid,)).fetchone()[0]
        if n and not force:
            bad(f"У учреждения есть отчёты: {n}. Подтвердите удаление вместе с ними", 409)
        return delete_facilities(c, [fid], "удаление учреждения")


@app.delete("/api/districts/{did}")
def api_district_delete(request: Request, did: int):
    need_super(request)
    with tx() as c:
        if not c.execute("SELECT 1 FROM districts WHERE id=?", (did,)).fetchone():
            bad("Район не найден", 404)
        n = c.execute("SELECT COUNT(*) FROM facilities WHERE district_id=?", (did,)).fetchone()[0]
        if n:
            bad(f"В районе учреждений: {n}. Сначала удалите их", 409)
        c.execute("DELETE FROM districts WHERE id=?", (did,))
        audit(c, "district.delete", "district", did, {})
    return {"ok": True}


@app.delete("/api/regions/{rid}")
def api_region_delete(request: Request, rid: int):
    need_super(request)
    with tx() as c:
        r = c.execute("SELECT name_ru FROM regions WHERE id=?", (rid,)).fetchone()
        if not r:
            bad("Регион не найден", 404)
        n = c.execute("SELECT COUNT(*) FROM facilities f JOIN districts d ON d.id=f.district_id WHERE d.region_id=?", (rid,)).fetchone()[0]
        if n:
            bad(f"В регионе учреждений: {n}. Сначала удалите их", 409)
        ra = c.execute("SELECT (SELECT COUNT(*) FROM region_access WHERE region_id=?) + (SELECT COUNT(*) FROM staff_scope WHERE region_id=?)", (rid, rid)).fetchone()[0]
        if ra:
            bad(f"К региону привязаны доступы ({ra}). Сначала снимите их", 409)
        c.execute("DELETE FROM districts WHERE region_id=?", (rid,))
        c.execute("DELETE FROM regions WHERE id=?", (rid,))
        audit(c, "region.delete", "region", rid, {"name": r["name_ru"]})
    return {"ok": True}


@app.post("/api/geo/import")
async def api_geo_import(request: Request, file: UploadFile = File(...), dry: int = 1):
    u = need_super(request)
    data = await file.read(10_000_001)
    if len(data) > 10_000_000:
        bad("Файл больше 10 МБ")
    with tx() as c:
        return people.import_territories(c, data, file.filename or "x.xlsx", bool(dry), u)


@app.post("/api/import/reports")
async def api_import_reports(request: Request, file: UploadFile = File(...), dry: int = 1, d_prev: str = "", d_today: str = ""):
    """Hospitals and the figures of two days from the 'places for patients' workbook (see xlsx_import)."""
    u = need_super(request)
    data = await file.read(10_000_001)
    if len(data) > 10_000_000:
        bad("Файл больше 10 МБ")
    d_today = d_today or today().isoformat()
    d_prev = d_prev or (date.fromisoformat(d_today) - timedelta(days=1)).isoformat()
    for d in (d_prev, d_today):
        reports.parse_date(d)
    with tx() as c:
        return xlsx_import.load(c, data, d_prev, d_today, bool(dry), reports.by_staff(u))


# ---------------------------------------------------------------- staff accounts (super administrator)
@app.get("/api/staff")
def api_staff(request: Request):
    need_super(request)
    c = connect()
    try:
        return {"items": [{"id": r["id"], "login": r["login"], "name": r["name"], "role": r["role"], "active": bool(r["active"]), "tg_id": r["tg_id"], "can_manage_users": bool(r["can_manage_users"]),
                           "can_edit_reports": bool(r["can_edit_reports"]), "regions": [x["region_id"] for x in c.execute("SELECT region_id FROM staff_scope WHERE staff_id=?", (r["id"],))]}
                          for r in c.execute("SELECT * FROM staff ORDER BY role, name")]}
    finally:
        c.close()


def _scope_ok(c, ids) -> list[int]:
    ids = [int(x) for x in (ids or []) if str(x).isdigit()]
    valid = {r["id"] for r in c.execute("SELECT id FROM regions")}
    return sorted(set(i for i in ids if i in valid))


@app.post("/api/staff")
async def api_staff_create(request: Request):
    need_super(request)
    b = await jbody(request)
    login = auth.norm_login(str(b.get("login") or ""))
    role = b.get("role") or "viewer"
    if len(login) < 3 or role not in auth.ROLES:
        bad("Логин: от 3 знаков (латиница, цифры, точка, дефис); роль: главный администратор, администратор или просмотр")
    password = str(b.get("password") or "")
    generated = not password
    if generated:
        password = auth.generate_password()
    elif len(password) < 8:
        bad("Пароль не короче 8 символов")
    with tx() as c:
        if c.execute("SELECT 1 FROM staff WHERE login=?", (login,)).fetchone():
            bad("Такой логин уже есть")
        cur = c.execute("INSERT INTO staff(login, name, password_hash, role, tg_id, can_manage_users, can_edit_reports, created_at) VALUES (?,?,?,?,?,?,?,?)",
                        (login, str(b.get("name") or "").strip(), auth.hash_password(password), role, str(b.get("tg_id") or "").strip(), int(bool(b.get("can_manage_users"))), int(b.get("can_edit_reports", True) is not False), now()))
        for rid in _scope_ok(c, b.get("regions")):
            c.execute("INSERT INTO staff_scope(staff_id, region_id) VALUES (?,?)", (cur.lastrowid, rid))
        audit(c, "staff.create", "staff", cur.lastrowid, {"login": login, "role": role})
    return {"id": cur.lastrowid, "password": password if generated else None}


@app.patch("/api/staff/{sid}")
async def api_staff_update(request: Request, sid: int):
    u = need_super(request)
    b = await jbody(request)
    with tx() as c:
        r = c.execute("SELECT * FROM staff WHERE id=?", (sid,)).fetchone()
        if not r:
            bad("Пользователь не найден", 404)
        role = b.get("role", r["role"])
        active = int(bool(b.get("active", r["active"])))
        if role not in auth.ROLES:
            bad("Неизвестная роль")
        if sid == u["id"] and (role != "super_admin" or not active):
            bad("Нельзя понизить или отключить самого себя")
        if r["role"] == "super_admin" and (role != "super_admin" or not active) and c.execute("SELECT COUNT(*) FROM staff WHERE role='super_admin' AND active=1 AND id != ?", (sid,)).fetchone()[0] == 0:
            bad("Должен остаться хотя бы один активный главный администратор")
        c.execute("UPDATE staff SET name=?, role=?, active=?, tg_id=?, can_manage_users=?, can_edit_reports=? WHERE id=?",
                  (str(b.get("name", r["name"])).strip(), role, active, str(b.get("tg_id", r["tg_id"])).strip(), int(bool(b.get("can_manage_users", r["can_manage_users"]))), int(bool(b.get("can_edit_reports", r["can_edit_reports"]))), sid))
        if "regions" in b:
            c.execute("DELETE FROM staff_scope WHERE staff_id=?", (sid,))
            for rid in _scope_ok(c, b["regions"]):
                c.execute("INSERT INTO staff_scope(staff_id, region_id) VALUES (?,?)", (sid, rid))
        if not active:
            c.execute("DELETE FROM sessions WHERE staff_id=?", (sid,))
        audit(c, "staff.update", "staff", sid, {k: v for k, v in b.items() if k != "password"})
    return {"ok": True}


@app.post("/api/staff/{sid}/password")
async def api_staff_password(request: Request, sid: int):
    need_super(request)
    b = await jbody(request)
    password = str(b.get("password") or "")
    generated = not password
    if generated:
        password = auth.generate_password()
    elif len(password) < 8:
        bad("Пароль не короче 8 символов")
    with tx() as c:
        if not c.execute("UPDATE staff SET password_hash=? WHERE id=?", (auth.hash_password(password), sid)).rowcount:
            bad("Пользователь не найден", 404)
        if sid != me(request)["id"]:
            c.execute("DELETE FROM sessions WHERE staff_id=?", (sid,))
        audit(c, "staff.password", "staff", sid, {})
    return {"password": password if generated else None}


@app.post("/api/me/password")
async def api_my_password(request: Request):
    b = await jbody(request)
    u = me(request)
    c = connect()
    try:
        row = c.execute("SELECT password_hash FROM staff WHERE id=?", (u["id"],)).fetchone()
    finally:
        c.close()
    if not auth.verify_password(str(b.get("old") or ""), row["password_hash"]):
        bad("Текущий пароль неверен")
    new = str(b.get("new") or "")
    if len(new) < 8:
        bad("Новый пароль не короче 8 символов")
    with tx() as c:
        c.execute("UPDATE staff SET password_hash=? WHERE id=?", (auth.hash_password(new), u["id"]))
        audit(c, "staff.password", "staff", u["id"], {"self": True})
    return {"ok": True}


# ---------------------------------------------------------------- indicators, rules, settings (super administrator)
@app.get("/api/indicators")
def api_indicators(request: Request):
    need_super(request)
    c = connect()
    try:
        return {"items": [dict(r) for r in c.execute("SELECT * FROM indicators ORDER BY sort")], "rules": [dict(r) for r in c.execute("SELECT * FROM rules ORDER BY sort, id")]}
    finally:
        c.close()


@app.post("/api/indicators")
async def api_indicator_create(request: Request):
    need_super(request)
    b = await jbody(request)
    code = re.sub(r"[^a-z0-9_]", "", str(b.get("code") or "").lower())
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", code) or code in ("occupancy", "beds_free", "n", "reported"):
        bad("Код: латиница, цифры, подчёркивание, начинается с буквы (2–40 знаков)")
    name = str(b.get("name_ru") or "").strip()
    if not name or b.get("agg", "sum") not in ("sum", "last", "max"):
        bad("Укажите название и способ сложения (sum / last / max)")
    with tx() as c:
        if c.execute("SELECT 1 FROM indicators WHERE code=?", (code,)).fetchone():
            bad("Такой код уже есть")
        c.execute("INSERT INTO indicators(code, grp, name_ru, name_uz, hint_ru, hint_uz, agg, sort) VALUES (?,?,?,?,?,?,?,(SELECT COALESCE(MAX(sort),0)+1 FROM indicators))",
                  (code, "extra", name, str(b.get("name_uz") or "").strip(), str(b.get("hint_ru") or "").strip(), str(b.get("hint_uz") or "").strip(), b.get("agg", "sum")))
        audit(c, "indicator.create", "indicator", code, {"name": name})
    return {"code": code}


@app.patch("/api/indicators/{code}")
async def api_indicator_update(request: Request, code: str):
    need_super(request)
    b = await jbody(request)
    with tx() as c:
        r = c.execute("SELECT * FROM indicators WHERE code=?", (code,)).fetchone()
        if not r:
            bad("Показатель не найден", 404)
        agg = b.get("agg", r["agg"])
        if agg not in ("sum", "last", "max"):
            bad("Способ сложения: sum / last / max")
        active = int(bool(b.get("active", r["active"])))
        if r["core"] and not active:
            bad("Основной показатель нельзя отключить: на нём построены расчёты")
        c.execute("UPDATE indicators SET name_ru=?, name_uz=?, hint_ru=?, hint_uz=?, agg=?, active=?, sort=? WHERE code=?",
                  (str(b.get("name_ru", r["name_ru"])).strip() or r["name_ru"], str(b.get("name_uz", r["name_uz"])).strip(), str(b.get("hint_ru", r["hint_ru"])).strip(), str(b.get("hint_uz", r["hint_uz"])).strip(),
                   agg, active, int(b.get("sort", r["sort"])), code))
        audit(c, "indicator.update", "indicator", code, b)
    return {"ok": True}


def _rule_fields(c, b: dict, rule=None) -> dict:
    expr = str(b.get("expr", rule["expr"] if rule else "")).strip()
    codes = {r["code"] for r in c.execute("SELECT code FROM indicators")}
    try:
        rules.parse(expr, codes)
    except rules.RuleError as e:
        bad(str(e))
    kind = b.get("kind", rule["kind"] if rule else "error")
    if kind not in ("error", "warning"):
        bad("Вид правила: error или warning")
    msg = str(b.get("message_ru", rule["message_ru"] if rule else "")).strip()
    if not msg:
        bad("Укажите текст сообщения (можно вставлять {код_показателя})")
    return {"expr": expr, "kind": kind, "message_ru": msg, "message_uz": str(b.get("message_uz", rule["message_uz"] if rule else "")).strip(),
            "active": int(bool(b.get("active", rule["active"] if rule else 1)))}


@app.post("/api/rules")
async def api_rule_create(request: Request):
    need_super(request)
    b = await jbody(request)
    with tx() as c:
        f = _rule_fields(c, b)
        cur = c.execute("INSERT INTO rules(kind, expr, message_ru, message_uz, active, sort) VALUES (?,?,?,?,?,(SELECT COALESCE(MAX(sort),0)+1 FROM rules))", (f["kind"], f["expr"], f["message_ru"], f["message_uz"], f["active"]))
        audit(c, "rule.create", "rule", cur.lastrowid, f)
    return {"id": cur.lastrowid}


@app.patch("/api/rules/{rid}")
async def api_rule_update(request: Request, rid: int):
    need_super(request)
    b = await jbody(request)
    with tx() as c:
        r = c.execute("SELECT * FROM rules WHERE id=?", (rid,)).fetchone()
        if not r:
            bad("Правило не найдено", 404)
        f = _rule_fields(c, b, r)
        c.execute("UPDATE rules SET kind=?, expr=?, message_ru=?, message_uz=?, active=? WHERE id=?", (f["kind"], f["expr"], f["message_ru"], f["message_uz"], f["active"], rid))
        audit(c, "rule.update", "rule", rid, f)
    return {"ok": True}


@app.delete("/api/rules/{rid}")
def api_rule_delete(request: Request, rid: int):
    need_super(request)
    with tx() as c:
        r = c.execute("SELECT core FROM rules WHERE id=?", (rid,)).fetchone()
        if not r:
            bad("Правило не найдено", 404)
        if r["core"]:
            bad("Основное правило из ТЗ можно отключить, но не удалить")
        c.execute("DELETE FROM rules WHERE id=?", (rid,))
        audit(c, "rule.delete", "rule", rid, {})
    return {"ok": True}


@app.post("/api/rules/test")
async def api_rule_test(request: Request):
    need_super(request)
    b = await jbody(request)
    c = connect()
    try:
        codes = {r["code"] for r in c.execute("SELECT code FROM indicators")}
    finally:
        c.close()
    try:
        tree = rules.parse(str(b.get("expr") or ""), codes)
    except rules.RuleError as e:
        return {"ok": False, "error": str(e)}
    vals = {k: v for k, v in (b.get("values") or {}).items() if isinstance(v, (int, float))}
    return {"ok": True, "result": rules.evaluate(tree, vals), "names": sorted(tree._names)}   # type: ignore[attr-defined]


NUM = {"deadline_day_offset": (0, 3), "backfill_days": (0, 14), "edit_window_hours": (0, 720), "lock_after_days": (0, 60), "occ_elevated": (1, 100), "occ_critical": (1, 100),
       "fac_occ_warn": (1, 100), "growth_warn_pct": (1, 1000), "growth_crit_pct": (1, 1000), "severe_growth_pct": (1, 1000), "hosp_growth_pct": (1, 1000)}
TIMES = ("deadline_time", "admin_summary_time", "admin_overdue_time")


@app.get("/api/settings")
def api_settings(request: Request):
    need_super(request)
    c = connect()
    try:
        out = all_settings(c)
    finally:
        c.close()
    return {"settings": {k: v for k, v in out.items() if k not in ("tg_offset", "tg_seen", "tg_error", "tg_bot")}, "bot": {"configured": tg.configured(), "username": out.get("tg_bot", ""), "error": out.get("tg_error", ""), "seen": out.get("tg_seen", "")}}


@app.put("/api/settings")
async def api_settings_put(request: Request):
    need_super(request)
    b = await jbody(request)
    values = {}
    for k, v in b.items():
        v = str(v).strip()
        if k in NUM:
            if not v.lstrip("-").isdigit() or not NUM[k][0] <= int(v) <= NUM[k][1]:
                bad(f"{k}: допустимо от {NUM[k][0]} до {NUM[k][1]}")
        elif k in TIMES:
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
                bad("Время в формате ЧЧ:ММ")
        elif k == "remind_times":
            if v and not all(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", x.strip()) for x in v.split(",")):
                bad("Времена напоминаний через запятую в формате ЧЧ:ММ")
            v = ",".join(sorted(x.strip() for x in v.split(",") if x.strip()))
        elif k == "remind_weekdays":
            days = sorted({x.strip() for x in v.split(",") if x.strip()})
            if not days or not all(d in "1234567" and len(d) == 1 for d in days):
                bad("Дни недели: числа от 1 (пн) до 7 (вс) через запятую")
            v = ",".join(days)
        elif k in ("remind_enabled", "allow_user_edit"):
            v = "1" if v in ("1", "true", "True") else "0"
        elif k == "default_lang":
            if v not in ("ru", "uz"):
                bad("Язык: ru или uz")
        elif k == "org_title":
            v = v[:200]
        else:
            continue
        values[k] = v
    if float(values.get("occ_elevated", all_settings().get("occ_elevated", 70))) >= float(values.get("occ_critical", all_settings().get("occ_critical", 85))):
        bad("Порог «повышенная нагрузка» должен быть ниже порога «критическая загрузка»")
    with tx() as c:
        for k, v in values.items():
            c.execute("INSERT INTO settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
        audit(c, "settings.update", "settings", "", values)
    return {"ok": True}


@app.post("/api/notify/run")
async def api_notify_run(request: Request):
    need_super(request)
    b = await jbody(request)
    res = notify.run_due(force=bool(b.get("force")), dry=bool(b.get("dry")))
    return {"items": res}


@app.post("/api/notify/remind")
async def api_notify_remind(request: Request):
    """Button 'remind those who have not reported'. dry=true only shows who would get a message."""
    u = need_write(request)
    b = await jbody(request)
    rid = q_int(b.get("region_id"))
    check_region(u, rid)
    d = str(b.get("date") or today().isoformat())
    reports.parse_date(d)
    c = connect()
    try:
        return notify.remind_now(c, u, d, rid, bool(b.get("dry", True)))
    finally:
        c.close()


@app.get("/api/notify/log")
def api_notify_log(request: Request):
    need_super(request)
    c = connect()
    try:
        return {"items": [dict(r) for r in c.execute("SELECT l.*, u.first_name, u.last_name FROM notify_log l LEFT JOIN tg_users u ON u.tg_id=l.tg_id ORDER BY l.id DESC LIMIT 100")]}
    finally:
        c.close()


@app.get("/api/audit")
def api_audit(request: Request, limit: int = 200, entity: str = ""):
    need_super(request)
    c = connect()
    try:
        sql, a = "SELECT * FROM audit", []
        if entity:
            sql += " WHERE entity=?"; a.append(entity)
        return {"items": [dict(r) for r in c.execute(sql + " ORDER BY id DESC LIMIT ?", a + [max(1, min(limit, 500))])]}
    finally:
        c.close()


@app.post("/api/backup")
def api_backup(request: Request):
    need_super(request)
    return {"file": backup.make_now()}


# ---------------------------------------------------------------- exports
@app.get("/api/export")
def api_export(request: Request, fmt: str = "xlsx", kind: str = "custom"):
    u = me(request)
    f = filters(request)
    check_scope_filters(u, f)
    d1, d2 = period(request)
    c = connect()
    try:
        if fmt == "xlsx":
            data, mime = exports.xlsx(c, u, d1, d2, kind=kind, **f), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif fmt == "pdf":
            data, mime = exports.pdf(c, u, d1, d2, kind=kind, **f), "application/pdf"
        elif fmt == "csv":
            data, mime = exports.csv_bytes(c, u, d1, d2, **f), "text/csv; charset=utf-8"
        else:
            bad("Формат: xlsx, pdf или csv")
        audit(c, "export", "export", fmt, {"d1": d1, "d2": d2, **f})
        c.commit()
    finally:
        c.close()
    name = f"flu_{d1}" + ("" if d1 == d2 else f"_{d2}") + "." + fmt
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})
