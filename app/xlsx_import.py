"""Loads the 'places for patients' workbook (one sheet per region, a row per hospital) into facilities and daily reports.

Per hospital row: total beds -> beds_flu; total minus free -> beds_occupied; visits for the last 24 hours -> visits (today only);
admitted yesterday/today -> hosp; discharged yesterday/today -> disch. Whatever the file does not contain (severe cases, ...)
stays empty rather than being invented."""
import io
import re

import openpyxl

from . import reports
from .db import audit, now

# the sheet name (Uzbek, as in the file) -> the region in the system
SHEETS = {"ққр": "Республика Каракалпакстан", "андижон": "Андижанская область", "бухоро": "Бухарская область", "жиззах": "Джизакская область", "қашқадарё": "Кашкадарьинская область",
          "навоий": "Навоийская область", "наманган": "Наманганская область", "самарқанд": "Самаркандская область", "сирдарё": "Сырдарьинская область",
          "сурхондарё": "Сурхандарьинская область", "тошкент вил": "Ташкентская область", "фарғона": "Ферганская область", "хоразм": "Хорезмская область", "тошкент": "город Ташкент"}
SHEETS = {k: v for k, v in SHEETS.items()}
DEFAULT_DISTRICT = "Без района"


def fold(s) -> str:
    return re.sub(r"[^\w]+", " ", str(s or "").lower().replace("ё", "е")).strip()


SHEETS = {fold(k): v for k, v in SHEETS.items()}   # compare in the same folded form as the sheet names


def default_district(c, region_id: int) -> int:
    """Facilities need a district in the data model; the people of the field do not use districts, so each region has one neutral district."""
    r = c.execute("SELECT id FROM districts WHERE region_id=? AND name_ru=?", (region_id, DEFAULT_DISTRICT)).fetchone()
    return r["id"] if r else c.execute("INSERT INTO districts(region_id, name_ru, name_uz) VALUES (?,?,?)", (region_id, DEFAULT_DISTRICT, "Туманларсиз")).lastrowid


def find_or_create_facility(c, region_id: int, name: str, by: str = "") -> tuple[int, bool]:
    key = fold(name)
    for f in c.execute("SELECT f.id, f.name_ru FROM facilities f JOIN districts d ON d.id=f.district_id WHERE d.region_id=?", (region_id,)):
        if fold(f["name_ru"]) == key:
            return f["id"], False
    fid = c.execute("INSERT INTO facilities(district_id, name_ru, created_at) VALUES (?,?,?)", (default_district(c, region_id), name.strip(), now())).lastrowid
    audit(c, "facility.create", "facility", fid, {"name": name.strip(), "region": region_id}, actor=by)
    return fid, True


def _int(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return int(round(v)) if v >= 0 else None
    return None


def parse(data: bytes) -> list[dict]:
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    out = []
    for ws in wb.worksheets:
        key = fold(ws.title.replace(".", ""))
        region = SHEETS.get(key)
        if not region:
            continue
        for row in ws.iter_rows(min_row=5, values_only=True):
            row = list(row) + [None] * 14
            if not isinstance(row[0], (int, float)) or not isinstance(row[1], str) or not row[1].strip():
                continue
            total, free = _int(row[4]), _int(row[5])
            out.append({"region": region, "name": " ".join(row[1].split()), "beds": total, "occupied": (total - free) if total is not None and free is not None and free <= total else None,
                        "visits": _int(row[6]), "hosp_prev": _int(row[7]), "hosp": _int(row[8]), "disch_prev": _int(row[10]), "disch": _int(row[11])})
    return out


def load(c, data: bytes, d_prev: str, d_today: str, dry: bool, by: dict) -> dict:
    rows = parse(data)
    if not rows:
        raise reports.ReportError("В файле не нашлось листов областей с таблицей учреждений")
    regions = {r["name_ru"]: r["id"] for r in c.execute("SELECT id, name_ru FROM regions")}
    created = saved = 0
    errors, facilities_new = [], []
    for r in rows:
        rid = regions.get(r["region"])
        if not rid:
            errors.append(f"{r['name']}: регион «{r['region']}» не найден")
            continue
        if dry:
            exists = any(fold(f["name_ru"]) == fold(r["name"]) for f in c.execute("SELECT f.name_ru FROM facilities f JOIN districts d ON d.id=f.district_id WHERE d.region_id=?", (rid,)))
            if not exists:
                created += 1
                facilities_new.append(f"{r['region']}: {r['name']}")
            saved += int(any(v is not None for v in (r["beds"], r["hosp"], r["disch"], r["visits"]))) + int(any(v is not None for v in (r["hosp_prev"], r["disch_prev"])))
            continue
        fid, new = find_or_create_facility(c, rid, r["name"], by["name"])
        created += new
        if new:
            facilities_new.append(f"{r['region']}: {r['name']}")
        for d, vals in ((d_prev, {"hosp": r["hosp_prev"], "disch": r["disch_prev"]}),
                        (d_today, {"beds_flu": r["beds"], "beds_occupied": r["occupied"], "visits": r["visits"], "hosp": r["hosp"], "disch": r["disch"]})):
            vals = {k: v for k, v in vals.items() if v is not None}
            if not vals:
                continue
            try:
                reports.admin_save(c, fid, d, vals, "Импорт из Excel", by, partial=True)
                saved += 1
            except reports.ReportError as e:
                errors.append(f"{r['name']} ({d}): {e.message}")
    return {"facilities": len(rows), "new_facilities": created, "reports": saved, "errors": errors[:30], "errors_total": len(errors), "new_list": facilities_new[:60], "dry": dry,
            "dates": [d_prev, d_today]}
