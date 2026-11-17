import pytest
from conftest import make_facility, put_report


def test_rules_block_and_warn(env):
    from app import rules
    from app.db import connect
    c = connect()
    ok = dict(beds_total=100, beds_flu=40, beds_occupied=20, visits=50, severe=5, severe_pregnant=1, severe_children=1, extreme=1, extreme_pregnant=0, extreme_children=0, hosp=10, disch=6)
    assert rules.validate(c, ok, "ru", None, None)["errors"] == []
    bad = dict(ok, beds_occupied=41)
    assert rules.validate(c, bad, "ru", None, None)["errors"]
    bad = dict(ok, severe=60)
    assert rules.validate(c, bad, "ru", None, None)["errors"]
    warn = dict(ok, hosp=80)
    r = rules.validate(c, warn, "ru", None, None)
    assert r["errors"] == [] and r["warnings"]


def test_rule_parser_rejects_code(env):
    from app import rules
    for e in ("__import__('os').system('x')", "beds_flu.__class__", "open('f')", "a if b else c"):
        with pytest.raises(rules.RuleError):
            rules.parse(e, {"beds_flu", "a", "b", "c"})


def test_report_unique_and_versions(env):
    from app import reports
    from app.db import connect, tx
    fid = make_facility()
    put_report(fid, "2026-02-10")
    out = put_report(fid, "2026-02-10", visits=60)
    c = connect()
    assert c.execute("SELECT COUNT(*) FROM reports WHERE facility_id=?", (fid,)).fetchone()[0] == 1
    rep = c.execute("SELECT id, version FROM reports WHERE facility_id=?", (fid,)).fetchone()
    assert rep["version"] == 2
    got = reports.get_report(c, rep["id"])
    assert got["values"]["visits"] == 60 and len(got["versions"]) == 2 and got["corrected"]
    with pytest.raises(Exception):
        with tx() as cc:
            cc.execute("UPDATE report_versions SET reason='x'")
    with pytest.raises(Exception):
        with tx() as cc:
            cc.execute("DELETE FROM audit")


def test_admin_edit_needs_reason(env):
    from app import reports
    from app.db import tx
    fid = make_facility()
    put_report(fid, "2026-02-10")
    with pytest.raises(reports.ReportError):
        with tx() as c:
            reports.admin_save(c, fid, "2026-02-10", {"visits": 5, "beds_total": 100, "beds_flu": 40, "beds_occupied": 20, "severe": 1, "severe_pregnant": 0, "severe_children": 0, "extreme": 0, "extreme_pregnant": 0, "extreme_children": 0, "hosp": 1, "disch": 1}, "", {"kind": "staff", "id": 1, "name": "a"})


def test_control_states(env):
    from app import reports
    from app.db import connect
    f1, f2 = make_facility(fac="A"), make_facility(fac="B")
    put_report(f1, "2026-02-10")
    c = connect()
    u = {"id": 1, "role": "super_admin", "regions": None}
    r = reports.control(c, u, "2026-02-10")
    st = {x["facility"]: x["state"] for x in r["rows"]}
    assert st["A"] == "sent" and st["B"] == "not_sent"      # 12:00 is before the 18:00 deadline
    r = reports.control(c, u, "2026-02-09")
    assert {x["state"] for x in r["rows"]} == {"overdue"}


def test_stats_and_regions_scope(env):
    from app import stats
    from app.db import connect
    f1, f2 = make_facility(1, fac="A"), make_facility(2, "Район Б", "B")
    put_report(f1, "2026-02-10", visits=10)
    put_report(f2, "2026-02-10", visits=30)
    c = connect()
    sup = {"id": 1, "role": "super_admin", "regions": None}
    reg = {"id": 2, "role": "admin", "regions": [1]}
    assert stats.kpis(c, sup, "2026-02-10", "2026-02-10")["totals"]["visits"] == 40
    k = stats.kpis(c, reg, "2026-02-10", "2026-02-10")
    assert k["totals"]["visits"] == 10 and k["totals"]["occupancy"] == 50.0 and k["totals"]["beds_free"] == 20


def test_forecast_reliability(env):
    from app import forecast
    from app.db import connect
    f = make_facility()
    for i in range(1, 4):
        put_report(f, f"2026-02-0{i}", visits=10 * i)
    c = connect()
    u = {"id": 1, "role": "super_admin", "regions": None}
    o = forecast.overview(c, u, "2026-02-03")
    assert o["metrics"]["visits"]["reliability"] == "low" and o["metrics"]["visits"]["ok"]
    assert o["metrics"]["visits"]["days"][0]["value"] > 30


def test_clear_data_removes_test_reports_and_facilities(env):
    from app import cli, db
    cli.demo()
    c = db.connect()
    assert c.execute("SELECT COUNT(*) FROM reports").fetchone()[0] > 0
    c.close()
    assert cli.clear_data(keep_facilities=True, yes=False) == 0          # a dry run changes nothing
    c = db.connect(); assert c.execute("SELECT COUNT(*) FROM reports").fetchone()[0] > 0; c.close()
    assert cli.clear_data(keep_facilities=True, yes=True) == 0
    c = db.connect()
    assert c.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 0 and c.execute("SELECT COUNT(*) FROM report_versions").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM facilities").fetchone()[0] > 0
    assert cli.clear_data(yes=True) == 0
    c.close(); c = db.connect()
    assert c.execute("SELECT COUNT(*) FROM facilities").fetchone()[0] == 0 and c.execute("SELECT COUNT(*) FROM regions").fetchone()[0] == 14
    assert c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'versions_no_%'").fetchone()[0] == 2   # the protection is back
    c.close()
