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
from .db import SETTINGS, TZ, all_settings
from .translit import lat

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
PERIOD_NAMES = {"daily": "Ежедневный сводный отчёт", "weekly": "Недельный сводный отчёт", "monthly": "Месячный сводный отчёт", "custom": "Сводный отчёт за период"}
# Uzbek (Latin) for the texts of the files; Russian is the key, so the Russian output is unchanged. See tools/uz-glossary.md.
XU = {
    "Ежедневный сводный отчёт": "Kunlik yig‘ma hisobot", "Недельный сводный отчёт": "Haftalik yig‘ma hisobot", "Месячный сводный отчёт": "Oylik yig‘ma hisobot", "Сводный отчёт за период": "Davr uchun yig‘ma hisobot",
    "Сводный отчёт по гриппу и ОРВИ": "Gripp va ORVI bo‘yicha yig‘ma hisobot",
    "Всего коек": "Jami o‘rinlar", "Выделено для гриппа и ОРВИ": "Gripp va ORVI uchun ajratilgan", "Обращения": "Murojaatlar", "Госпитализации": "Yotqizilganlar", "Выписки": "Chiqarilganlar",
    "Занято коек": "Band o‘rinlar", "в т.ч. беременные": "shundan homilador ayollar", "в т.ч. дети": "shundan bolalar", "Тяжёлые": "Og‘ir", "Крайне тяжёлые": "O‘ta og‘ir",
    "из них беременные": "shundan homilador ayollar", "из них дети": "shundan bolalar", "Свободные койки": "Bo‘sh o‘rinlar",
    "Регион: ": "Viloyat: ", "Район: ": "Tuman: ", "Учреждение: ": "Muassasa: ", "Вся доступная территория": "Barcha mavjud hudud",
    "Отчётный период: ": "Hisobot davri: ", "Дата формирования: ": "Shakllantirilgan sana: ", "Сформирован: ": "Shakllantirilgan: ",
    "Составил: ": "Tuzdi: ", "Проверил: ": "Tekshirdi: ", "Утвердил: ": "Tasdiqladi: ", "Дата: ": "Sana: ", "Подпись: ": "Imzo: ",
    "Страница &P из &N": "Sahifa &P / &N", "Страница ": "Sahifa ",
    "Сводная информация": "Umumiy ma’lumot", "Детальная информация": "Batafsil ma’lumot", "Динамика": "Dinamika",
    "Основные показатели": "Asosiy ko‘rsatkichlar", "Учреждений в системе": "Tizimdagi muassasalar", "Предоставили отчёт": "Hisobot taqdim etganlar", "Не предоставили": "Hisobot taqdim etmaganlar",
    "Тяжёлые пациенты": "Og‘ir ahvoldagi bemorlar", "Крайне тяжёлые пациенты": "O‘ta og‘ir ahvoldagi bemorlar", "Выделено коек для гриппа и ОРВИ": "Gripp va ORVI uchun ajratilgan o‘rinlar",
    "Занятость коечного фонда, %": "O‘rinlar fondi bandligi, %", "Итоги по регионам": "Viloyatlar bo‘yicha yakunlar",
    "Регион": "Viloyat", "Район": "Tuman", "Учреждение": "Muassasa", "Отчётов": "Hisobotlar", "Выделено коек": "Ajratilgan o‘rinlar", "Занято": "Band", "Занятость, %": "Bandlik, %", "ИТОГО": "JAMI",
    ": по учреждениям": ": muassasalar kesimida", "Динамика показателей": "Ko‘rsatkichlar dinamikasi", "Дата": "Sana", "Госпит. − выписки": "Yotqizilgan − chiqarilgan",
    "Сравнение с предыдущим периодом такой же длины": "Xuddi shu uzunlikdagi oldingi davr bilan solishtirish", "Этот период": "Joriy davr", "Предыдущий": "Oldingi", "Изменение, %": "O‘zgarish, %",
    "Период с": "Davr boshi", "Период по": "Davr oxiri",
    "Вопросы": "Savollar", "Вопрос": "Savol", "Название в таблицах": "Jadvallardagi nomi", "Формулировка вопроса": "Savol matni", "Уточняет вопрос": "Qaysi savolga qo‘shimcha",
    "Вопросы анкеты, по которым построены таблицы": "Jadvallar tuzilgan anketa savollari", "Свободные койки": "Bo‘sh o‘rinlar", "Занятость, %": "Band qilinganlik, %",
}
UZ_ORG = "O‘zbekiston Respublikasi Sog‘liqni saqlash vazirligi"


