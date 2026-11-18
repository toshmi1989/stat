"""Summary reports (§10): Excel with three sheets and print setup, PDF for printing, CSV for processing. Every export obeys the
filters (period, region, district, facility) and the rights of the person who asks. Signature fields are at the end."""
import csv
import io
import os
from datetime import date, datetime, timedelta

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import stats
from .db import TZ, all_settings

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
PERIOD_NAMES = {"daily": "Ежедневный сводный отчёт", "weekly": "Недельный сводный отчёт", "monthly": "Месячный сводный отчёт", "custom": "Сводный отчёт за период"}
# column definitions of the detail table: (title, code or special key)
BASE_COLS = [("Всего коек", "beds_total"), ("Выделено для гриппа и ОРВИ", "beds_flu"), ("Обращения", "visits"), ("Госпитализации", "hosp"), ("Выписки", "disch"), ("Занято коек", "beds_occupied"),
             ("в т.ч. беременные", "occ_pregnant"), ("в т.ч. дети", "occ_children"), ("Тяжёлые", "severe"), ("Крайне тяжёлые", "extreme"), ("из них беременные", "extreme_pregnant"),
             ("из них дети", "extreme_children"), ("Свободные койки", "beds_free")]


def _names(c):
    fac = {r["id"]: (r["region"], r["district"], r["name"]) for r in c.execute(
        "SELECT f.id, r.name_ru AS region, d.name_ru AS district, f.name_ru AS name FROM facilities f JOIN districts d ON d.id=f.district_id JOIN regions r ON r.id=d.region_id")}
    return fac


def columns(c) -> list[tuple[str, str]]:
    """The base columns (when the indicator is active) and every other active indicator after them: new figures appear in exports automatically."""
    active = {r["code"]: r for r in c.execute("SELECT code, name_ru FROM indicators WHERE active=1")}
    cols = [(t, code) for t, code in BASE_COLS if code in active or code == "beds_free"]
    known = {code for _, code in BASE_COLS}
    cols += [(r["name_ru"], r["code"]) for r in c.execute("SELECT code, name_ru FROM indicators WHERE active=1 ORDER BY sort") if r["code"] not in known]
    return cols


def describe(c, region_id, district_id, facility_id) -> str:
    parts = []
    if region_id:
        parts.append("Регион: " + (c.execute("SELECT name_ru FROM regions WHERE id=?", (region_id,)).fetchone() or ["?"])[0])
    if district_id:
        parts.append("Район: " + (c.execute("SELECT name_ru FROM districts WHERE id=?", (district_id,)).fetchone() or ["?"])[0])
    if facility_id:
        parts.append("Учреждение: " + (c.execute("SELECT name_ru FROM facilities WHERE id=?", (facility_id,)).fetchone() or ["?"])[0])
    return "; ".join(parts) or "Вся доступная территория"


def build(c, user, d1: str, d2: str, region_id=None, district_id=None, facility_id=None) -> dict:
    cols = columns(c)
    fac = _names(c)
    agg = stats.aggregate(c, user, d1, d2, "facility", region_id, district_id, facility_id)
    rows = []
    for fid, t in sorted(agg.items(), key=lambda kv: fac.get(kv[0], ("", "", ""))):
        reg, dist, name = fac[fid]
        rows.append({"region": reg, "district": dist, "facility": name, "v": t})
    total = {}
    for r in rows:
        for code, v in r["v"].items():
            if code not in ("occupancy", "reported"):
                total[code] = total.get(code, 0) + v
    total["occupancy"] = round(100 * total.get("beds_occupied", 0) / total["beds_flu"], 1) if total.get("beds_flu") else None
    by_region = stats.aggregate(c, user, d1, d2, "region", region_id, district_id, facility_id)
    rnames = {r["id"]: r["name_ru"] for r in c.execute("SELECT id, name_ru FROM regions")}
    regions = [{"name": rnames[k], "v": v} for k, v in sorted(by_region.items(), key=lambda kv: kv[0])]
    days = stats.daterange(d1, d2)
    tot = stats.daily_totals(c, user, d1, d2, region_id, district_id, facility_id)
    span = len(days)
    prev = stats.daily_totals(c, user, (date.fromisoformat(d1) - timedelta(days=span)).isoformat(), (date.fromisoformat(d1) - timedelta(days=1)).isoformat(), region_id, district_id, facility_id) if span else {}
    dyn = [{"date": d, "v": tot.get(d)} for d in days]
    prev_sum = {k: sum(t.get(k, 0) for t in prev.values()) for k in ("visits", "hosp", "disch")}
    cur_sum = {k: sum(t.get(k, 0) for t in tot.values()) for k in ("visits", "hosp", "disch")}
    return {"cols": cols, "rows": rows, "total": total, "regions": regions, "dynamics": dyn, "prev": prev_sum, "cur": cur_sum, "d1": d1, "d2": d2,
            "facilities_total": stats.facility_count(c, user, region_id, district_id, facility_id), "reported": total and len(rows),
            "filters": describe(c, region_id, district_id, facility_id), "settings": all_settings(c)}


