"""Forecast and early warning (§8). Everything is computed from the collected statistics and every forecast says how it was
made and how reliable it is. It is a tool of operational planning, not an epidemiological conclusion."""
from datetime import date, timedelta
from math import sqrt

from . import auth, stats
from .db import all_settings, today

METHOD = "Линейный тренд (метод наименьших квадратов) по последним дням с данными; значения не ниже нуля"
WINDOW = 14


def linreg(xs: list[float], ys: list[float]):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my, 0.0, 0.0
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1 - ss_res / ss_tot if ss_tot else 1.0
    se = sqrt(ss_res / (n - 2)) if n > 2 else 0.0
    return b, a, r2, se


def reliability(n: int, r2: float) -> tuple[str, str]:
    if n < 5:
        return "low", "Низкая: данных меньше 5 дней"
    if n >= 10 and r2 >= 0.6:
        return "high", f"Высокая: {n} дней данных, тренд устойчив (R² = {r2:.2f})"
    return "medium", f"Средняя: {n} дней данных, R² = {r2:.2f}"


def project(series: dict[str, float], ref: date, horizon: int = 7) -> dict:
    """series: {iso date: value}. The next `horizon` days after the latest date with data."""
    pts = sorted(series.items())[-WINDOW:]
    n = len(pts)
    if n < 2:
        return {"n": n, "ok": False, "reliability": "low", "reliability_text": "Низкая: данных недостаточно для прогноза", "method": METHOD}
    last = date.fromisoformat(pts[-1][0])
    xs = [(date.fromisoformat(d) - last).days for d, _ in pts]
    ys = [float(v) for _, v in pts]
    b, a, r2, se = linreg(xs, ys)
    days = []
    for h in range(1, horizon + 1):
        y = max(a + b * h, 0.0)
        days.append({"date": (last + timedelta(days=h)).isoformat(), "value": round(y, 1), "low": round(max(y - 1.64 * se, 0), 1), "high": round(y + 1.64 * se, 1)})
    level, text = reliability(n, r2)
    return {"n": n, "ok": True, "current": ys[-1], "current_date": last.isoformat(), "slope": round(b, 2), "days": days, "reliability": level, "reliability_text": text, "r2": round(r2, 2), "method": METHOD}


def series_of(tot: dict, code: str) -> dict:
    return {d: t[code] for d, t in tot.items() if code in t}


def overview(c, user, ref: str | None = None, region_id=None, district_id=None, facility_id=None) -> dict:
    """Forecast of visits, severe, extreme, hospitalisations, discharges and of the bed load for 3 and 7 days."""
    ref_d = date.fromisoformat(ref) if ref else today()
    tot = stats.daily_totals(c, user, (ref_d - timedelta(days=WINDOW + 3)).isoformat(), ref_d.isoformat(), region_id, district_id, facility_id)
    out = {"ref": ref_d.isoformat(), "metrics": {}, "beds": None}
    for code in ("visits", "severe", "extreme", "hosp", "disch"):
        out["metrics"][code] = project(series_of(tot, code), ref_d)
    if tot:
        lastd = max(tot)
        t = tot[lastd]
        occ0, flu = t.get("beds_occupied", 0), t.get("beds_flu", 0)
        h, dis = out["metrics"]["hosp"], out["metrics"]["disch"]
        if h.get("ok") and dis.get("ok") and flu:
            run, days = occ0, []
            for i in range(7):
                run = max(run + h["days"][i]["value"] - dis["days"][i]["value"], 0)
                days.append({"date": h["days"][i]["date"], "occupied": round(run, 1), "free": round(flu - run, 1), "occupancy": round(100 * run / flu, 1), "deficit": round(max(run - flu, 0), 1)})
            lvl = min((h, dis), key=lambda m: {"low": 0, "medium": 1, "high": 2}[m["reliability"]])
            out["beds"] = {"current_date": lastd, "occupied": occ0, "beds_flu": flu, "days": days, "reliability": lvl["reliability"], "reliability_text": lvl["reliability_text"],
                           "method": "Занятые койки сегодня + прогноз госпитализаций − прогноз выписок за каждый следующий день"}
    return out


def _growth(tot: dict, code: str, ref_d: date, mode: str = "sum") -> tuple[float | None, float, float]:
    """(growth %, previous, last) of the last 3 days against the previous 3 days; None without enough data."""
    def win(a, b):
        return [tot[(ref_d - timedelta(days=i)).isoformat()][code] for i in range(a, b) if (ref_d - timedelta(days=i)).isoformat() in tot and code in tot[(ref_d - timedelta(days=i)).isoformat()]]
    last, prev = win(0, 3), win(3, 6)
    if len(last) < 2 or len(prev) < 2:
        return None, 0, 0
    f = (lambda x: sum(x)) if mode == "sum" else (lambda x: sum(x) / len(x))
    a, b = f(prev), f(last)
    if len(last) != len(prev) and mode == "sum":
        a, b = a / len(prev), b / len(last)
    return (None if a == 0 else round(100 * (b - a) / a, 1)), round(a, 1), round(b, 1)