def tr(lang: str):
    """A translator of the fixed texts of the files: Russian stays as it is, Uzbek is looked up by the Russian text."""
    return (lambda s: XU.get(s, s)) if lang == "uz" else (lambda s: s)


def pick(c, table: str, ident, lang: str, col: str = "name") -> str:
    r = c.execute(f"SELECT {col}_ru AS ru, {col}_uz AS uz FROM {table} WHERE id=?", (ident,)).fetchone()
    return ("?" if not r else (lat(r["uz"]) if lang == "uz" and r["uz"] else r["ru"]))


def org_title(st: dict, lang: str) -> str:
    """The organisation named in the heading: the Uzbek form when the setting still holds the default Russian text."""
    t = st["org_title"]
    return UZ_ORG if lang == "uz" and t == SETTINGS["org_title"] else t


def report_title(kind: str, lang: str) -> str:
    """«Недельный сводный отчёт по гриппу и ОРВИ» / «Gripp va ORVI bo‘yicha haftalik yig‘ma hisobot»."""
    name = PERIOD_NAMES.get(kind, PERIOD_NAMES["custom"])
    if lang == "uz":
        n = XU[name]
        return "Gripp va ORVI bo‘yicha " + n[0].lower() + n[1:]
    return name + " по гриппу и ОРВИ"


def filename(lang: str, d1: str, d2: str, ext: str) -> str:
    """ASCII file name: flu_2026-11-25.xlsx in Russian, hisobot_2026-11-25.xlsx in Uzbek (a period gets both dates)."""
    return ("hisobot_" if lang == "uz" else "flu_") + d1 + ("" if d1 == d2 else f"_{d2}") + "." + ext


def _names(c, lang: str = "ru"):
    """{facility id: (region, district, facility)} in the language, and the Russian triple (the order of the rows in Russian; in Uzbek they follow the Uzbek names)."""
    names, order = {}, {}
    for r in c.execute("SELECT f.id, r.name_ru AS rr, r.name_uz AS ru_, d.name_ru AS dr, d.name_uz AS du, f.name_ru AS fr, f.name_uz AS fu FROM facilities f JOIN districts d ON d.id=f.district_id JOIN regions r ON r.id=d.region_id"):
        order[r["id"]] = (r["rr"], r["dr"], r["fr"])
        names[r["id"]] = tuple((lat(u) if lang == "uz" and u else ru) for ru, u in ((r["rr"], r["ru_"]), (r["dr"], r["du"]), (r["fr"], r["fu"])))
    return names, order


def _heading(r, lang: str, full: bool = False) -> str:
    """The name of a question in the language: the short one (the head of a column) or the full wording."""
    if lang == "uz":
        names = (r["name_uz"],) if full else (r["short_uz"], r["name_uz"])
        return next((lat(x) for x in names if x), r["name_ru"] if full else (r["short_ru"] or r["name_ru"]))
    return r["name_ru"] if full else (r["short_ru"] or r["name_ru"])


