"""Numbers for the dashboards: totals, regions with drill-down, dynamics, bed balance, admissions vs discharges.

Two kinds of figures. A flow (visits, hospitalisations, discharges) is added over the days of a period. A state (beds, patients
in severe condition) is taken on the latest day of the period for each facility. Which is which is a property of the indicator
(aggregation sum / last / max), editable in the settings."""
from collections import defaultdict
from datetime import date, timedelta

from . import auth
from .db import all_settings, today


def _where(user, region_id=None, district_id=None, facility_id=None):
    w, a = ["f.active=1", "d.active=1", "r.active=1"], []
    sql, args = auth.region_filter_sql(user, "r.id")
    if sql:
        w.append(sql); a += args
    for col, v in (("r.id", region_id), ("d.id", district_id), ("f.id", facility_id)):
        if v:
            w.append(f"{col}=?"); a.append(int(v))
    return " AND ".join(w), a


def indicators(c) -> list:
    # Switched-off questions stay in the analytics: the history that was collected under them must not vanish.
    return c.execute("SELECT * FROM indicators ORDER BY sort").fetchall()


def facility_count(c, user, region_id=None, district_id=None, facility_id=None) -> int:
    w, a = _where(user, region_id, district_id, facility_id)
    return c.execute(f"SELECT COUNT(*) FROM facilities f JOIN districts d ON d.id=f.district_id JOIN regions r ON r.id=d.region_id WHERE {w}", a).fetchone()[0]


def load(c, user, d1: str, d2: str, region_id=None, district_id=None, facility_id=None) -> dict:
    """{facility_id: {date: {code: value}}} for the reports of the visible facilities in [d1, d2], plus a map facility -> (district, region)."""
    w, a = _where(user, region_id, district_id, facility_id)
    rows = c.execute(f"""SELECT rep.facility_id AS fid, d.id AS did, r.id AS rid, rep.report_date AS dt, v.code AS code, v.value AS val
                         FROM reports rep JOIN facilities f ON f.id=rep.facility_id JOIN districts d ON d.id=f.district_id JOIN regions r ON r.id=d.region_id
                         JOIN report_values v ON v.report_id=rep.id
                         WHERE {w} AND rep.report_date BETWEEN ? AND ?""", a + [d1, d2]).fetchall()
    data: dict[int, dict[str, dict]] = defaultdict(lambda: defaultdict(dict))
    where_is: dict[int, tuple] = {}
    for r in rows:
        data[r["fid"]][r["dt"]][r["code"]] = r["val"]
        where_is[r["fid"]] = (r["did"], r["rid"])
    return {"data": data, "where": where_is}


def facility_totals(days: dict, inds) -> dict:
    """The figures of one facility over its days: flows added, states from the latest day, maxima."""
    out = {}
    for i in inds:
        vals = [(dt, v[i["code"]]) for dt, v in days.items() if i["code"] in v]
        if not vals:
            continue
        out[i["code"]] = (sum(x for _, x in vals) if i["agg"] == "sum" else max(x for _, x in vals) if i["agg"] == "max" else max(vals)[1])
    return out


def stay_days(c) -> int:
    try:
        return max(1, min(30, int(float(all_settings(c).get("stay_days", 5)))))
    except (TypeError, ValueError):
        return 5


def occupied_estimate(days: dict, last: str, stay: int):
    """The occupied beds of a facility on its latest day, counted from the admissions of patients with flu and ARVI over the last `stay` days
    (a patient who came less than the average stay ago is still in hospital). None when the facility did not report those admissions."""
    lo = (date.fromisoformat(last) - timedelta(days=stay - 1)).isoformat()
    vals = [v["hosp_flu"] for dt, v in days.items() if lo <= dt <= last and "hosp_flu" in v]
    return sum(vals) if vals else None


def derive(t: dict) -> dict:
    t["occ_estimated"] = t.get("occ_est_n", 0) > 0          # the occupied beds are counted from the admissions, not reported
    flu = t.get("beds_flu", 0)
    if "beds_occupied" not in t:  # nobody reported occupied beds (the question is switched off): no occupancy, no free beds
        t["beds_free"], t["occupancy"] = None, None
        return t
    occ = t["beds_occupied"]
    t["beds_free"] = max(flu - occ, 0)
    t["occupancy"] = round(100 * occ / flu, 1) if flu else None
    return t


def add(total: dict, part: dict, inds) -> None:
    for i in inds:
        if i["code"] in part:
            total[i["code"]] = total.get(i["code"], 0) + part[i["code"]]


