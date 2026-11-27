"""Summary reports (§10): Excel with three sheets and print setup, PDF for printing, CSV for processing. Every export obeys the
filters (period, region, district, facility) and the rights of the person who asks. Signature fields are at the end."""
import csv
import io
import os
from datetime import date, datetime, timedelta

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.chart import BarChart, DoughnutChart, Reference
from openpyxl.chart.series import DataPoint
from openpyxl.chart.label import DataLabelList
from openpyxl.formatting.rule import ColorScaleRule, DataBarRule
from openpyxl.worksheet.pagebreak import Break
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
    "Сводка для руководства": "Rahbariyat uchun xulosa", "Охват отчётностью, %": "Hisobot qamrovi, %", "Охват отчётностью по регионам": "Viloyatlar bo‘yicha hisobot qamrovi",
    "Доля учреждений, сдавших отчёт, %": "Hisobot topshirgan muassasalar ulushi, %", "Сдали и не сдали отчёт, по регионам": "Hisobot topshirgan va topshirmaganlar, viloyatlar bo‘yicha",
    "Доля сдавших отчёт по дням, %": "Kunlar bo‘yicha hisobot topshirganlar ulushi, %", "Сдали": "Topshirdi", "Не сдали": "Topshirmadi", "Охват, %": "Qamrov, %",
    "Календарь сдачи: какая доля учреждений региона сдала отчёт в этот день, %": "Topshirish kalendari: viloyat muassasalarining qancha qismi o‘sha kuni hisobot topshirdi, %",
    "Не сдали отчёт за период": "Davr mobaynida hisobot topshirmaganlar", "Последний отчёт": "Oxirgi hisobot", "Все учреждения сдали отчёт": "Barcha muassasalar hisobot topshirdi",
    "Всего": "Jami", "Учреждений": "Muassasalar", " (расч.)": " (hisoblangan)", "Итоги по регионам: отчёты за период": "Viloyatlar bo‘yicha yakunlar: davr uchun hisobotlar",
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


def columns(c, lang: str = "ru", occupancy: bool = False, estimated: bool = False) -> list[tuple[str, str]]:
    """The columns follow the questionnaire: its switched-on questions in their order, with their short names, so a changed questionnaire changes the files.
    «Свободные койки» and «Занятость, %» follow the occupied beds; when that question is switched off but the period has such data, the block is added at the end."""
    L = tr(lang)
    rows = c.execute("SELECT code, name_ru, name_uz, short_ru, short_uz, active FROM indicators ORDER BY sort").fetchall()
    mark = L(" (расч.)") if estimated else ""                       # counted from the admissions, not reported: said in the head of the column
    extra = [(L("Свободные койки") + mark, "beds_free"), (L("Занятость, %") + mark, "occupancy")]
    cols = []
    for r in rows:
        if r["active"]:
            cols.append((_heading(r, lang) + (mark if r["code"] == "beds_occupied" else ""), r["code"]))
            if r["code"] == "beds_occupied":
                cols += extra
    if occupancy and not any(code == "beds_occupied" for _, code in cols):
        occ = next((r for r in rows if r["code"] == "beds_occupied"), None)
        if occ:
            cols += [(_heading(occ, lang) + mark, "beds_occupied")] + extra
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


