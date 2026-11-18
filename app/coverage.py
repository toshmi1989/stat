"""Coverage: for every region, district and facility, who is connected (the responsible people with their Telegram) and how many reports were sent in a period."""
import io
from datetime import date, timedelta

from openpyxl import Workbook
from openpyxl.worksheet.properties import PageSetupProperties
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
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
    pend_req: dict = {}
    requests = []
    for r in c.execute("""SELECT q.region_id, q.created_at, u.tg_id, u.first_name, u.last_name, u.username, rg.name_ru AS region, f.name_ru AS facility FROM access_requests q JOIN tg_users u ON u.tg_id=q.tg_id
                          JOIN regions rg ON rg.id=q.region_id LEFT JOIN facilities f ON f.id=q.facility_id WHERE q.status='pending' ORDER BY q.id"""):
        if auth.sees_region(user, r["region_id"]):
            pend_req[r["region_id"]] = pend_req.get(r["region_id"], 0) + 1
            requests.append({"region_id": r["region_id"], "region": r["region"], "name": _name(r), "username": r["username"] or "", "tg_id": r["tg_id"], "facility": r["facility"] or "", "created_at": r["created_at"]})
    waiting_list = [dict(region_id=r["region_id"], region=r["region"], username=r["username"], facility=r["facility"] or "", kind=r["kind"], fio=r["fio"], created_at=r["created_at"])
                    for r in c.execute("""SELECT p.region_id, p.username, p.kind, p.fio, p.created_at, rg.name_ru AS region, f.name_ru AS facility FROM preapproved p JOIN regions rg ON rg.id=p.region_id
                                          LEFT JOIN facilities f ON f.id=p.facility_id WHERE p.used_at='' ORDER BY p.id""") if auth.sees_region(user, r["region_id"])]
    no_responsible, people_rows = [], []
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
                if not have:
                    no_responsible.append({"region": rg["name_ru"], "district": d["name_ru"], "facility": f["name_ru"], "last_ever": ever.get(f["id"], "")})
                people_ids |= {p["tg_id"] for p in ppl}
            districts.append({"id": d["id"], "name": d["name_ru"], "facilities": facs, "reports": sum(x["reports"] for x in facs), "people": len({p["tg_id"] for x in facs for p in x["people"]})})
        reg_people = on_reg.get(rg["id"], [])
        people_ids |= {p["tg_id"] for p in reg_people}
        for p in reg_people:                                           # one row per person and region: the whole region, or the list of facilities
            people_rows.append({"region": rg["name_ru"], **p, "scope": "весь регион", "facilities": ""})
        by_person: dict = {}
        for d in districts:
            for f in d["facilities"]:
                for p in f["people"]:
                    by_person.setdefault(p["tg_id"], {"p": p, "facs": []})["facs"].append(f["name"])
        for v in by_person.values():
            people_rows.append({"region": rg["name_ru"], **v["p"], "scope": f"учреждений: {len(v['facs'])}", "facilities": "; ".join(v["facs"])})
        regions.append({"id": rg["id"], "name": rg["name_ru"], "districts": districts, "region_people": reg_people, "waiting": waiting.get(rg["id"], 0), "n_districts": len(districts), "facilities": nfac,
                        "people": len(people_ids), "with_responsible": with_resp, "reports": nrep, "possible": nfac * days, "requests": pend_req.get(rg["id"], 0)})
    tot = {"regions": len(regions), "districts": sum(r["n_districts"] for r in regions), "facilities": sum(r["facilities"] for r in regions), "reports": sum(r["reports"] for r in regions),
           "people": len({p["tg_id"] for r in regions for d in r["districts"] for f in d["facilities"] for p in f["people"]} | {p["tg_id"] for r in regions for p in r["region_people"]}),
           "with_responsible": sum(r["with_responsible"] for r in regions), "waiting": sum(r["waiting"] for r in regions), "possible": sum(r["possible"] for r in regions)}
    tot["requests"] = len(requests)
    return {"d1": d1, "d2": d2, "days": days, "totals": tot, "regions": regions, "no_responsible": no_responsible, "waiting_list": waiting_list, "requests": requests, "people_rows": people_rows}


BLUE, GREEN, AMBER, RED, GREY = "3B6CF6", "DCF5E7", "FFF1D6", "FBE0E0", "EEF1F7"


def _sheet(wb, first: bool, title: str, note: str, head: list, rows: list, widths: list, total: list | None = None, pct_col: int | None = None, zero_bad_cols: tuple = ()):
    ws = wb.active if first else wb.create_sheet()
    ws.title = title
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = note
    ws["A2"].font = Font(italic=True, color="666666")
    ws["A2"].alignment = Alignment(wrap_text=False)
    ws.append([])
    ws.append(head)
    hr = ws.max_row
    for col in range(1, len(head) + 1):
        c = ws.cell(row=hr, column=col)
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor=BLUE); c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center" if col > 1 else "left")
    ws.row_dimensions[hr].height = 54
    thin = Side(style="thin", color="D5DAE5")
    for r in rows:
        ws.append(r)
        row = ws.max_row
        for col in range(1, len(head) + 1):
            cell = ws.cell(row=row, column=col)
            cell.border = Border(bottom=thin)
            cell.alignment = Alignment(vertical="top", wrap_text=isinstance(cell.value, str) and len(cell.value) > 40, horizontal="center" if isinstance(cell.value, (int, float)) else "left")
        if pct_col:                                                    # the share of reports sent: green / amber / red
            v = ws.cell(row=row, column=pct_col)
            if isinstance(v.value, (int, float)):
                v.fill = PatternFill("solid", fgColor=GREEN if v.value >= 80 else AMBER if v.value >= 40 else RED)
        for col in zero_bad_cols:                                      # a zero here is the thing to look at
            v = ws.cell(row=row, column=col)
            if v.value == 0:
                v.fill = PatternFill("solid", fgColor=RED)
    if total:
        ws.append(total)
        for col in range(1, len(head) + 1):
            c = ws.cell(row=ws.max_row, column=col)
            c.font = Font(bold=True); c.fill = PatternFill("solid", fgColor=GREY); c.alignment = Alignment(horizontal="center" if col > 1 else "left")
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row=hr + 1, column=2)
    ws.sheet_view.zoomScale = 110
    ws.page_setup.orientation = "landscape"                       # printing: landscape, the whole width on one page
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    return ws