def columns(c, lang: str = "ru", occupancy: bool = False) -> list[tuple[str, str]]:
    """The columns follow the questionnaire: its switched-on questions in their order, with their short names, so a changed questionnaire changes the files.
    «Свободные койки» and «Занятость, %» follow the occupied beds; when that question is switched off but the period has such data, the block is added at the end."""
    L = tr(lang)
    rows = c.execute("SELECT code, name_ru, name_uz, short_ru, short_uz, active FROM indicators ORDER BY sort").fetchall()
    extra = [(L("Свободные койки"), "beds_free"), (L("Занятость, %"), "occupancy")]
    cols = []
    for r in rows:
        if r["active"]:
            cols.append((_heading(r, lang), r["code"]))
            if r["code"] == "beds_occupied":
                cols += extra
    if occupancy and not any(code == "beds_occupied" for _, code in cols):
        occ = next((r for r in rows if r["code"] == "beds_occupied"), None)
        if occ:
            cols += [(_heading(occ, lang), "beds_occupied")] + extra
    return cols


def questions(c, lang: str = "ru") -> list[dict]:
    """The switched-on questions as the bot numbers them: number, short name, the full wording, the number of the question it adds to."""
    rows = [r for r in c.execute("SELECT code, name_ru, name_uz, short_ru, short_uz, parent_code, agg FROM indicators WHERE active=1 ORDER BY sort")]
    no = {r["code"]: i for i, r in enumerate(rows, 1)}
    return [{"no": i, "code": r["code"], "short": _heading(r, lang), "full": _heading(r, lang, True), "parent": no.get(r["parent_code"], ""), "agg": r["agg"]} for i, r in enumerate(rows, 1)]


def _cell(v: dict, code: str):
    """A figure for a file: empty when there is none (not reported, or not computable)."""
    x = v.get(code)
    return "" if x is None else x


def describe(c, region_id, district_id, facility_id, lang: str = "ru") -> str:
    L = tr(lang)
    parts = []
    if region_id:
        parts.append(L("Регион: ") + pick(c, "regions", region_id, lang))
    if district_id:
        parts.append(L("Район: ") + pick(c, "districts", district_id, lang))
    if facility_id:
        parts.append(L("Учреждение: ") + pick(c, "facilities", facility_id, lang))
    return "; ".join(parts) or L("Вся доступная территория")


def build(c, user, d1: str, d2: str, region_id=None, district_id=None, facility_id=None, lang: str = "ru") -> dict:
    fac, order = _names(c, lang)
    agg = stats.aggregate(c, user, d1, d2, "facility", region_id, district_id, facility_id)
    cols = columns(c, lang, occupancy=any("beds_occupied" in t for t in agg.values()))
    qs = questions(c, lang)
    rows = []
    for fid, t in sorted(agg.items(), key=lambda kv: (fac if lang == "uz" else order).get(kv[0], ("", "", ""))):
        reg, dist, name = fac[fid]
        rows.append({"region": reg, "district": dist, "facility": name, "v": t})
    total = {}
    for r in rows:
        for code, v in r["v"].items():
            if code not in ("occupancy", "reported") and v is not None:
                total[code] = total.get(code, 0) + v
    if "beds_occupied" in total:
        total["occupancy"] = round(100 * total["beds_occupied"] / total["beds_flu"], 1) if total.get("beds_flu") else None
    else:
        total["occupancy"] = None
        total.pop("beds_free", None)
    by_region = stats.aggregate(c, user, d1, d2, "region", region_id, district_id, facility_id)
    rnames = {r["id"]: (lat(r["name_uz"]) if lang == "uz" and r["name_uz"] else r["name_ru"]) for r in c.execute("SELECT id, name_ru, name_uz FROM regions")}
    regions = [{"name": rnames[k], "v": v} for k, v in sorted(by_region.items(), key=lambda kv: kv[0])]
    days = stats.daterange(d1, d2)
    tot = stats.daily_totals(c, user, d1, d2, region_id, district_id, facility_id)
    span = len(days)
    prev = stats.daily_totals(c, user, (date.fromisoformat(d1) - timedelta(days=span)).isoformat(), (date.fromisoformat(d1) - timedelta(days=1)).isoformat(), region_id, district_id, facility_id) if span else {}
    dyn = [{"date": d, "v": tot.get(d)} for d in days]
    flows = [(title, code) for title, code in cols if code in {q["code"] for q in qs if q["agg"] == "sum"}]      # the figures that are added up over days: compared with the previous period
    prev_sum = {k: sum(t.get(k, 0) for t in prev.values()) for _, k in flows}
    cur_sum = {k: sum(t.get(k, 0) for t in tot.values()) for _, k in flows}
    return {"cols": cols, "questions": qs, "flows": flows, "rows": rows, "total": total, "regions": regions, "dynamics": dyn, "prev": prev_sum, "cur": cur_sum, "d1": d1, "d2": d2,
            "facilities_total": stats.facility_count(c, user, region_id, district_id, facility_id), "reported": total and len(rows),
            "filters": describe(c, region_id, district_id, facility_id, lang), "settings": all_settings(c)}


