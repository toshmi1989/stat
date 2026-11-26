import pytest
from conftest import make_facility, put_report


def codes(client):
    return [i["code"] for i in client.get("/api/indicators").json()["items"] if i["active"]]


def test_questions_are_added_edited_ordered_and_removed_from_the_site(client):
    r = client.post("/api/indicators", json={"name_ru": "Обращения детей", "name_uz": "Bolalar murojaatlari", "hint_ru": "до 14 лет", "hint_uz": "14 yoshgacha", "agg": "sum", "required": False})
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    assert code.startswith("q_") and code.isascii()                                                    # the code is made from the name
    again = client.post("/api/indicators", json={"name_ru": "Обращения детей", "agg": "sum"}).json()["code"]
    assert again != code and again.startswith(code)                                                    # and it is unique
    item = next(i for i in client.get("/api/indicators").json()["items"] if i["code"] == code)
    assert item["required"] == 0 and item["hint_uz"] == "14 yoshgacha" and item["core"] == 0 and item["grp"] == "extra"
    assert client.patch(f"/api/indicators/{code}", json={"name_ru": "Обращения детей до 14", "hint_uz": "14 yoshgacha, jami", "required": True}).status_code == 200
    item = next(i for i in client.get("/api/indicators").json()["items"] if i["code"] == code)
    assert item["name_ru"] == "Обращения детей до 14" and item["required"] == 1
    # the order: the given codes go first, in that order
    before = codes(client)
    assert client.post("/api/indicators/reorder", json={"codes": [code, "visits"]}).status_code == 200
    after = codes(client)
    assert after[:2] == [code, "visits"] and set(after) == set(before)
    assert client.post("/api/indicators/reorder", json={"codes": ["no_such_code"]}).status_code == 400
    assert client.post("/api/indicators/reorder", json={"codes": [code, code]}).status_code == 400
    # removing: a question added later and never answered is deleted, a core one only switched off
    assert client.delete(f"/api/indicators/{again}").status_code == 200 and client.delete(f"/api/indicators/{again}").status_code == 404
    assert client.delete("/api/indicators/visits").status_code == 409
    assert client.patch("/api/indicators/visits", json={"active": False}).status_code == 200 and "visits" not in codes(client)
    # a question with a figure in a report or in a rule is not deleted
    f = make_facility(1)
    put_report(f, "2026-02-10", **{code: 3})
    assert client.delete(f"/api/indicators/{code}").status_code == 409
    other = client.post("/api/indicators", json={"name_ru": "Для правила", "agg": "last"}).json()["code"]
    assert client.post("/api/rules", json={"expr": f"{other} <= beds_total", "kind": "error", "message_ru": "m"}).status_code == 200
    assert client.delete(f"/api/indicators/{other}").status_code == 200                                # the rule written for it (its limit) goes with it
    assert not [r for r in client.get("/api/indicators").json()["rules"] if other in r["expr"]]


def test_an_optional_question_may_stay_empty_and_a_required_one_may_not(client):
    from app import rules
    from app.db import connect
    code = client.post("/api/indicators", json={"name_ru": "Необязательный", "agg": "sum", "required": False}).json()["code"]
    must = client.post("/api/indicators", json={"name_ru": "Обязательный", "agg": "sum"}).json()["code"]
    c = connect()
    full = dict(beds_total=100, beds_flu=40, beds_occupied=20, visits=50, severe=5, occ_pregnant=1, occ_children=1, extreme=1, extreme_pregnant=0, extreme_children=0, hosp=10, disch=6)
    res = rules.validate(c, full | {must: 1}, "ru", None, None)
    assert res["errors"] == []                                                                         # the optional one is absent, and that is fine
    res = rules.validate(c, full, "ru", None, None)
    assert res["errors"] and must in res["fields"] and code not in res["fields"]                       # the required one is absent: an error


def test_the_dashboard_and_the_lists_still_work_when_core_questions_are_switched_off(client):
    f = make_facility(1)
    put_report(f, "2026-02-10")
    for code in ("occ_pregnant", "occ_children", "extreme_pregnant", "extreme_children"):
        assert client.patch(f"/api/indicators/{code}", json={"active": False}).status_code == 200
    for path in ("/api/dashboard", "/api/regions-table?level=region", "/api/forecast", "/api/alerts", "/api/reports?size=5", "/api/control", "/api/export?fmt=xlsx&kind=custom&d1=2026-02-01&d2=2026-02-10", "/api/export?fmt=csv&kind=custom&d1=2026-02-01&d2=2026-02-10"):
        assert client.get(path).status_code == 200, path


def test_the_note_and_the_hints_are_switches_in_the_settings(client):
    s = client.get("/api/settings").json()["settings"]
    assert s["note_enabled"] == "1" and s["q_hints"] == "0"
    assert client.put("/api/settings", json={"note_enabled": "0", "q_hints": "true"}).status_code == 200
    s = client.get("/api/settings").json()["settings"]
    assert s["note_enabled"] == "0" and s["q_hints"] == "1"


def test_the_preview_shows_what_the_bot_sends(client):
    from app.db import connect
    r = client.get("/api/questionnaire/preview?lang=uz").json()
    assert r["lang"] == "uz" and len(r["items"]) == 13 and r["items"][0]["code"] == "beds_total" and "1-savol / 13" in r["items"][0]["text"] and r["items"][-1]["code"] == "__note"
    assert "Jami o‘rinlar" in r["items"][0]["text"] and "Hozir" not in r["items"][0]["text"]
    sev = next(x for x in r["items"] if x["code"] == "severe")["text"]
    assert "Ko‘pi bilan" in sev and "(2-savol)" not in sev and "…" in sev                              # a limit that comes from a rule: «not more than the answer to question N»
    client.put("/api/settings", json={"q_hints": "1", "note_enabled": "0"})
    r = client.get("/api/questionnaire/preview?lang=ru").json()
    assert len(r["items"]) == 12 and r["items"][-1]["code"] != "__note" and "Все койки учреждения" in r["items"][0]["text"] and "Вопрос 1 из 12" in r["items"][0]["text"]
    assert client.get("/api/questionnaire/preview").status_code == 200
