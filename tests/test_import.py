import io

import openpyxl


def workbook():
    wb = openpyxl.Workbook()
    wb.active.title = "Республика"
    for name, rows in (("Андижон.", [[1, "Вилоят шифохонаси", 1, 1, 100, 30, 12, 5, 8, 3, 7, 9, 2, 50], [2, "Без коек", None, None, None, None, None, None, None, 0, 4, 6, 2, 1]]),
                       ("Қашқадарё.", [[1, "Касбий шифохона", 1, 1, 60, 10, 5, 2, 4, 2, 1, 3, 2, 9]])):
        ws = wb.create_sheet(name)
        for r in range(1, 5):
            ws.append([None] * 14)
        ws.append(["ЖАМИ"] + [None] * 13)
        for row in rows:
            ws.append(row)
    b = io.BytesIO(); wb.save(b)
    return b.getvalue()


def test_parse_and_load(client):
    r = client.post("/api/import/reports?dry=1&d_prev=2026-02-09&d_today=2026-02-10", files={"file": ("a.xlsx", workbook())}).json()
    assert r["facilities"] == 3 and r["new_facilities"] == 3 and r["errors_total"] == 0
    assert client.get("/api/facilities").json()["total"] == 0                 # preview writes nothing
    r = client.post("/api/import/reports?dry=0&d_prev=2026-02-09&d_today=2026-02-10", files={"file": ("a.xlsx", workbook())}).json()
    assert r["new_facilities"] == 3 and r["reports"] == 6 and r["errors_total"] == 0
    d = client.get("/api/dashboard?d1=2026-02-10&d2=2026-02-10").json()["kpis"]["totals"]
    assert d["beds_flu"] == 160 and d["beds_occupied"] == 120 and d["hosp"] == 12 and d["disch"] == 18 and d["visits"] == 17
    y = client.get("/api/dashboard?d1=2026-02-09&d2=2026-02-09").json()["kpis"]["totals"]
    assert y["hosp"] == 7 and y["disch"] == 12 and "visits" not in y            # nothing is invented for the missing figures
    again = client.post("/api/import/reports?dry=0&d_prev=2026-02-09&d_today=2026-02-10", files={"file": ("a.xlsx", workbook())}).json()
    assert again["new_facilities"] == 0                                        # a second load creates no duplicates
    assert client.get("/api/facilities?q=Вилоят").json()["total"] == 1
    assert client.get("/api/reports?d1=2026-02-09&d2=2026-02-10").json()["total"] == 6


def test_import_rejects_other_files_and_non_super(client):
    bad = openpyxl.Workbook(); b = io.BytesIO(); bad.save(b)
    assert client.post("/api/import/reports?dry=1", files={"file": ("a.xlsx", b.getvalue())}).status_code == 400
    from test_api import mk_staff
    a = mk_staff(client, "reg1", "admin", [1])
    assert a.post("/api/import/reports?dry=1", files={"file": ("a.xlsx", workbook())}).status_code == 403