def _coverage(c, user, d1: str, d2: str, region_id, district_id, facility_id, lang: str, fac: dict) -> dict:
    """Who sent reports in the period: by region (facilities, sent, share), by day, and the facilities that sent nothing."""
    w, a = stats._where(user, region_id, district_id, facility_id)
    facs = c.execute(f"SELECT f.id, r.id AS rid FROM facilities f JOIN districts d ON d.id=f.district_id JOIN regions r ON r.id=d.region_id WHERE {w}", a).fetchall()
    sent = stats.load(c, user, d1, d2, region_id, district_id, facility_id)["data"]          # {facility: {date: values}}
    days = stats.daterange(d1, d2)[-31:]
    last = {r["facility_id"]: r["last"] for r in c.execute("SELECT facility_id, MAX(report_date) AS last FROM reports GROUP BY facility_id")}
    regions = []
    for r in c.execute("SELECT id, name_ru, name_uz FROM regions WHERE active=1 ORDER BY sort, id"):
        mine = [f["id"] for f in facs if f["rid"] == r["id"]]
        if not mine:
            continue
        done = [i for i in mine if i in sent]
        by_day = {d: sum(1 for i in mine if d in sent.get(i, {})) for d in days}
        regions.append({"id": r["id"], "name": (lat(r["name_uz"]) if lang == "uz" and r["name_uz"] else r["name_ru"]), "total": len(mine), "reported": len(done),
                        "pct": round(100 * len(done) / len(mine), 1), "by_day": by_day})
    total, reported = sum(x["total"] for x in regions), sum(x["reported"] for x in regions)
    missing = sorted(([fac[f["id"]][0], fac[f["id"]][1], fac[f["id"]][2], last.get(f["id"], "")] for f in facs if f["id"] not in sent), key=lambda x: x[:3])
    return {"regions": regions, "days": days, "total": total, "reported": reported, "pct": round(100 * reported / total, 1) if total else 0.0, "missing": missing,
            "by_day": {d: sum(x["by_day"][d] for x in regions) for d in days}}


