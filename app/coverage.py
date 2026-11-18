"""Coverage: for every region, district and facility, who is connected (the responsible people with their Telegram) and how many reports were sent in a period."""
import io
from datetime import date, timedelta

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import auth
from .db import today


def _name(r) -> str:
    return " ".join(x for x in (r["first_name"], r["last_name"]) if x) or (("@" + r["username"]) if r["username"] else r["tg_id"])


def person(r, kind: str, via: str) -> dict:
    return {"tg_id": r["tg_id"], "name": _name(r), "username": r["username"] or "", "kind": kind, "via": via, "active": bool(r["active"]), "last_seen": r["last_seen"] or ""}


def build(c, user, d1: str, d2: str) -> dict:
    """{period, days, totals, regions: [{id, name, districts: [{id, name, facilities: [...]}], people (the whole-region access), ...counters}]}, limited to the regions the user sees."""
    days = (date.fromisoformat(d2) - date.fromisoformat(d1)).days + 1
    sent = {r["facility_id"]: r for r in c.execute("SELECT facility_id, COUNT(*) n, SUM(status='returned') ret, MAX(report_date) last FROM reports WHERE report_date BETWEEN ? AND ? GROUP BY facility_id", (d1, d2))}
    ever = {r["facility_id"]: r["last"] for r in c.execute("SELECT facility_id, MAX(report_date) last FROM reports GROUP BY facility_id")}
    on_fac: dict = {}
    for r in c.execute("""SELECT a.facility_id, a.kind, u.tg_id, u.first_name, u.last_name, u.username, u.active, u.last_seen FROM assignments a JOIN tg_users u ON u.tg_id=a.tg_id
                          WHERE a.active=1 ORDER BY (a.kind='primary') DESC, u.first_name"""):
        on_fac.setdefault(r["facility_id"], []).append(person(r, r["kind"], "facility"))
    on_reg: dict = {}
    for r in c.execute("""SELECT ra.region_id, ra.kind, u.tg_id, u.first_name, u.last_name, u.username, u.active, u.last_seen FROM region_access ra JOIN tg_users u ON u.tg_id=ra.tg_id
                          WHERE ra.active=1 ORDER BY (ra.kind='primary') DESC, u.first_name"""):
        on_reg.setdefault(r["region_id"], []).append(person(r, r["kind"], "region"))
    waiting: dict = {}
    for r in c.execute("SELECT region_id, COUNT(*) n FROM preapproved WHERE used_at='' GROUP BY region_id"):
        waiting[r["region_id"]] = r["n"]
    regions = []
    for rg in c.execute("SELECT id, name_ru FROM regions WHERE active=1 ORDER BY sort, id"):
        if not auth.sees_region(user, rg["id"]):
            continue
        districts, people_ids, nfac, nrep, with_resp = [], set(), 0, 0, 0
        for d in c.execute("SELECT id, name_ru FROM districts WHERE region_id=? AND active=1 ORDER BY name_ru", (rg["id"],)):
            facs = []
            for f in c.execute("SELECT id, name_ru FROM facilities WHERE district_id=? AND active=1 ORDER BY name_ru", (d["id"],)):
                ppl = list(on_fac.get(f["id"], []))
                s = sent.get(f["id"])
                have = bool(ppl or on_reg.get(rg["id"]))
                facs.append({"id": f["id"], "name": f["name_ru"], "people": ppl, "reports": s["n"] if s else 0, "returned": (s["ret"] or 0) if s else 0, "last_in_period": s["last"] if s else "",
                             "last_ever": ever.get(f["id"], ""), "has_responsible": have})
                nfac += 1; nrep += facs[-1]["reports"]; with_resp += 1 if have else 0
                people_ids |= {p["tg_id"] for p in ppl}
            districts.append({"id": d["id"], "name": d["name_ru"], "facilities": facs, "reports": sum(x["reports"] for x in facs), "people": len({p["tg_id"] for x in facs for p in x["people"]})})
        reg_people = on_reg.get(rg["id"], [])
        people_ids |= {p["tg_id"] for p in reg_people}
        regions.append({"id": rg["id"], "name": rg["name_ru"], "districts": districts, "region_people": reg_people, "waiting": waiting.get(rg["id"], 0), "n_districts": len(districts), "facilities": nfac,
                        "people": len(people_ids), "with_responsible": with_resp, "reports": nrep, "possible": nfac * days})
    tot = {"regions": len(regions), "districts": sum(r["n_districts"] for r in regions), "facilities": sum(r["facilities"] for r in regions), "reports": sum(r["reports"] for r in regions),
           "people": len({p["tg_id"] for r in regions for d in r["districts"] for f in d["facilities"] for p in f["people"]} | {p["tg_id"] for r in regions for p in r["region_people"]}),
           "with_responsible": sum(r["with_responsible"] for r in regions), "waiting": sum(r["waiting"] for r in regions), "possible": sum(r["possible"] for r in regions)}
    return {"d1": d1, "d2": d2, "days": days, "totals": tot, "regions": regions}


def xlsx(data: dict) -> bytes:
    """The same coverage as a flat table: one row per facility."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Охват"
    ws.append([f"Охват и отчёты с {data['d1']} по {data['d2']}"])
    ws["A1"].font = Font(bold=True, size=13)
    head = ["Регион", "Район", "Учреждение", "Ответственные (Telegram)", "Доступ ко всему региону", "Отчётов за период", "Возвращено", "Возможно за период", "Последний отчёт"]
    ws.append([])
    ws.append(head)
    for col in range(1, len(head) + 1):
        cell = ws.cell(row=3, column=col)
        cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="3B6CF6"); cell.alignment = Alignment(wrap_text=True, vertical="center")
    for r in data["regions"]:
        reg_people = "; ".join(p["name"] + (f" (@{p['username']})" if p["username"] else "") for p in r["region_people"])
        for d in r["districts"]:
            for f in d["facilities"]:
                ppl = "; ".join(p["name"] + (f" (@{p['username']})" if p["username"] else "") + (" [резерв]" if p["kind"] == "reserve" else "") for p in f["people"])
                ws.append([r["name"], d["name"], f["name"], ppl, reg_people, f["reports"], f["returned"], data["days"], f["last_ever"] or ""])
    ws.append([])
    t = data["totals"]
    ws.append(["Итого", f"районов: {t['districts']}", f"учреждений: {t['facilities']}", f"подключено людей: {t['people']}", "", t["reports"], "", t["possible"], ""])
    for i, w in enumerate((26, 20, 40, 46, 40, 16, 12, 18, 16), 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A4"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