def aggregate(c, user, d1: str, d2: str, group: str = "all", region_id=None, district_id=None, facility_id=None) -> dict:
    """{key: {code: value, 'beds_free', 'occupancy', 'reported'}} grouped by 'all' | 'region' | 'district' | 'facility'."""
    inds = indicators(c)
    stay = stay_days(c)
    ld = load(c, user, (date.fromisoformat(d1) - timedelta(days=stay - 1)).isoformat(), d2, region_id, district_id, facility_id)     # a few days before the period: for the estimate
    groups: dict = defaultdict(dict)
    n = defaultdict(int)
    for fid, days in ld["data"].items():
        inside = {dt: v for dt, v in days.items() if d1 <= dt <= d2}
        if not inside:
            continue
        did, rid = ld["where"][fid]
        key = "all" if group == "all" else rid if group == "region" else did if group == "district" else fid
        ft = facility_totals(inside, inds)
        add(groups[key], ft, inds)
        n[key] += 1
        est = occupied_estimate(days, max(inside), stay) if "beds_occupied" not in ft else None
        if est is not None:                                   # nobody reported the occupied beds of this facility: they are counted from the admissions
            g = groups[key]
            g["beds_occupied"] = g.get("beds_occupied", 0) + est
            g["occ_est_n"] = g.get("occ_est_n", 0) + 1
    for k, t in groups.items():
        derive(t)
        t["reported"] = n[k]
    return dict(groups)


def kpis(c, user, d1: str, d2: str, region_id=None, district_id=None, facility_id=None) -> dict:
    t = aggregate(c, user, d1, d2, "all", region_id, district_id, facility_id).get("all") or derive({})
    total = facility_count(c, user, region_id, district_id, facility_id)
    reported = t.get("reported", 0)
    return {"facilities": total, "reported": reported, "not_reported": max(total - reported, 0), "totals": t,
            "d1": d1, "d2": d2}


def latest_date(c, user, upto: str | None = None) -> str | None:
    w, a = _where(user)
    sql = f"SELECT MAX(rep.report_date) FROM reports rep JOIN facilities f ON f.id=rep.facility_id JOIN districts d ON d.id=f.district_id JOIN regions r ON r.id=d.region_id WHERE {w}"
    if upto:
        sql += " AND rep.report_date <= ?"; a.append(upto)
    return c.execute(sql, a).fetchone()[0]


def regions_table(c, user, d1: str, d2: str, level: str = "region", parent_id: int | None = None) -> dict:
    """Rows for the comparison table: regions; then the districts of a region; then the facilities of a district (drill-down)."""
    st = all_settings(c)
    if level == "region":
        names = {r["id"]: r["name_ru"] for r in c.execute("SELECT id, name_ru FROM regions WHERE active=1")}
        agg = aggregate(c, user, d1, d2, "region")
        counts = {r["rid"]: r["n"] for r in c.execute("SELECT d.region_id AS rid, COUNT(*) n FROM facilities f JOIN districts d ON d.id=f.district_id WHERE f.active=1 AND d.active=1 GROUP BY d.region_id")}
        ids = [i for i in names if (user["regions"] is None or i in user["regions"])]
    elif level == "district":
        names = {r["id"]: r["name_ru"] for r in c.execute("SELECT id, name_ru FROM districts WHERE active=1 AND region_id=?", (parent_id,))}
        agg = aggregate(c, user, d1, d2, "district", region_id=parent_id)
        counts = {r["did"]: r["n"] for r in c.execute("SELECT f.district_id AS did, COUNT(*) n FROM facilities f WHERE f.active=1 GROUP BY f.district_id")}
        ids = list(names) if user["regions"] is None or parent_id in user["regions"] else []
    elif level == "rfac":       # all the facilities of a region at once (the district level is skipped: most regions have a single district)
        names, district = {}, {}
        for r in c.execute("SELECT f.id, f.name_ru, d.name_ru AS district FROM facilities f JOIN districts d ON d.id=f.district_id WHERE f.active=1 AND d.active=1 AND d.region_id=? ORDER BY f.name_ru", (parent_id,)):
            names[r["id"]], district[r["id"]] = r["name_ru"], r["district"]
        agg = aggregate(c, user, d1, d2, "facility", region_id=parent_id)
        counts = {i: 1 for i in names}
        ids = list(names) if user["regions"] is None or parent_id in user["regions"] else []
    else:
        names = {r["id"]: r["name_ru"] for r in c.execute("SELECT id, name_ru FROM facilities WHERE active=1 AND district_id=?", (parent_id,))}
        agg = aggregate(c, user, d1, d2, "facility", district_id=parent_id)
        counts = {i: 1 for i in names}
        ids = list(names)
        ok = c.execute("SELECT region_id FROM districts WHERE id=?", (parent_id,)).fetchone()
        if not ok or not auth.sees_region(user, ok["region_id"]):
            ids = []
    rows = []
    for i in ids:
        t = agg.get(i) or derive({})
        occ = t.get("occupancy")
        rows.append({"id": i, "name": names[i], "district": (district.get(i) if level == "rfac" else None), "facilities": counts.get(i, 0), "reported": t.get("reported", 0), "values": t, "level_state": occupancy_state(occ, st)})
    return {"level": level, "parent_id": parent_id, "rows": rows, "d1": d1, "d2": d2}