# ---------------------------------------------------------------- Excel
THIN = Side(style="thin", color="888888")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD_FILL = PatternFill("solid", fgColor="DCE6F1")
TOTAL_FILL = PatternFill("solid", fgColor="F2F2F2")


def _sheet_title(ws, title: str, period: str, filters: str, org: str, width: int, lang: str = "ru") -> int:
    L = tr(lang)
    ws["A1"] = org
    ws["A1"].font = Font(bold=True, size=11)
    ws["A2"] = title
    ws["A2"].font = Font(bold=True, size=14)
    ws["A3"] = L("Отчётный период: ") + period + ".   " + filters
    ws["A4"] = L("Дата формирования: ") + datetime.now(TZ).strftime("%d.%m.%Y %H:%M")
    for r in (1, 2, 3, 4):
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=max(width, 4))
    return 6


SIGNATURES = ("Составил: ", "Проверил: ", "Утвердил: ", "Дата: ", "Подпись: ")
LINE = "____________________________"


def _signatures(ws, row: int, width: int, lang: str = "ru") -> None:
    row += 2
    for label in (tr(lang)(k) + LINE for k in SIGNATURES):
        ws.cell(row=row, column=1, value=label).font = Font(size=11)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=max(width, 4))
        row += 2


def _print(ws, header_row: int, last_col: int, landscape: bool = True, lang: str = "ru") -> None:
    ws.page_setup.paperSize = 9   # A4
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{header_row}:{header_row}"
    ws.print_area = f"A1:{get_column_letter(last_col)}{ws.max_row}"
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = ws.page_margins.bottom = 0.5
    ws.oddFooter.center.text = tr(lang)("Страница &P из &N")


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