def alerts(c, user, ref: str | None = None) -> list[dict]:
    """The warnings of §8.3 for the regions of the person: growth, severe cases, hospitalisations, occupancy, bed shortage, missing reports."""
    st = all_settings(c)
    ref_d = date.fromisoformat(ref) if ref else today()
    names = {r["id"]: r["name_ru"] for r in c.execute("SELECT id, name_ru FROM regions WHERE active=1 ORDER BY sort")}
    out = []

    def add(level, kind, scope, text, **kw):
        out.append({"level": level, "kind": kind, "scope": scope, "text": text, **kw})

    for rid, name in names.items():
        if not auth.sees_region(user, rid):
            continue
        tot = stats.daily_totals(c, user, (ref_d - timedelta(days=WINDOW)).isoformat(), ref_d.isoformat(), rid)
        if not tot:
            continue
        for code, label, key, mode, absmin in (("visits", "обращений", "growth_warn_pct", "sum", 0), ("severe", "тяжёлых пациентов", "severe_growth_pct", "mean", 1),
                                               ("extreme", "крайне тяжёлых пациентов", "severe_growth_pct", "mean", 2), ("hosp", "госпитализаций", "hosp_growth_pct", "sum", 0)):
            g, a, b = _growth(tot, code, ref_d, mode)
            if g is None or abs(b - a) < absmin:
                continue
            crit = float(st["growth_crit_pct"])
            if g >= float(st[key]):
                add("critical" if g >= crit else "warning", "growth_" + code, name,
                    f"{'Внимание! ' if g < crit else 'Тревога! '}В регионе «{name}» за последние 3 дня отмечается увеличение количества {label} на {g:g}% относительно предыдущего сопоставимого периода ({a:g} → {b:g}).",
                    region_id=rid, value=g)
        lastd = max(tot)
        t = tot[lastd]
        occ = t.get("occupancy")
        if occ is not None:
            if occ >= float(st["occ_critical"]):
                add("critical", "occupancy", name, f"Критическая загрузка коек: в регионе «{name}» занято {occ:g}% коек для больных гриппом (на {lastd}).", region_id=rid, value=occ)
            elif occ >= float(st["occ_elevated"]):
                add("warning", "occupancy", name, f"Повышенная нагрузка: в регионе «{name}» занято {occ:g}% коек для больных гриппом (на {lastd}).", region_id=rid, value=occ)
        ov = overview(c, user, ref_d.isoformat(), rid)
        b = ov.get("beds")
        if b:
            d3 = b["days"][2]
            if d3["deficit"] > 0 or d3["occupancy"] >= 100:
                add("critical", "bed_risk", name, f"Риск нехватки коек: в регионе «{name}» через 3 дня ожидается потребность {d3['occupied']:g} коек при {b['beds_flu']:g} выделенных. Надёжность прогноза: {b['reliability_text'].split(':')[0].lower()}.", region_id=rid, value=d3["occupancy"])
    # facilities with a very high occupancy on the latest day
    last = stats.latest_date(c, user, ref_d.isoformat())
    if last:
        thr = float(st["fac_occ_warn"])
        for fid, t in stats.aggregate(c, user, last, last, "facility").items():
            if t.get("occupancy") is not None and t["occupancy"] >= thr:
                f = c.execute("SELECT f.name_ru, r.name_ru AS region FROM facilities f JOIN districts d ON d.id=f.district_id JOIN regions r ON r.id=d.region_id WHERE f.id=?", (fid,)).fetchone()
                add("warning", "facility_occupancy", f["region"], f"Предупреждение! В учреждении «{f['name_ru']}» ({f['region']}) занято {t['occupancy']:g}% коек, выделенных для госпитализации больных гриппом.", facility_id=fid, value=t["occupancy"])
    out.sort(key=lambda a: (0 if a["level"] == "critical" else 1, a["scope"]))
    return out


def missing_reports_alerts(c, user, d: str, st: dict | None = None) -> list[dict]:
    """After the deadline: how many facilities have not reported, by region."""
    from . import reports
    st = st or all_settings(c)
    ctl = reports.control(c, user, d, st=st)
    if not ctl["overdue"]:
        return []
    by = {}
    for r in ctl["rows"]:
        if r["state"] == "overdue":
            by.setdefault(r["region"], []).append(r["facility"])
    return [{"level": "warning", "kind": "missing_report", "scope": reg, "text": f"Нет отчёта за {d} от {len(f)} учреждений региона «{reg}».", "count": len(f)} for reg, f in sorted(by.items())]