def _val(v: dict, code: str):
    return v.get(code, None)


# ---------------------------------------------------------------- Excel
THIN = Side(style="thin", color="888888")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD_FILL = PatternFill("solid", fgColor="DCE6F1")
TOTAL_FILL = PatternFill("solid", fgColor="F2F2F2")


def _sheet_title(ws, title: str, period: str, filters: str, org: str, width: int) -> int:
    ws["A1"] = org
    ws["A1"].font = Font(bold=True, size=11)
    ws["A2"] = title
    ws["A2"].font = Font(bold=True, size=14)
    ws["A3"] = "Отчётный период: " + period + ".   " + filters
    ws["A4"] = "Дата формирования: " + datetime.now(TZ).strftime("%d.%m.%Y %H:%M")
    for r in (1, 2, 3, 4):
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=max(width, 4))
    return 6


def _signatures(ws, row: int, width: int) -> None:
    row += 2
    for label in ("Составил: ____________________________", "Проверил: ____________________________", "Утвердил: ____________________________", "Дата: ____________________________", "Подпись: ____________________________"):
        ws.cell(row=row, column=1, value=label).font = Font(size=11)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=max(width, 4))
        row += 2


def _print(ws, header_row: int, last_col: int, landscape: bool = True) -> None:
    ws.page_setup.paperSize = 9   # A4
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{header_row}:{header_row}"
    ws.print_area = f"A1:{get_column_letter(last_col)}{ws.max_row}"
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = ws.page_margins.bottom = 0.5
    ws.oddFooter.center.text = "Страница &P из &N"


