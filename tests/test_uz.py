"""The web in Uzbek (Latin) by default: the login page, the exports, the texts the server writes itself, and the dictionary of the messages of the server."""
import ast
import io
import json
import os
import re
import shutil
import subprocess

import openpyxl
import pytest

from conftest import make_facility, put_report

CYR = re.compile("[А-Яа-яЁё]")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def logged_in(lang=None):
    """A client of a person who is logged in, with the cookie `lang` as given (None: no cookie at all, the default language)."""
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app, base_url="http://testserver")
    c.__enter__()
    assert c.post("/login", data={"login": "admin", "password": "secret123"}, follow_redirects=False).status_code == 303
    c.cookies.pop("lang", None)
    if lang:
        c.cookies.set("lang", lang)
    return c


def cells(wb):
    return [c.value for ws in wb for row in ws.iter_rows() for c in row if isinstance(c.value, str)]


def test_login_page_follows_the_cookie(env):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        page = c.get("/login").text
        assert '<html lang="uz"' in page and 'id="lang"' in page and "/static/i18n.js" in page and "data-i18n" in page   # Uzbek by default, with the switch
        assert "Login yoki parol noto‘g‘ri." in c.post("/login", data={"login": "admin", "password": "wrong"}).text
        c.cookies.set("lang", "ru")
        assert '<html lang="ru"' in c.get("/login").text
        r = c.post("/login", data={"login": "admin", "password": "wrong"})
        assert r.status_code == 401 and "Неверный логин или пароль." in r.text
        c.cookies.set("lang", "xx")                                  # anything but uz / ru is the default
        assert "Login yoki parol noto‘g‘ri." in c.post("/login", data={"login": "admin", "password": "wrong"}).text
    with TestClient(app) as c:
        codes = [c.post("/login", data={"login": "admin", "password": "x"}).text for _ in range(12)]
        assert any("Urinishlar juda ko‘p" in t for t in codes)


def test_exports_are_uzbek_by_default_and_russian_with_the_cookie(env):
    f = make_facility(1, "Район А", "Больница 1")
    put_report(f, "2026-02-09")
    q = "d1=2026-02-01&d2=2026-02-10&kind=weekly"
    uz = logged_in()
    r = uz.get(f"/api/export?fmt=xlsx&{q}")
    assert r.headers["content-disposition"] == 'attachment; filename="hisobot_2026-02-01_2026-02-10.xlsx"'
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Umumiy ma’lumot", "Batafsil ma’lumot", "Dinamika"] and all(len(n) <= 31 and not re.search(r"[\[\]:*?/\\]", n) for n in wb.sheetnames)
    text = cells(wb)
    assert "Gripp va ORVI bo‘yicha haftalik yig‘ma hisobot" in text and "Imzo: ____________________________" in text and "O‘zbekiston Respublikasi Sog‘liqni saqlash vazirligi" in text
    assert not [t for t in text if CYR.search(t) and t != "Больница 1" and t != "Район А"]               # a facility without an Uzbek name keeps its Russian one; the rest is Uzbek
    assert "Qoraqalpog‘iston Respublikasi" in text                                                         # region names: name_uz
    assert wb.worksheets[0].oddFooter.center.text == "Sahifa &P / &N"
    ru = logged_in("ru")
    r = ru.get(f"/api/export?fmt=xlsx&{q}")
    assert 'filename="flu_2026-02-01_2026-02-10.xlsx"' in r.headers["content-disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Сводная информация", "Детальная информация", "Динамика"] and "Недельный сводный отчёт по гриппу и ОРВИ" in cells(wb)
    assert "Республика Каракалпакстан" in cells(wb) and wb.worksheets[0].oddFooter.center.text == "Страница &P из &N"
    # CSV and PDF
    assert uz.get(f"/api/export?fmt=csv&{q}").content.decode("utf-8-sig").splitlines()[0].startswith("Viloyat;Tuman;Muassasa;Davr boshi;Davr oxiri;Jami o‘rinlar;")
    assert ru.get(f"/api/export?fmt=csv&{q}").content.decode("utf-8-sig").splitlines()[0].startswith("Регион;Район;Учреждение;Период с;Период по;Всего коек;")
    pdf_uz, pdf_ru = uz.get(f"/api/export?fmt=pdf&{q}"), ru.get(f"/api/export?fmt=pdf&{q}")
    assert pdf_uz.content[:4] == b"%PDF" and pdf_ru.content[:4] == b"%PDF" and 'filename="hisobot_' in pdf_uz.headers["content-disposition"]
    if shutil.which("pdftotext"):
        t_uz = subprocess.run(["pdftotext", "-", "-"], input=pdf_uz.content, capture_output=True).stdout.decode()
        t_ru = subprocess.run(["pdftotext", "-", "-"], input=pdf_ru.content, capture_output=True).stdout.decode()
        assert "yig‘ma hisobot" in t_uz and "Imzo:" in t_uz and not CYR.search(t_uz.replace("Больница 1", "").replace("Район А", ""))
        assert "Недельный сводный отчёт" in t_ru and "Подпись:" in t_ru