def occupancy_state(occ, st: dict) -> str:
    """normal / elevated / critical by the thresholds of the settings; 'none' when no beds are reported."""
    if occ is None:
        return "none"
    return "critical" if occ >= float(st["occ_critical"]) else "elevated" if occ >= float(st["occ_elevated"]) else "normal"


def daily_totals(c, user, d1: str, d2: str, region_id=None, district_id=None, facility_id=None) -> dict:
    """{date: {code: sum over the facilities that reported that day, 'n': how many reported}} (a day with no reports is absent)."""
    inds = indicators(c)
    ld = load(c, user, d1, d2, region_id, district_id, facility_id)
    out: dict = defaultdict(lambda: {"n": 0})
    for fid, days in ld["data"].items():
        for dt, vals in days.items():
            out[dt]["n"] += 1
            add(out[dt], vals, inds)
    for t in out.values():
        derive(t)
    return dict(out)


def daterange(d1: str, d2: str) -> list[str]:
    a, b = date.fromisoformat(d1), date.fromisoformat(d2)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)] if b >= a else []


def dynamics(c, user, d1: str, d2: str, metrics: list[str], region_ids: list[int] | None = None, district_id=None, facility_id=None) -> dict:
    """Daily series of the chosen metrics for the whole scope, or for each chosen region (comparison)."""
    dates = daterange(d1, d2)
    if len(dates) > 400:
        dates = dates[-400:]
    out = {"dates": dates, "series": []}
    scopes = [(None, "Все выбранные")] if not region_ids else [(i, None) for i in region_ids]
    names = {r["id"]: r["name_ru"] for r in c.execute("SELECT id, name_ru FROM regions")}
    for rid, label in scopes:
        tot = daily_totals(c, user, dates[0], dates[-1], rid, district_id, facility_id) if dates else {}
        for m in metrics:
            out["series"].append({"key": f"{m}:{rid or 'all'}", "metric": m, "region_id": rid, "name": label or names.get(rid, str(rid)),
                                  "points": [(tot[d].get(m) if d in tot else None) for d in dates]})
    return out


def bed_balance(c, user, d1: str, d2: str, level: str = "region", parent_id=None) -> dict:
    st = all_settings(c)
    table = regions_table(c, user, d1, d2, level, parent_id)
    rows = []
    for r in table["rows"]:
        v = r["values"]
        rows.append({"id": r["id"], "name": r["name"], "beds_flu": v.get("beds_flu", 0), "occupied": v.get("beds_occupied", 0), "free": v.get("beds_free", 0),
                     "occupancy": v.get("occupancy"), "state": r["level_state"], "reported": r["reported"], "facilities": r["facilities"]})
    rows.sort(key=lambda x: (x["occupancy"] is None, -(x["occupancy"] or 0)))
    hot = []
    thr = float(st["fac_occ_warn"])
    for fid, t in aggregate(c, user, d1, d2, "facility").items():
        if t.get("occupancy") is not None and t["occupancy"] >= thr:
            f = c.execute("SELECT f.name_ru, d.name_ru AS district, r.name_ru AS region FROM facilities f JOIN districts d ON d.id=f.district_id JOIN regions r ON r.id=d.region_id WHERE f.id=?", (fid,)).fetchone()
            hot.append({"facility_id": fid, "name": f["name_ru"], "district": f["district"], "region": f["region"], "occupancy": t["occupancy"], "free": t["beds_free"], "beds_flu": t.get("beds_flu", 0)})
    hot.sort(key=lambda x: -x["occupancy"])
    return {"estimated": any(r["values"].get("occ_estimated") for r in table["rows"]), "stay_days": stay_days(c), "rows": rows, "hot": hot[:50], "thresholds": {"elevated": float(st["occ_elevated"]), "critical": float(st["occ_critical"]), "facility": thr}, "d1": d1, "d2": d2}


def hosp_disch(c, user, d1: str, d2: str, region_id=None, district_id=None, facility_id=None) -> dict:
    dates = daterange(d1, d2)
    tot = daily_totals(c, user, d1, d2, region_id, district_id, facility_id)
    rows, prev_occ = [], None
    for d in dates:
        t = tot.get(d)
        if not t:
            rows.append({"date": d, "hosp": None, "disch": None, "diff": None, "occupied": None, "occ_change": None, "occupancy": None})
            continue
        occ = t.get("beds_occupied")
        rows.append({"date": d, "hosp": t.get("hosp"), "disch": t.get("disch"), "diff": (t.get("hosp", 0) - t.get("disch", 0)), "occupied": occ,
                     "occ_change": None if prev_occ is None or occ is None else occ - prev_occ, "occupancy": t.get("occupancy")})
        prev_occ = occ if occ is not None else prev_occ
    return {"rows": rows}