def _table(ws, start: int, heads: list[str], body: list[list], total: list | None, widths: list[int] | None = None) -> int:
    for j, h in enumerate(heads, 1):
        cell = ws.cell(row=start, column=j, value=h)
        cell.font, cell.fill, cell.border = Font(bold=True), HEAD_FILL, BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[start].height = 48
    r = start
    for row in body:
        r += 1
        for j, v in enumerate(row, 1):
            cell = ws.cell(row=r, column=j, value=v)
            cell.border = BORDER
            if isinstance(v, (int, float)):
                cell.number_format = "#,##0" if isinstance(v, int) else "0.0"
                cell.alignment = Alignment(horizontal="right")
    if total:
        r += 1
        for j, v in enumerate(total, 1):
            cell = ws.cell(row=r, column=j, value=v)
            cell.font, cell.fill, cell.border = Font(bold=True), TOTAL_FILL, BORDER
            if isinstance(v, (int, float)):
                cell.number_format = "#,##0" if isinstance(v, int) else "0.0"
    ws.freeze_panes = ws.cell(row=start + 1, column=4 if len(heads) > 6 else 2)
    ws.auto_filter.ref = f"A{start}:{get_column_letter(len(heads))}{r - (1 if total else 0)}"
    for j, w in enumerate(widths or [], 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    return r


def xlsx(c, user, d1, d2, region_id=None, district_id=None, facility_id=None, kind: str = "custom") -> bytes:
    b = build(c, user, d1, d2, region_id, district_id, facility_id)
    org, cols = b["settings"]["org_title"], b["cols"]
    period = d1 if d1 == d2 else f"{d1} — {d2}"
    title = PERIOD_NAMES.get(kind, PERIOD_NAMES["custom"]) + " по гриппу и ОРВИ"
    wb = Workbook()
    # ---- sheet 1: the summary
    ws = wb.active
    ws.title = "Сводная информация"
    t = b["total"]
    r0 = _sheet_title(ws, title, period, b["filters"], org, 9)
    ws.cell(row=r0, column=1, value="Основные показатели").font = Font(bold=True)
    head = [("Учреждений в системе", b["facilities_total"]), ("Предоставили отчёт", b["reported"] or 0), ("Не предоставили", max(b["facilities_total"] - (b["reported"] or 0), 0)),
            ("Обращения", t.get("visits", 0)), ("Госпитализации", t.get("hosp", 0)), ("Выписки", t.get("disch", 0)), ("Тяжёлые пациенты", t.get("severe", 0)),
            ("Крайне тяжёлые пациенты", t.get("extreme", 0)), ("Выделено коек для гриппа и ОРВИ", t.get("beds_flu", 0)), ("Занято коек", t.get("beds_occupied", 0)),
            ("Свободные койки", t.get("beds_free", 0)), ("Занятость коечного фонда, %", t.get("occupancy"))]
    r = r0 + 1
    for k, v in head:
        ws.cell(row=r, column=1, value=k).border = BORDER
        ws.cell(row=r, column=2, value=v if v is not None else "—").border = BORDER
        r += 1
    r += 1
    ws.cell(row=r, column=1, value="Итоги по регионам").font = Font(bold=True)
    heads = ["№", "Регион", "Отчётов", "Обращения", "Тяжёлые", "Крайне тяжёлые", "Госпитализации", "Выписки", "Выделено коек", "Занято", "Свободные койки", "Занятость, %"]
    body = [[i, x["name"], x["v"].get("reported", 0), x["v"].get("visits", 0), x["v"].get("severe", 0), x["v"].get("extreme", 0), x["v"].get("hosp", 0), x["v"].get("disch", 0),
             x["v"].get("beds_flu", 0), x["v"].get("beds_occupied", 0), x["v"].get("beds_free", 0), x["v"].get("occupancy")] for i, x in enumerate(b["regions"], 1)]
    total = ["", "ИТОГО", sum(x[2] for x in body), sum(x[3] for x in body), sum(x[4] for x in body), sum(x[5] for x in body), sum(x[6] for x in body), sum(x[7] for x in body),
             sum(x[8] for x in body), sum(x[9] for x in body), sum(x[10] for x in body), t.get("occupancy")]
    end = _table(ws, r + 1, heads, body, total, [34, 30, 12, 12, 12, 14, 14, 12, 14, 12, 14, 14])
    _signatures(ws, end, len(heads))
    _print(ws, r + 1, len(heads))
    # ---- sheet 2: the detail by facility
    ws2 = wb.create_sheet("Детальная информация")
    heads2 = ["№", "Регион", "Район", "Учреждение"] + [x for x, _ in cols]
    r0 = _sheet_title(ws2, title + ": по учреждениям", period, b["filters"], org, len(heads2))
    body2 = [[i, x["region"], x["district"], x["facility"]] + [_val(x["v"], code) if _val(x["v"], code) is not None else "" for _, code in cols] for i, x in enumerate(b["rows"], 1)]
    total2 = ["", "ИТОГО", "", ""] + [t.get(code) if t.get(code) is not None else "" for _, code in cols]
    widths = [5, 26, 24, 38] + [13] * len(cols)
    end = _table(ws2, r0, heads2, body2, total2, widths)
    _signatures(ws2, end, len(heads2))
    _print(ws2, r0, len(heads2))
    # ---- sheet 3: the dynamics
    ws3 = wb.create_sheet("Динамика")
    heads3 = ["Дата", "Отчётов", "Обращения", "Тяжёлые", "Крайне тяжёлые", "Госпитализации", "Выписки", "Госпит. − выписки", "Занято коек", "Свободные койки", "Занятость, %"]
    r0 = _sheet_title(ws3, "Динамика показателей", period, b["filters"], org, len(heads3))
    body3 = []
    for x in b["dynamics"]:
        v = x["v"]
        body3.append([x["date"], (v or {}).get("n", 0), (v or {}).get("visits", ""), (v or {}).get("severe", ""), (v or {}).get("extreme", ""), (v or {}).get("hosp", ""), (v or {}).get("disch", ""),
                      (v["hosp"] - v["disch"]) if v and "hosp" in v and "disch" in v else "", (v or {}).get("beds_occupied", ""), (v or {}).get("beds_free", ""), (v or {}).get("occupancy") if v and v.get("occupancy") is not None else ""])
    end = _table(ws3, r0, heads3, body3, None, [14, 10, 12, 10, 14, 14, 10, 16, 12, 14, 14])
    end += 2
    ws3.cell(row=end, column=1, value="Сравнение с предыдущим периодом такой же длины").font = Font(bold=True)
    for k, label in (("visits", "Обращения"), ("hosp", "Госпитализации"), ("disch", "Выписки")):
        end += 1
        cur, prev = b["cur"][k], b["prev"][k]
        ws3.cell(row=end, column=1, value=label)
        ws3.cell(row=end, column=2, value=cur)
        ws3.cell(row=end, column=3, value=prev)
        ws3.cell(row=end, column=4, value=(round(100 * (cur - prev) / prev, 1) if prev else "—"))
    ws3.cell(row=end - 3, column=2, value="Этот период").font = Font(bold=True)
    ws3.cell(row=end - 3, column=3, value="Предыдущий").font = Font(bold=True)
    ws3.cell(row=end - 3, column=4, value="Изменение, %").font = Font(bold=True)
    _signatures(ws3, end, len(heads3))
    _print(ws3, r0, len(heads3))
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ---------------------------------------------------------------- CSV
def csv_bytes(c, user, d1, d2, region_id=None, district_id=None, facility_id=None) -> bytes:
    b = build(c, user, d1, d2, region_id, district_id, facility_id)
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["Регион", "Район", "Учреждение", "Период с", "Период по"] + [x for x, _ in b["cols"]])
    for r in b["rows"]:
        w.writerow([r["region"], r["district"], r["facility"], d1, d2] + [r["v"].get(code, "") for _, code in b["cols"]])
    return ("﻿" + out.getvalue()).encode("utf-8")