def xlsx(c, user, d1, d2, region_id=None, district_id=None, facility_id=None, kind: str = "custom", lang: str = "ru") -> bytes:
    """The Excel workbook (three sheets). lang is 'ru' (the original wording) or 'uz' (Uzbek in Latin: titles, sheet names, headers, names of the territories)."""
    L = tr(lang)
    b = build(c, user, d1, d2, region_id, district_id, facility_id, lang)
    org, cols = org_title(b["settings"], lang), b["cols"]
    period = d1 if d1 == d2 else f"{d1} — {d2}"
    title = report_title(kind, lang)
    wb = Workbook()
    # ---- sheet 1: the summary
    ws = wb.active
    ws.title = L("Сводная информация")
    t = b["total"]
    full = {q["code"]: q["full"] for q in b["questions"]}
    r0 = _sheet_title(ws, title, period, b["filters"], org, max(9, len(cols) + 3), lang)
    ws.cell(row=r0, column=1, value=L("Основные показатели")).font = Font(bold=True)
    head = [(L("Учреждений в системе"), b["facilities_total"]), (L("Предоставили отчёт"), b["reported"] or 0), (L("Не предоставили"), max(b["facilities_total"] - (b["reported"] or 0), 0))]
    head += [(full.get(code, title_), t.get(code)) for title_, code in cols]                  # every figure of the questionnaire, with the full wording of the question
    r = r0 + 1
    for k, v in head:
        ws.cell(row=r, column=1, value=k).border = BORDER
        ws.cell(row=r, column=2, value=v if v is not None else "—").border = BORDER
        r += 1
    r += 1
    ws.cell(row=r, column=1, value=L("Итоги по регионам")).font = Font(bold=True)
    heads = ["№", L("Регион"), L("Отчётов")] + [x for x, _ in cols]
    body = [[i, x["name"], x["v"].get("reported", 0)] + [_cell(x["v"], code) for _, code in cols] for i, x in enumerate(b["regions"], 1)]
    total = ["", L("ИТОГО"), sum(x[2] for x in body)] + [_cell(t, code) for _, code in cols]
    end = _table(ws, r + 1, heads, body, total, [34, 30, 12] + [14] * len(cols))
    _signatures(ws, end, len(heads), lang)
    _print(ws, r + 1, len(heads), lang=lang)
    # ---- sheet 2: the detail by facility
    ws2 = wb.create_sheet(L("Детальная информация"))
    heads2 = ["№", L("Регион"), L("Район"), L("Учреждение")] + [x for x, _ in cols]
    r0 = _sheet_title(ws2, title + L(": по учреждениям"), period, b["filters"], org, len(heads2), lang)
    body2 = [[i, x["region"], x["district"], x["facility"]] + [_cell(x["v"], code) for _, code in cols] for i, x in enumerate(b["rows"], 1)]
    total2 = ["", L("ИТОГО"), "", ""] + [_cell(t, code) for _, code in cols]
    widths = [5, 26, 24, 38] + [13] * len(cols)
    end = _table(ws2, r0, heads2, body2, total2, widths)
    _signatures(ws2, end, len(heads2), lang)
    _print(ws2, r0, len(heads2), lang=lang)
    # ---- sheet 3: the dynamics
    ws3 = wb.create_sheet(L("Динамика"))
    both = {code for _, code in cols} >= {"hosp", "disch"}
    heads3 = [L("Дата"), L("Отчётов")] + [x for x, _ in cols] + ([L("Госпит. − выписки")] if both else [])
    r0 = _sheet_title(ws3, L("Динамика показателей"), period, b["filters"], org, len(heads3), lang)
    body3 = []
    for x in b["dynamics"]:
        v = x["v"] or {}
        body3.append([x["date"], v.get("n", 0)] + [_cell(v, code) for _, code in cols] + ([(v["hosp"] - v["disch"]) if "hosp" in v and "disch" in v else ""] if both else []))
    end = _table(ws3, r0, heads3, body3, None, [14, 10] + [13] * (len(heads3) - 2))
    end += 2
    ws3.cell(row=end, column=1, value=L("Сравнение с предыдущим периодом такой же длины")).font = Font(bold=True)
    ws3.cell(row=end + 1, column=2, value=L("Этот период")).font = Font(bold=True)
    ws3.cell(row=end + 1, column=3, value=L("Предыдущий")).font = Font(bold=True)
    ws3.cell(row=end + 1, column=4, value=L("Изменение, %")).font = Font(bold=True)
    end += 1
    for label, k in b["flows"]:                                                                 # the figures that are added up over the days
        end += 1
        cur, prev = b["cur"][k], b["prev"][k]
        ws3.cell(row=end, column=1, value=label)
        ws3.cell(row=end, column=2, value=cur)
        ws3.cell(row=end, column=3, value=prev)
        ws3.cell(row=end, column=4, value=(round(100 * (cur - prev) / prev, 1) if prev else "—"))
    _signatures(ws3, end, len(heads3), lang)
    _print(ws3, r0, len(heads3), lang=lang)
    # ---- sheet 4: the questions: which wording stands behind the head of a column
    ws4 = wb.create_sheet(L("Вопросы"))
    heads4 = ["№", L("Название в таблицах"), L("Формулировка вопроса"), L("Уточняет вопрос")]
    r0 = _sheet_title(ws4, L("Вопросы анкеты, по которым построены таблицы"), period, b["filters"], org, len(heads4), lang)
    body4 = [[q["no"], q["short"], q["full"], q["parent"]] for q in b["questions"]]
    _table(ws4, r0, heads4, body4, None, [6, 34, 80, 18])
    ws4.freeze_panes = None
    ws4.auto_filter.ref = None
    _print(ws4, r0, len(heads4), lang=lang)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ---------------------------------------------------------------- CSV