def test_export_functions_keep_the_russian_default_for_the_bot(env):
    """The bot asks the exports for the language of the person; without a language the files are what they always were."""
    from app import exports
    from app.db import connect
    f = make_facility(1, "Район А", "Больница 1")
    put_report(f, "2026-02-09")
    c = connect()
    user = {"id": 1, "role": "super_admin", "regions": None}
    assert openpyxl.load_workbook(io.BytesIO(exports.xlsx(c, user, "2026-02-09", "2026-02-09", kind="daily"))).sheetnames == ["Сводная информация", "Детальная информация", "Динамика"]
    assert openpyxl.load_workbook(io.BytesIO(exports.xlsx(c, user, "2026-02-09", "2026-02-09", kind="daily", lang="uz"))).sheetnames[0] == "Umumiy ma’lumot"
    assert exports.pdf(c, user, "2026-02-09", "2026-02-09", kind="daily", lang="uz")[:4] == b"%PDF"
    assert exports.filename("ru", "2026-02-09", "2026-02-09", "xlsx") == "flu_2026-02-09.xlsx" and exports.filename("uz", "2026-02-09", "2026-02-10", "pdf") == "hisobot_2026-02-09_2026-02-10.pdf"
    c.close()


def test_coverage_xlsx_follows_the_cookie(env):
    make_facility(1, "Район А", "Больница 1")
    uz, ru = logged_in(), logged_in("ru")
    x = uz.get("/api/coverage.xlsx?d1=2026-02-04&d2=2026-02-10")
    assert 'filename="qamrov_2026-02-04_2026-02-10.xlsx"' in x.headers["content-disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(x.content))
    assert wb.sheetnames == ["Yig‘ma", "Ulanmaganlar", "Shaxslar", "Muassasalar bo‘yicha"]
    assert not [t for t in cells(wb) if CYR.search(t) and t not in ("Больница 1", "Район А")]
    assert openpyxl.load_workbook(io.BytesIO(ru.get("/api/coverage.xlsx?d1=2026-02-04&d2=2026-02-10").content)).sheetnames == ["Сводка", "Не подключены", "Люди", "По учреждениям"]
    assert ru.get("/api/coverage?d1=2026-02-04&d2=2026-02-10").json()["regions"][0]["name"] == "Республика Каракалпакстан"       # the JSON for the page stays as it was


def test_validation_alerts_and_control_are_written_in_the_language_of_the_cookie(env):
    f = make_facility(1, "Район А", "Больница 1")
    put_report(f, "2026-02-10", beds_flu=40, beds_occupied=39)                            # 97.5% of the beds: a critical alert
    uz, ru = logged_in(), logged_in("ru")
    full = dict(beds_total=10, beds_flu=20, beds_occupied=5, visits=50, severe=5, occ_pregnant=1, occ_children=1, extreme=1, extreme_pregnant=0, extreme_children=0, hosp=10, disch=6)
    bad = {"facility_id": f, "date": "2026-02-09", "values": full}
    v = uz.post("/api/validate", json=bad).json()
    assert "Gripp va ORVI uchun ajratilgan o‘rinlar (20) jami o‘rinlardan (10) ko‘p." in v["errors"] and not [m for m in v["errors"] + v["warnings"] if CYR.search(m)]
    assert "Коек для больных гриппом и ОРВИ (20) больше общего числа коек (10)." in ru.post("/api/validate", json=bad).json()["errors"]
    r = uz.put("/api/reports", json={"facility_id": f, "date": "2026-02-09", "values": full, "reason": "x"})
    assert r.status_code == 422 and r.json()["error"].startswith("Gripp va ORVI uchun") and not [m for m in r.json()["details"]["errors"] if CYR.search(m)]
    # the figures that are missing, wrong or negative, in the names of the questions in Uzbek
    miss = uz.post("/api/validate", json={"values": {"beds_total": -1, "beds_flu": "x"}}).json()["errors"]
    assert "Manfiy qiymatlar taqiqlanadi: Jami o‘rinlar soni" in miss and any(m.startswith("To‘ldirilmagan: ") for m in miss) and any(m.startswith("Butun son kerak: ") for m in miss) and not [m for m in miss if CYR.search(m)]
    assert any(m.startswith("Не заполнено: ") for m in ru.post("/api/validate", json={"values": {}}).json()["errors"])
    a_uz = uz.get("/api/alerts").json()["items"]
    a_ru = ru.get("/api/alerts").json()["items"]
    assert any(x["text"].startswith("O‘rinlar bandligi kritik: «Qoraqalpog‘iston Respublikasi» bo‘yicha") for x in a_uz) and not [x for x in a_uz if CYR.search(x["text"].replace("Больница 1", ""))]      # (the facility of the test has no Uzbek name)
    assert any(x["text"].startswith("Критическая загрузка коек: в регионе «Республика Каракалпакстан»") for x in a_ru)
    assert all(CYR.search(x["scope"]) for x in a_uz)                                       # scope stays the Russian name: the page maps it to the name of the region
    ctl = uz.get("/api/control?date=2026-02-10").json()
    assert ctl["rows"] and ctl["counts"]["total"] == 1


def test_territory_import_accepts_uzbek_headers(env):
    uz = logged_in()
    data = "Viloyat;Tuman;Muassasa\nToshkent shahri;Yangi tuman;7-poliklinika\n".encode("utf-8")
    r = uz.post("/api/geo/import?dry=1", files={"file": ("t.csv", data)}).json()
    assert r["districts"] == 1 and r["facilities"] == 1 and r["errors_total"] == 0


# ---------------------------------------------------------------- the dictionary of the messages of the server
def node(*args, stdin=None):
    return subprocess.run(["node", *args], input=stdin, capture_output=True, text=True, cwd=ROOT)


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_every_pattern_of_the_dictionary_compiles_and_is_consistent():
    r = node("tools/uzpcheck.js")
    assert r.returncode == 0, r.stdout + r.stderr


def _sample(node_):
    """The text of a string or an f-string with a number in place of every value."""
    if isinstance(node_, ast.Constant) and isinstance(node_.value, str):
        return node_.value
    if isinstance(node_, ast.JoinedStr):
        return "".join(p.value if isinstance(p, ast.Constant) else "5" for p in node_.values)
    return None


def server_messages() -> list[str]:
    """Every Russian text the server puts into an error: bad("..."), HTTPException(...), ReportError / PeopleError / BroadcastError / RuleError("...")."""
    names = {"bad", "ReportError", "PeopleError", "BroadcastError", "RuleError", "HTTPException"}
    out = []
    for f in ("main", "people", "reports", "rules", "broadcast", "xlsx_import"):
        tree = ast.parse(open(os.path.join(ROOT, "app", f + ".py"), encoding="utf-8").read())
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) in names:
                for a in n.args[:2]:
                    s = _sample(a)
                    if s and CYR.search(s):
                        out.append(s)
    return out


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_every_error_message_of_the_server_has_an_uzbek_text():
    msgs = server_messages()
    assert len(msgs) > 90
    msgs += ["строка 3: неизвестный регион «X»", "Facility 1: регион «Region» не найден", "Средняя: 7 дней данных, R² = 0.50", "Высокая: 12 дней данных, тренд устойчив (R² = 0.80)", "Низкая: данных меньше 5 дней",
             "Нет отчёта за 2026-02-10 от 3 учреждений региона «X».", "Не заполнено: Name", "Telegram не принял тест: Forbidden", "нет связи с Telegram: timed out",
             "Коек для больных гриппом и ОРВИ (50) больше общего числа коек (40).", "Выписано (9) больше, чем было занято и поступило (5 + 3). Проверьте данные.",
             "Обращений в 3 и более раз больше, чем в прошлом отчёте (10 → 40). Проверьте.", "Неизвестные показатели: a, b"]
    r = node("tools/uzpcheck.js", "--ts", stdin=json.dumps(msgs))
    assert r.returncode == 0, r.stderr
    left = [m for m, t in zip(msgs, json.loads(r.stdout)) if CYR.search(t)]
    assert not left, left
