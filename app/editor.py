"""The editor of territories: a list of facilities from Excel (region, facility, number of beds, head physician, phone) is read and every row is matched to a facility
of the platform in the same region. Many facilities are already on the platform with misspelled names; the list has the right ones, so a row is offered the most
similar facility (the name is then corrected), or «new», or «skip», and the person confirms or changes it on the site before anything is written.

The pieces: parse() reads the workbook, preview() matches, apply() writes what the person decided. Phones are kept as digits (998XXXXXXXXX)."""
import io
import re
from difflib import SequenceMatcher

import openpyxl

from .db import audit, now
from .translit import lat

GENERIC = {"tuman", "tumani", "shahar", "shahri", "sh", "viloyat", "viloyati", "tibbiyot", "birlashmasi", "birlashma", "markazi", "markaz", "shifohonasi", "shifohona",
           "kasalhonasi", "klinikasi", "bolimi", "filiali", "filial", "ilmiy", "respublika", "respublikasi", "son", "sonli", "va", "boyicha"}
PLACEHOLDER = re.compile(r"мавжуд\s+бўлса|mavjud\s+bo.lsa|если\s+имеется", re.I)
CITY_WORDS = re.compile(r"шаҳар|шахар|shahar|shahri|город", re.I)
_DROP = str.maketrans("", "", "‘’ʻʼ'`´")


class EditorError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message, self.status = message, status


def key(s) -> str:
    """A name in the form in which two spellings of it become equal: Latin, no apostrophes, h = x, k = q, only letters and digits."""
    s = lat(str(s or "").replace("ў", "у").replace("Ў", "У")).lower()           # ў is written у by people who have no Uzbek keyboard, and o‘ in Latin: one letter
    s = re.sub("o[‘’ʻʼ'`´]", "u", s).translate(_DROP)
    s = s.replace("x", "h").replace("q", "k").replace("ё", "e").replace("w", "v")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def tokens(k: str) -> list[str]:
    return [t for t in k.split() if t]


def _w(t: str) -> float:
    return 2.0 if t.isdigit() else 0.3 if t in GENERIC else 1.0


def sim(ka: str, kb: str) -> float:
    """0..1: how much two names (in the form of key()) look like one name. Numbers must agree («1-сон» is not «2-сон»); the place names count more than «тиббиёт бирлашмаси»."""
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    ta, tb = tokens(ka), tokens(kb)
    da, db = {t for t in ta if t.isdigit()}, {t for t in tb if t.isdigit()}

    def cover(x, y):
        tot = sum(_w(t) for t in x) or 1.0
        got = 0.0
        for t in x:
            b = max((SequenceMatcher(None, t, o).ratio() for o in y), default=0.0)
            if b >= 0.75:
                got += _w(t) * b
        return got / tot
    score = 0.35 * SequenceMatcher(None, ka, kb).ratio() + 0.65 * min(cover(ta, tb), cover(tb, ta))
    if da != db:
        score *= 0.5
    return round(score, 4)


# ---------------------------------------------------------------- phones
def phones(raw) -> list[str]:
    """The numbers of a cell as digits «998901234567»: separated by a line break, ; , or a wide gap; nine digits get the 998 in front."""
    if raw is None:
        return []
    out = []
    for part in re.split(r"[\n;,/]+|\s{3,}", str(raw)):
        d = re.sub(r"\D", "", part)
        if not d:
            continue
        chunks = [d]
        if d.startswith("998") and len(d) > 12 and len(d) % 12 == 0:
            chunks = [d[i:i + 12] for i in range(0, len(d), 12)]
        elif not d.startswith("998") and len(d) > 9 and len(d) % 9 == 0:
            chunks = [d[i:i + 9] for i in range(0, len(d), 9)]
        for x in chunks:
            out.append("998" + x if len(x) == 9 else x)
    seen, res = set(), []
    for x in out:
        if x not in seen:
            seen.add(x); res.append(x)
    return res


def phone_ok(p: str) -> bool:
    return len(p) == 12 and p.startswith("998")


def clean_fio(s) -> str:
    return " ".join(str(s or "").split())[:200]