def csv_bytes(c, user, d1, d2, region_id=None, district_id=None, facility_id=None, lang: str = "ru") -> bytes:
    L = tr(lang)
    b = build(c, user, d1, d2, region_id, district_id, facility_id, lang)
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow([L("Регион"), L("Район"), L("Учреждение"), L("Период с"), L("Период по")] + [x for x, _ in b["cols"]])
    for r in b["rows"]:
        w.writerow([r["region"], r["district"], r["facility"], d1, d2] + [_cell(r["v"], code) for _, code in b["cols"]])
    return ("﻿" + out.getvalue()).encode("utf-8")


# ---------------------------------------------------------------- PDF
def pdf(c, user, d1, d2, region_id=None, district_id=None, facility_id=None, kind: str = "custom", lang: str = "ru") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVu", os.path.join(FONT_DIR, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")))
    L = tr(lang)
    b = build(c, user, d1, d2, region_id, district_id, facility_id, lang)
    cols = b["cols"]
    st_h = ParagraphStyle("h", fontName="DejaVu-Bold", fontSize=13, leading=16)
    st_p = ParagraphStyle("p", fontName="DejaVu", fontSize=8, leading=10)
    st_c = ParagraphStyle("c", fontName="DejaVu", fontSize=6.5, leading=8)
    width = landscape(A4)[0] - 30
    fixed = [18, 62, 55, 100]
    rest = (width - sum(fixed)) / max(len(cols), 1)
    hsize = 6.3
    if lang == "uz":       # the Uzbek words of the headers are longer: the font of the headers shrinks until the longest word fits into its column (no word is cut in the middle)
        longest = max((pdfmetrics.stringWidth(w, "DejaVu-Bold", 1) for x, _ in cols for w in x.split()), default=1)
        hsize = max(4.6, min(6.3, round((rest - 4.5) / longest, 1)))
    st_hc = ParagraphStyle("hc", fontName="DejaVu-Bold", fontSize=hsize, leading=hsize * 1.2, alignment=1)
    period = d1 if d1 == d2 else f"{d1} — {d2}"
    story = [Paragraph(org_title(b["settings"], lang), st_p), Paragraph(report_title(kind, lang), st_h),
             Paragraph(f"{L('Отчётный период: ')}{period}. {b['filters']}. {L('Сформирован: ')}{datetime.now(TZ).strftime('%d.%m.%Y %H:%M')}", st_p), Spacer(1, 6)]
    head = [Paragraph(x, st_hc) for x in ["№", L("Регион"), L("Район"), L("Учреждение")] + [x for x, _ in cols]]
    data = [head]
    for i, r in enumerate(b["rows"], 1):
        data.append([Paragraph(str(i), st_c), Paragraph(r["region"], st_c), Paragraph(r["district"], st_c), Paragraph(r["facility"], st_c)] + [Paragraph(str(_cell(r["v"], code)), st_c) for _, code in cols])
    t = b["total"]
    data.append([Paragraph("", st_c), Paragraph("<b>" + L("ИТОГО") + "</b>", st_c), "", ""] + [Paragraph(f"<b>{_cell(t, code)}</b>", st_c) for _, code in cols])
    table = Table(data, colWidths=fixed + [rest] * len(cols), repeatRows=1)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6F1")), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F2F2F2")),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]))
    story.append(table)
    story.append(Spacer(1, 18))
    for label in (L(k) + LINE for k in SIGNATURES):
        story.append(Paragraph(label, st_p))
        story.append(Spacer(1, 8))
    out = io.BytesIO()

    def footer(canvas, doc):
        canvas.setFont("DejaVu", 7)
        canvas.drawCentredString(landscape(A4)[0] / 2, 12, f"{L('Страница ')}{doc.page}")

    SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=15, rightMargin=15, topMargin=18, bottomMargin=24, title=L("Сводный отчёт по гриппу и ОРВИ")).build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()