def xlsx(data: dict) -> bytes:
    """A workbook of four sheets: «Сводка» (one row per region: districts, facilities, people, who is not connected), «Не подключены», «Люди», «По учреждениям»."""
    wb = Workbook()
    t, days = data["totals"], data["days"]
    period = f"Период: {data['d1']} — {data['d2']} ({days} дн.)"
    pct = lambda a, b: round(100 * a / b) if b else 0
    rows = [[r["name"], r["n_districts"], r["facilities"], r["people"], len(r["region_people"]), r["with_responsible"], r["facilities"] - r["with_responsible"], r["waiting"], r["requests"], r["reports"], r["possible"], pct(r["reports"], r["possible"])]
            for r in data["regions"]]
    _sheet(wb, True, "Сводка", period + ". Подключён: человек, который открыл бота и получил доступ. «Без ответственного»: учреждение, за которое никто не отвечает.",
           ["Регион", "Районов", "Учреждений", "Подключено людей", "из них доступ ко всему региону", "Учреждений с ответственным", "Учреждений БЕЗ ответственного", "Записаны, ещё не вошли в бот", "Заявки на доступ (ждут решения)", "Отчётов за период",
            "Возможно (учреждения × дни)", "Сдача, %"],
           rows, [30, 13, 17, 17, 19, 19, 19, 19, 19, 15, 21, 11],
           total=["ИТОГО", t["districts"], t["facilities"], t["people"], sum(len(r["region_people"]) for r in data["regions"]), t["with_responsible"], t["facilities"] - t["with_responsible"], t["waiting"], t["requests"], t["reports"], t["possible"], pct(t["reports"], t["possible"])],
           pct_col=12, zero_bad_cols=(4,))
    ws = _sheet(wb, False, "Не подключены", "Кого ещё нет в системе: учреждения без ответственного, люди, которых записали, но они не заходили в бот, и заявки, которые ждут решения.",
                ["Кто / что", "Регион", "Район", "Учреждение или доступ", "Контакт Telegram", "Когда записан / подал заявку"], [], [30, 28, 20, 44, 24, 22])
    def block(title, items):
        ws.append([title]); ws.cell(row=ws.max_row, column=1).font = Font(bold=True, color=BLUE, size=12)
        for it in items:
            ws.append(it)
        if not items:
            ws.append(["— нет —"]); ws.cell(row=ws.max_row, column=1).font = Font(italic=True, color="888888")
        ws.append([])
    block(f"Учреждения без ответственного ({len(data['no_responsible'])})", [["Учреждение", x["region"], x["district"], x["facility"], "", ("последний отчёт: " + x["last_ever"]) if x["last_ever"] else "отчётов не было"] for x in data["no_responsible"]])
    block(f"Записаны заранее и ещё не вошли в бот ({len(data['waiting_list'])})", [["Человек", x["region"], "", x["facility"] or "весь регион", "@" + x["username"], x["created_at"]] for x in data["waiting_list"]])
    block(f"Заявки на доступ, ждут решения ({len(data['requests'])})", [["Заявка", x["region"], "", x["facility"] or "весь регион", (x["name"] + (f" (@{x['username']})" if x["username"] else "")), x["created_at"]] for x in data["requests"]])
    _sheet(wb, False, "Люди", "Все подключённые люди: по строке на человека и регион.",
           ["Регион", "Человек", "@username", "Telegram ID", "Вид", "Доступ", "Учреждения", "Бот включён", "Последняя активность"],
           [[x["region"], x["name"], ("@" + x["username"]) if x["username"] else "", x["tg_id"], "резерв" if x["kind"] == "reserve" else "основной", x["scope"], x["facilities"], "да" if x["active"] else "нет", x["last_seen"]] for x in data["people_rows"]],
           [28, 28, 20, 14, 12, 18, 60, 12, 20])
    rows = []
    for r in data["regions"]:
        reg_people = "; ".join(p["name"] + (f" (@{p['username']})" if p["username"] else "") for p in r["region_people"])
        for d in r["districts"]:
            for f in d["facilities"]:
                ppl = "; ".join(p["name"] + (f" (@{p['username']})" if p["username"] else "") + (" [резерв]" if p["kind"] == "reserve" else "") for p in f["people"])
                rows.append([r["name"], d["name"], f["name"], ppl or ("через доступ к региону" if reg_people else "НЕ ПОДКЛЮЧЁН"), reg_people, f["reports"], f["returned"], days, f["last_ever"] or ""])
    _sheet(wb, False, "По учреждениям", period, ["Регион", "Район", "Учреждение", "Ответственные (Telegram)", "Доступ ко всему региону", "Отчётов за период", "Возвращено", "Дней в периоде", "Последний отчёт"],
           rows, [28, 20, 40, 46, 40, 14, 12, 12, 16])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