# ---------------------------------------------------------------- reading the workbook
def parse(data: bytes) -> list[dict]:
    """The rows of the list: {region, name, beds, fio, phone_raw, row}. A row with a text in the first column and nothing else opens a region; a facility row has a number in
    the first column and a name in the second. The columns are found by their headers (the facility, beds, head physician, phone) and fall back to B, C, D, E."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception:
        raise EditorError("Не удалось прочитать файл: нужен Excel (.xlsx)")
    out = []
    for ws in wb.worksheets:
        rows = [list(r) + [None] * 8 for r in ws.iter_rows(values_only=True)]
        cols = {"name": 1, "beds": 2, "fio": 3, "phone": 4}
        for r in rows[:10]:
            heads = [str(x or "").lower() for x in r[:8]]
            if sum(1 for h in heads if h.strip()) >= 3 and any(re.search(r"муассаса|muassasa|учрежд", h) for h in heads):      # the row of headers, not the title
                for i, h in enumerate(heads):
                    if re.search(r"муассаса|muassasa|учрежд", h): cols["name"] = i
                    elif re.search(r"койка|o.rin|коек|bed", h): cols["beds"] = i
                    elif re.search(r"фиш|фио|шифокор|ответствен|mas.ul|fio", h): cols["fio"] = i
                    elif re.search(r"тел|phone|telefon", h): cols["phone"] = i
                break
        region = ""
        for i, r in enumerate(rows, 1):
            a, nm = r[0], r[cols["name"]]
            if isinstance(a, str) and a.strip() and all(x in (None, "") for x in r[1:6]) and not a.strip().isdigit():
                region = " ".join(a.split())
                continue
            if not isinstance(a, (int, float)) or isinstance(a, bool) or not isinstance(nm, str) or not nm.strip():
                continue
            beds = r[cols["beds"]]
            beds = int(beds) if isinstance(beds, (int, float)) and not isinstance(beds, bool) and beds >= 0 else None
            out.append({"row": i, "region": region, "name": " ".join(nm.split()), "beds": beds, "fio": clean_fio(r[cols["fio"]]), "phone_raw": "" if r[cols["phone"]] is None else str(r[cols["phone"]])})
    if not out:
        raise EditorError("В файле не нашлось учреждений: нужны столбцы «Муассаса», «Койка сони», «Бош шифокор ФИШ», «Тел рақами» и названия регионов отдельными строками")
    return out


# ---------------------------------------------------------------- matching
def match_region(regions: list, text: str):
    """The region of the platform that a region line of the list means: by the Latin form of its Uzbek name, the oblast and the city of Tashkent told apart."""
    city = bool(CITY_WORDS.search(text))
    kt = [t for t in tokens(key(text)) if t not in GENERIC]
    best, score = None, 0.0
    for r in regions:
        rcity = r["name_ru"].lower().startswith("город") or bool(CITY_WORDS.search(r["name_uz"] or ""))
        if rcity != city:
            continue
        kr = [t for t in tokens(key(r["name_uz"] or r["name_ru"])) if t not in GENERIC] or tokens(key(r["name_ru"]))
        if not kt or not kr:
            continue
        s = min(sum(max(SequenceMatcher(None, a, b).ratio() for b in kr) for a in kt) / len(kt), sum(max(SequenceMatcher(None, a, b).ratio() for b in kt) for a in kr) / len(kr))
        if s > score:
            best, score = r, s
    return best if score >= 0.8 else None


def facilities_of(c, region_id: int) -> list:
    return c.execute("""SELECT f.id, f.name_ru, f.name_uz, f.active, f.beds, d.name_ru AS district FROM facilities f JOIN districts d ON d.id=f.district_id
                        WHERE d.region_id=? ORDER BY f.name_ru""", (region_id,)).fetchall()


def contacts_of(c, ids: list[int]) -> dict:
    out: dict = {}
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        for x in c.execute(f"SELECT id, facility_id, kind, fio, phone FROM facility_contacts WHERE facility_id IN ({','.join('?' * len(part))}) ORDER BY kind, id", part):
            out.setdefault(x["facility_id"], []).append(dict(x))
    return out


AUTO_MIN, AUTO_GAP, REVIEW_MIN = 0.80, 0.06, 0.70


def preview(c, user, data: bytes) -> dict:
    """The list matched against the platform. Per row: the region, what was read, the candidates (the most similar facilities of the region) and the proposal
    (action: match / new / skip); then the facilities of the platform that no row claimed."""
    from . import auth
    parsed = parse(data)
    regions = [dict(r) for r in c.execute("SELECT id, name_ru, name_uz FROM regions WHERE active=1 ORDER BY sort")]
    by_region: dict = {}
    for p in parsed:
        by_region.setdefault(p["region"], []).append(p)
    rows, region_info, unmatched, problems, all_fac = [], [], [], [], {}
    for text, items in by_region.items():
        reg = match_region(regions, text) if text else None
        allowed = bool(reg) and auth.sees_region(user, reg["id"])
        fac = facilities_of(c, reg["id"]) if reg else []
        info = {"text": text, "region_id": reg["id"] if reg else None, "region": reg["name_ru"] if reg else "", "region_uz": (reg["name_uz"] if reg else ""), "rows": len(items),
                "allowed": allowed, "facilities": len(fac)}
        region_info.append(info)
        if not reg:
            problems.append({"kind": "region", "text": text})
        # all pairs, best first; a facility goes to one row only
        scored = []
        for ix, p in enumerate(items):
            kp = key(p["name"])
            cand = sorted(({"id": f["id"], "score": sim(kp, key(f["name_ru"])) if not f["name_uz"] else max(sim(kp, key(f["name_ru"])), sim(kp, key(f["name_uz"])))} for f in fac), key=lambda x: -x["score"])
            scored.append(cand)
        taken: dict = {}
        order = sorted(((cand[0]["score"], ix) for ix, cand in enumerate(scored) if cand), reverse=True)
        choice: dict = {}
        for sc, ix in order:
            cand = scored[ix]
            top = cand[0]
            second = cand[1]["score"] if len(cand) > 1 else 0.0
            if top["score"] >= AUTO_MIN and top["score"] - second >= AUTO_GAP and top["id"] not in taken:
                taken[top["id"]] = ix; choice[ix] = top
        facmap = {f["id"]: f for f in fac}
        cmap = contacts_of(c, [f["id"] for f in fac])
        if reg and allowed:           # every facility of the region: the person may pick any of them for a row
            all_fac[str(reg["id"])] = [{"id": f["id"], "name": f["name_ru"], "name_uz": f["name_uz"], "district": f["district"], "active": bool(f["active"]), "beds": f["beds"],
                                        "fio": next((x["fio"] for x in cmap.get(f["id"], []) if x["kind"] == "main"), ""), "phone": next((x["phone"] for x in cmap.get(f["id"], []) if x["kind"] == "main"), "")} for f in fac]
        for ix, p in enumerate(items):
            ph = phones(p["phone_raw"])
            warn = []
            if p["fio"] == "":
                warn.append("fio")
            if not ph:
                warn.append("phone")
            elif not all(phone_ok(x) for x in ph):
                warn.append("phone_format")
            placeholder = bool(PLACEHOLDER.search(p["name"]))
            ch = choice.get(ix)
            row = {"row": p["row"], "region_id": reg["id"] if reg else None, "region_text": text, "name": p["name"], "name_lat": lat(p["name"]), "beds": p["beds"], "fio": p["fio"],
                   "phone": ", ".join(ph), "phone_raw": p["phone_raw"], "warn": warn, "allowed": allowed}
            if not reg or not allowed:
                row.update(action="skip", facility_id=None, reason="region" if not reg else "access", score=0, candidates=[])
            elif placeholder:
                row.update(action="skip", facility_id=None, reason="placeholder", score=0, candidates=[])
            else:
                # not sure (a facility that looks alike but not enough to be taken for the same): the person must decide, so that no duplicate is made by default
                unsure = not ch and bool(scored[ix]) and scored[ix][0]["score"] >= REVIEW_MIN
                row.update(action="match" if ch else "review" if unsure else "new", facility_id=ch["id"] if ch else None, score=ch["score"] if ch else 0, reason="")
                row["candidates"] = [{"id": x["id"], "score": x["score"], "name": facmap[x["id"]]["name_ru"], "district": facmap[x["id"]]["district"]} for x in scored[ix][:3] if x["score"] >= 0.45]
            if row["facility_id"]:
                f, cs = facmap[row["facility_id"]], cmap.get(row["facility_id"], [])
                main = next((x for x in cs if x["kind"] == "main"), None)
                row["current"] = {"name": f["name_ru"], "name_uz": f["name_uz"], "beds": f["beds"], "active": bool(f["active"]), "fio": main["fio"] if main else "", "phone": main["phone"] if main else "", "district": f["district"]}
            rows.append(row)
        if reg and allowed:
            used = set(choice[ix]["id"] for ix in choice)
            for f in fac:
                if f["id"] not in used:
                    unmatched.append({"id": f["id"], "region_id": reg["id"], "name": f["name_ru"], "name_uz": f["name_uz"], "district": f["district"], "active": bool(f["active"])})
    return {"rows": rows, "regions": region_info, "unmatched": unmatched, "problems": problems, "facilities": all_fac,
            "summary": {"rows": len(rows), "match": sum(r["action"] == "match" for r in rows), "new": sum(r["action"] == "new" for r in rows), "skip": sum(r["action"] == "skip" for r in rows),
                                                                                                   "review": sum(r["action"] == "review" for r in rows)}}


# ---------------------------------------------------------------- writing
def default_district(c, region_id: int) -> int:
    from .xlsx_import import default_district as dd
    return dd(c, region_id)


def set_main_contact(c, facility_id: int, fio: str, phone: str) -> bool:
    """The main responsible person of a facility: what is empty keeps what is there. True when something changed."""
    fio, phone = clean_fio(fio), ",".join(dict.fromkeys(phones(phone)))
    if not fio and not phone:
        return False
    cur = c.execute("SELECT * FROM facility_contacts WHERE facility_id=? AND kind='main' ORDER BY id LIMIT 1", (facility_id,)).fetchone()
    if cur:
        nf, np = fio or cur["fio"], phone or cur["phone"]
        if (nf, np) == (cur["fio"], cur["phone"]):
            return False
        c.execute("UPDATE facility_contacts SET fio=?, phone=?, updated_at=? WHERE id=?", (nf, np, now(), cur["id"]))
        return True
    c.execute("INSERT INTO facility_contacts(facility_id, kind, fio, phone, created_at, updated_at) VALUES (?,?,?,?,?,?)", (facility_id, "main", fio, phone, now(), now()))
    return True


def replace_contacts(c, facility_id: int, items: list) -> None:
    """The responsible people of a facility as the form sends them: [{kind: main|reserve, fio, phone}]; an empty one is dropped."""
    c.execute("DELETE FROM facility_contacts WHERE facility_id=?", (facility_id,))
    seen_main = False
    for x in (items or [])[:5]:
        fio, phone = clean_fio(x.get("fio")), ",".join(dict.fromkeys(phones(x.get("phone"))))
        if not fio and not phone:
            continue
        kind = "main" if (x.get("kind") != "reserve" and not seen_main) else "reserve"
        seen_main = seen_main or kind == "main"
        c.execute("INSERT INTO facility_contacts(facility_id, kind, fio, phone, created_at, updated_at) VALUES (?,?,?,?,?,?)", (facility_id, kind, fio, phone, now(), now()))
    from .people import link_facility
    link_facility(c, facility_id)                                                  # the people of the bot with these phones become responsible



def apply(c, user, rows: list, disable: list, actor: str = "") -> dict:
    """What the person decided: per row match (the name of the facility is corrected to the one of the list, the beds and the responsible person are set), new (a facility is
    created) or skip; and facilities to switch off. Everything in one transaction; a row that cannot be applied is reported, the others are done."""
    from . import auth
    from .xlsx_import import fold
    res = {"renamed": 0, "same": 0, "created": 0, "contacts": 0, "linked": 0, "disabled": 0, "skipped": 0, "errors": []}

    def err(row, msg):
        res["errors"].append({"name": str(row.get("name") or "")[:120], "message": msg})
    used: set = set()
    touched: set = set()
    for r in rows[:2000]:
        action = r.get("action")
        name = " ".join(str(r.get("name") or "").split())[:200]
        if action == "skip" or not action:
            res["skipped"] += 1
            continue
        if action == "review":
            err(r, "Строка не решена: выберите учреждение, «создать» или «пропустить»"); continue
        try:
            rid = int(r.get("region_id"))
        except (TypeError, ValueError):
            err(r, "Не указан регион"); continue
        if not auth.sees_region(user, rid) or not c.execute("SELECT 1 FROM regions WHERE id=?", (rid,)).fetchone():
            err(r, "Этот регион вам не назначен"); continue
        if len(name) < 3:
            err(r, "Название слишком короткое"); continue
        beds = r.get("beds")
        beds = int(beds) if isinstance(beds, (int, float)) and not isinstance(beds, bool) and beds >= 0 else None
        if action == "match":
            f = c.execute("SELECT f.* FROM facilities f JOIN districts d ON d.id=f.district_id WHERE f.id=? AND d.region_id=?", (r.get("facility_id"), rid)).fetchone()
            if not f:
                err(r, "Учреждение не найдено в этом регионе"); continue
            if f["id"] in used:
                err(r, "Это учреждение уже выбрано для другой строки"); continue
            used.add(f["id"])
            dup = [x for x in facilities_of(c, rid) if x["id"] != f["id"] and fold(x["name_ru"]) == fold(name)]
            if dup:
                err(r, "В регионе уже есть другое учреждение с таким названием"); continue
            new_uz = lat(name)
            changed = (f["name_ru"], f["name_uz"], f["beds"], f["active"]) != (name, new_uz, beds if beds is not None else f["beds"], 1)
            if changed:
                c.execute("UPDATE facilities SET name_ru=?, name_uz=?, beds=?, active=1 WHERE id=?", (name, new_uz, beds if beds is not None else f["beds"], f["id"]))
                audit(c, "facility.update", "facility", f["id"], {"editor": True, "from": f["name_ru"], "name": name, "beds": beds}, actor=actor)
            res["renamed" if f["name_ru"] != name else "same"] += 1
            if set_main_contact(c, f["id"], r.get("fio"), r.get("phone")):
                res["contacts"] += 1
            touched.add(f["id"])
        elif action == "new":
            if any(fold(x["name_ru"]) == fold(name) for x in facilities_of(c, rid)):
                err(r, "Такое учреждение уже есть в регионе: выберите его в списке"); continue
            fid = c.execute("INSERT INTO facilities(district_id, name_ru, name_uz, beds, created_at) VALUES (?,?,?,?,?)", (default_district(c, rid), name, lat(name), beds, now())).lastrowid
            audit(c, "facility.create", "facility", fid, {"editor": True, "name": name, "region": rid}, actor=actor)
            res["created"] += 1
            if set_main_contact(c, fid, r.get("fio"), r.get("phone")):
                res["contacts"] += 1
            touched.add(fid)
        elif action == "review":
            err(r, "Строка не решена: выберите учреждение, «создать» или «пропустить»")
        else:
            err(r, "Неизвестное действие")
    from .people import link_facility
    for fid in touched:                                                            # the people of the bot whose verified phone is one of these phones become responsible
        res["linked"] += link_facility(c, fid)
    for fid in disable[:2000]:
        f = c.execute("SELECT f.id, f.name_ru, d.region_id FROM facilities f JOIN districts d ON d.id=f.district_id WHERE f.id=?", (fid,)).fetchone()
        if not f or not auth.sees_region(user, f["region_id"]):
            res["errors"].append({"name": str(fid), "message": "Учреждение не найдено или не из вашего региона"}); continue
        c.execute("UPDATE facilities SET active=0 WHERE id=?", (f["id"],))
        audit(c, "facility.update", "facility", f["id"], {"editor": True, "active": False, "name": f["name_ru"]}, actor=actor)
        res["disabled"] += 1
    audit(c, "editor.apply", "facility", 0, {k: v for k, v in res.items() if k != "errors"} | {"errors": len(res["errors"])}, actor=actor)
    return res