# ---------------------------------------------------------------- PDF
def pdf(c, user, d1, d2, region_id=None, district_id=None, facility_id=None, kind: str = "custom") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVu", os.path.join(FONT_DIR, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")))
    b = build(c, user, d1, d2, region_id, district_id, facility_id)
    cols = b["cols"]
    st_h = ParagraphStyle("h", fontName="DejaVu-Bold", fontSize=13, leading=16)
    st_p = ParagraphStyle("p", fontName="DejaVu", fontSize=8, leading=10)
    st_c = ParagraphStyle("c", fontName="DejaVu", fontSize=6.5, leading=8)
    st_hc = ParagraphStyle("hc", fontName="DejaVu-Bold", fontSize=6.3, leading=7.5, alignment=1)
    period = d1 if d1 == d2 else f"{d1} — {d2}"
    story = [Paragraph(b["settings"]["org_title"], st_p), Paragraph(PERIOD_NAMES.get(kind, PERIOD_NAMES["custom"]) + " по гриппу и ОРВИ", st_h),
             Paragraph(f"Отчётный период: {period}. {b['filters']}. Сформирован: {datetime.now(TZ).strftime('%d.%m.%Y %H:%M')}", st_p), Spacer(1, 6)]
    head = [Paragraph(x, st_hc) for x in ["№", "Регион", "Район", "Учреждение"] + [x for x, _ in cols]]
    data = [head]
    for i, r in enumerate(b["rows"], 1):
        data.append([Paragraph(str(i), st_c), Paragraph(r["region"], st_c), Paragraph(r["district"], st_c), Paragraph(r["facility"], st_c)] + [Paragraph(str(r["v"].get(code, "")), st_c) for _, code in cols])
    t = b["total"]
    data.append([Paragraph("", st_c), Paragraph("<b>ИТОГО</b>", st_c), "", ""] + [Paragraph(f"<b>{t.get(code, '')}</b>", st_c) for _, code in cols])
    width = landscape(A4)[0] - 30
    fixed = [18, 62, 55, 100]
    rest = (width - sum(fixed)) / max(len(cols), 1)
    table = Table(data, colWidths=fixed + [rest] * len(cols), repeatRows=1)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6F1")), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F2F2F2")),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]))
    story.append(table)
    story.append(Spacer(1, 18))
    for label in ("Составил: ____________________________", "Проверил: ____________________________", "Утвердил: ____________________________", "Дата: ____________________________", "Подпись: ____________________________"):
        story.append(Paragraph(label, st_p))
        story.append(Spacer(1, 8))
    out = io.BytesIO()

    def footer(canvas, doc):
        canvas.setFont("DejaVu", 7)
        canvas.drawCentredString(landscape(A4)[0] / 2, 12, f"Страница {doc.page}")

    SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=15, rightMargin=15, topMargin=18, bottomMargin=24, title="Сводный отчёт по гриппу и ОРВИ").build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()