def build(c, user, d1: str, d2: str, region_id=None, district_id=None, facility_id=None, lang: str = "ru") -> dict:
    fac, order = _names(c, lang)
    agg = stats.aggregate(c, user, d1, d2, "facility", region_id, district_id, facility_id)
    cols = columns(c, lang, occupancy=any("beds_occupied" in t for t in agg.values()), estimated=any(t.get("occ_estimated") for t in agg.values()))
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
    return {"coverage": _coverage(c, user, d1, d2, region_id, district_id, facility_id, lang, fac), "cols": cols, "questions": qs, "flows": flows, "rows": rows, "total": total, "regions": regions, "dynamics": dyn, "prev": prev_sum, "cur": cur_sum, "d1": d1, "d2": d2,
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


def _table(ws, start: int, heads: list[str], body: list[list], total: list | None, widths: list[int] | None = None, head_h: int = 48) -> int:
    for j, h in enumerate(heads, 1):
        cell = ws.cell(row=start, column=j, value=h)
        cell.font, cell.fill, cell.border = Font(bold=True), HEAD_FILL, BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[start].height = head_h
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


GREEN_C, RED_C, BLUE_C, AMBER_C = "2E9E6B", "E05A5A", "3B6CF6", "F2A93B"


def _tile(ws, row: int, c1: int, c2: int, label: str, value, sub: str, color: str) -> None:
    """A big figure for the heads: the label above, the number, a line under it; merged over the columns c1..c2."""
    for k, (text, font, h) in enumerate(((label, Font(size=10, color="666666"), 18), (value, Font(size=26, bold=True, color=color), 40), (sub, Font(size=10, color="666666"), 18))):
        ws.merge_cells(start_row=row + k, start_column=c1, end_row=row + k, end_column=c2)
        cell = ws.cell(row=row + k, column=c1, value=text)
        cell.font, cell.alignment = font, Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[row + k].height = h
        for j in range(c1, c2 + 1):
            ws.cell(row=row + k, column=j).fill = PatternFill("solid", fgColor="F4F6FB")
            ws.cell(row=row + k, column=j).border = Border(left=Side(style="thin", color="FFFFFF") if j == c1 else None, right=Side(style="medium", color="FFFFFF") if j == c2 else None)


def _bar(title: str, horizontal: bool, stacked: bool = False, height: float = 9.0, width: float = 17.5) -> BarChart:
    ch = BarChart()
    ch.type = "bar" if horizontal else "col"
    ch.title = title
    ch.height, ch.width = height, width
    if stacked:
        ch.grouping, ch.overlap = "stacked", 100
    ch.x_axis.delete = ch.y_axis.delete = False
    ch.gapWidth = 60
    ch.x_axis.tickLblSkip = 1
    return ch


def _values_only() -> DataLabelList:
    d = DataLabelList()
    d.showVal, d.showSerName, d.showCatName, d.showLegendKey, d.showPercent = True, False, False, False, False
    return d


def _leadership(ws, b: dict, L, lang: str, org: str, title: str, period: str) -> None:
    """The sheet for the heads: the picture of the reporting. Tiles (facilities / sent / not sent / share), two charts by region, the table with data bars,
    the calendar of sending (region x day, red to green) with its chart, and the list of the facilities that sent nothing."""
    cv = b["coverage"]
    regs = sorted(cv["regions"], key=lambda x: (-x["pct"], x["name"]))
    ws.title = L("Сводка для руководства")
    ws.sheet_view.showGridLines = False
    for col, w in {"A": 5, "B": 30}.items():
        ws.column_dimensions[col].width = w
    for j in range(3, 17):
        ws.column_dimensions[get_column_letter(j)].width = 12.5
    _sheet_title(ws, L("Охват отчётностью по регионам"), period, b["filters"], org, 16, lang)
    ws["A2"].value = title + ". " + L("Охват отчётностью по регионам")
    not_sent = cv["total"] - cv["reported"]
    level = GREEN_C if cv["pct"] >= 80 else AMBER_C if cv["pct"] >= 50 else RED_C
    _tile(ws, 6, 1, 2, L("Учреждений в системе"), cv["total"], "", BLUE_C)
    _tile(ws, 6, 3, 5, L("Предоставили отчёт"), cv["reported"], f"{cv['pct']:g}%", GREEN_C)
    _tile(ws, 6, 6, 8, L("Не предоставили"), not_sent, f"{round(100 - cv['pct'], 1):g}%", RED_C if not_sent else GREEN_C)
    _tile(ws, 6, 9, 11, L("Охват отчётностью, %"), f"{cv['pct']:g}%", f"{cv['reported']} / {cv['total']}", level)
    # the table of the regions (also the data of the charts below it)
    top = 31
    ws.row_breaks.append(Break(id=top - 3))                                                         # the picture on the first page, the tables on the next
    ws.cell(row=top - 1, column=1, value=L("Итоги по регионам: отчёты за период")).font = Font(bold=True, size=12)
    heads = ["№", L("Регион"), L("Учреждений"), L("Сдали"), L("Не сдали"), L("Охват, %")]
    body = [[i, x["name"], x["total"], x["reported"], x["total"] - x["reported"], x["pct"]] for i, x in enumerate(regs, 1)]
    end = _table(ws, top, heads, body, ["", L("ИТОГО"), cv["total"], cv["reported"], not_sent, cv["pct"]], None, 32)
    ws.freeze_panes = None
    ws.auto_filter.ref = None
    first, last = top + 1, top + len(regs)
    for r in range(first, end + 1):
        ws.cell(row=r, column=6).number_format = '0.0"%"'
        ws.cell(row=r, column=6).alignment = Alignment(horizontal="right")
    if regs:
        ws.conditional_formatting.add(f"F{first}:F{last}", DataBarRule(start_type="num", start_value=0, end_type="num", end_value=100, color="7FA6F8", showValue=True))
        ws.conditional_formatting.add(f"E{first}:E{last}", ColorScaleRule(start_type="num", start_value=0, start_color="FFFFFF", end_type="max", end_color="F8B4B4"))
        cats = Reference(ws, min_col=2, min_row=first, max_row=last)
        c1 = _bar(L("Доля учреждений, сдавших отчёт, %"), True)                                   # the share by region: the best at the top
        c1.add_data(Reference(ws, min_col=6, min_row=top, max_row=last), titles_from_data=True)
        c1.set_categories(cats)
        c1.x_axis.scaling.orientation = "maxMin"
        c1.y_axis.scaling.min, c1.y_axis.scaling.max = 0, 100
        c1.legend = None
        c1.series[0].graphicalProperties.solidFill = BLUE_C
        c1.dataLabels = _values_only()
        ws.add_chart(c1, "A11")
        c2 = _bar(L("Сдали и не сдали отчёт, по регионам"), True, stacked=True)
        c2.add_data(Reference(ws, min_col=4, max_col=5, min_row=top, max_row=last), titles_from_data=True)
        c2.set_categories(cats)
        c2.x_axis.scaling.orientation = "maxMin"
        c2.series[0].graphicalProperties.solidFill, c2.series[1].graphicalProperties.solidFill = GREEN_C, RED_C
        c2.legend.position = "b"
        ws.add_chart(c2, "H11")
    # the calendar of sending: the share of the facilities of a region that sent a report on that day (for a period of several days)
    days = cv["days"][-14:]
    many = len(cv["days"]) > 1
    r = end
    if not many and regs:                                                                          # one day: the share of the sent and the not sent as a ring next to the table
        c3 = DoughnutChart()
        c3.title, c3.holeSize, c3.height, c3.width = L("Охват отчётностью, %"), 55, 9.0, 11
        c3.add_data(Reference(ws, min_col=4, max_col=5, min_row=end, max_row=end), from_rows=True, titles_from_data=False)
        c3.set_categories(Reference(ws, min_col=4, max_col=5, min_row=top))
        for idx, color in enumerate((GREEN_C, RED_C)):
            pt = DataPoint(idx=idx)
            pt.graphicalProperties.solidFill = color
            c3.series[0].dPt.append(pt)
        c3.dataLabels = _values_only()
        c3.legend.position = "b"
        ws.add_chart(c3, f"I{top}")
    if many:
        row = max(end, top + 18) + 3
        ws.cell(row=row - 1, column=1, value=L("Календарь сдачи: какая доля учреждений региона сдала отчёт в этот день, %")).font = Font(bold=True, size=12)
        dd = lambda d: f"{d[8:10]}.{d[5:7]}"
        hrow = row
        for j, h in enumerate(["№", L("Регион")] + [dd(d) for d in days], 1):
            cell = ws.cell(row=hrow, column=j, value=h)
            cell.font, cell.fill, cell.border = Font(bold=True), HEAD_FILL, BORDER
            cell.alignment = Alignment(horizontal="center", vertical="center")
        r = hrow
        for i, x in enumerate(regs, 1):
            r += 1
            ws.cell(row=r, column=1, value=i).border = BORDER
            ws.cell(row=r, column=2, value=x["name"]).border = BORDER
            for j, d in enumerate(days, 3):
                cell = ws.cell(row=r, column=j, value=round(100 * x["by_day"][d] / x["total"]))
                cell.number_format, cell.border, cell.alignment = '0"%"', BORDER, Alignment(horizontal="center")
        r += 1
        totals_row = r
        ws.cell(row=r, column=2, value=L("Всего")).font = Font(bold=True)
        for j, d in enumerate(days, 3):
            cell = ws.cell(row=r, column=j, value=round(100 * cv["by_day"][d] / cv["total"]) if cv["total"] else 0)
            cell.font, cell.fill, cell.border, cell.alignment, cell.number_format = Font(bold=True), TOTAL_FILL, BORDER, Alignment(horizontal="center"), '0"%"'
        for j in (1, 2):
            ws.cell(row=r, column=j).fill, ws.cell(row=r, column=j).border = TOTAL_FILL, BORDER
        if regs and days:
            ws.conditional_formatting.add(f"C{hrow + 1}:{get_column_letter(2 + len(days))}{r}", ColorScaleRule(start_type="num", start_value=0, start_color="F8696B", mid_type="num", mid_value=50, mid_color="FFEB84", end_type="num", end_value=100, end_color="63BE7B"))
        if regs:                                                                                   # the course of the share over the days, next to the table of the regions
            c3 = _bar(L("Доля сдавших отчёт по дням, %"), False)
            c3.add_data(Reference(ws, min_col=2, max_col=2 + len(days), min_row=totals_row), from_rows=True, titles_from_data=True)
            c3.set_categories(Reference(ws, min_col=3, max_col=2 + len(days), min_row=hrow))
            c3.y_axis.scaling.min, c3.y_axis.scaling.max = 0, 100
            c3.legend = None
            c3.series[0].graphicalProperties.solidFill = BLUE_C
            c3.dataLabels = _values_only()
            ws.add_chart(c3, f"I{top}")
    # the facilities that sent nothing in the period
    row = r + 3
    miss = cv["missing"]
    ws.cell(row=row - 1, column=1, value=f"{L('Не сдали отчёт за период')} ({len(miss)})").font = Font(bold=True, size=12)
    if not miss:
        ws.cell(row=row, column=2, value=L("Все учреждения сдали отчёт")).font = Font(italic=True, color="2E9E6B")
        end2 = row
    else:
        shown = miss[:300]
        end2 = _table(ws, row, ["№", L("Регион"), L("Район"), "", L("Учреждение"), "", "", L("Последний отчёт")],
                      [[i, x[0], x[1], "", x[2], "", "", x[3] or "—"] for i, x in enumerate(shown, 1)], None, None, 24)
        for i in range(row + 1, end2 + 1):                                                         # the district and the facility need more room than one narrow column
            ws.merge_cells(start_row=i, start_column=3, end_row=i, end_column=4)
            ws.merge_cells(start_row=i, start_column=5, end_row=i, end_column=7)
        ws.merge_cells(start_row=row, start_column=3, end_row=row, end_column=4)
        ws.merge_cells(start_row=row, start_column=5, end_row=row, end_column=7)
        ws.freeze_panes = None
        ws.auto_filter.ref = None
        if len(miss) > len(shown):
            ws.cell(row=end2 + 1, column=2, value=f"+ {len(miss) - len(shown)}").font = Font(italic=True)
    _signatures(ws, end2, 12, lang)
    ws.page_setup.paperSize = 9
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_area = f"A1:P{ws.max_row}"
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.oddFooter.center.text = L("Страница &P из &N")


def xlsx(c, user, d1, d2, region_id=None, district_id=None, facility_id=None, kind: str = "custom", lang: str = "ru") -> bytes:
    """The Excel workbook (three sheets). lang is 'ru' (the original wording) or 'uz' (Uzbek in Latin: titles, sheet names, headers, names of the territories)."""
    L = tr(lang)
    b = build(c, user, d1, d2, region_id, district_id, facility_id, lang)
    org, cols = org_title(b["settings"], lang), b["cols"]
    period = d1 if d1 == d2 else f"{d1} — {d2}"
    title = report_title(kind, lang)
    wb = Workbook()
    # ---- sheet 1: for the heads (how the reporting looks), then the totals by region
    t = b["total"]
    _leadership(wb.active, b, L, lang, org, title, period)
    ws = wb.create_sheet(L("Сводная информация"))
    r0 = _sheet_title(ws, title, period, b["filters"], org, len(cols) + 3, lang)
    ws.cell(row=r0, column=1, value=L("Итоги по регионам")).font = Font(bold=True)
    heads = ["№", L("Регион"), L("Отчётов")] + [x for x, _ in cols]
    body = [[i, x["name"], x["v"].get("reported", 0)] + [_cell(x["v"], code) for _, code in cols] for i, x in enumerate(b["regions"], 1)]
    total = ["", L("ИТОГО"), sum(x[2] for x in body)] + [_cell(t, code) for _, code in cols]
    end = _table(ws, r0 + 1, heads, body, total, [5, 30, 11] + [15] * len(cols), 64)
    _signatures(ws, end, len(heads), lang)
    _print(ws, r0 + 1, len(heads), lang=lang)
    # ---- sheet 2: the detail by facility
    ws2 = wb.create_sheet(L("Детальная информация"))
    heads2 = ["№", L("Регион"), L("Район"), L("Учреждение")] + [x for x, _ in cols]
    r0 = _sheet_title(ws2, title + L(": по учреждениям"), period, b["filters"], org, len(heads2), lang)
    body2 = [[i, x["region"], x["district"], x["facility"]] + [_cell(x["v"], code) for _, code in cols] for i, x in enumerate(b["rows"], 1)]
    total2 = ["", L("ИТОГО"), "", ""] + [_cell(t, code) for _, code in cols]
    widths = [5, 26, 24, 38] + [13] * len(cols)
    end = _table(ws2, r0, heads2, body2, total2, widths, 64)
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
    end = _table(ws3, r0, heads3, body3, None, [14, 10] + [14] * (len(heads3) - 2), 64)
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
