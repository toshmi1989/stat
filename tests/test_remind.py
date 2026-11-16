from conftest import make_facility, put_report
from test_api import mk_staff


def setup_people(monkeypatch):
    from app import people, tg
    from app.db import tx
    sent = []
    monkeypatch.setattr(tg, "send", lambda chat, text, markup=None: (sent.append((str(chat), text)) or (True, "")))
    f1, f2, f3, f4 = make_facility(1, fac="A"), make_facility(1, "Район Б", "B"), make_facility(2, "Район В", "C"), make_facility(2, "Район В", "D")
    with tx() as c:
        for uid, f in (("10001", f1), ("10002", f2), ("10003", f3)):
            people.add_tg_user(c, uid, "x" + uid)
            people.assign(c, {"id": 1, "role": "super_admin", "regions": None}, uid, f)
    put_report(f2, "2026-02-10")                 # B has reported; A and C have not; D has nobody responsible
    return sent, (f1, f2, f3, f4)


def test_preview_then_send(client, monkeypatch):
    sent, _ = setup_people(monkeypatch)
    pre = client.post("/api/notify/remind", json={"date": "2026-02-10", "dry": True}).json()
    assert pre["dry"] and pre["people"] == 2 and pre["missing"] == 3 and pre["no_responsible_total"] == 1
    assert sent == []                              # the preview sends nothing
    r = client.post("/api/notify/remind", json={"date": "2026-02-10", "dry": False}).json()
    assert r["sent"] == 2 and sorted(c for c, _ in sent) == ["10001", "10003"]
    assert all("не отправлен" in t for _, t in sent)
    again = client.post("/api/notify/remind", json={"date": "2026-02-10", "dry": False}).json()
    assert again["sent"] == 0 and again["skipped"] == 2 and len(sent) == 2     # no repeat within the hour


def test_regional_admin_reminds_only_own_region(client, monkeypatch):
    sent, _ = setup_people(monkeypatch)
    a = mk_staff(client, "reg1", "admin", [1])
    r = a.post("/api/notify/remind", json={"date": "2026-02-10", "dry": False}).json()
    assert r["sent"] == 1 and [c for c, _ in sent] == ["10001"]
    assert a.post("/api/notify/remind", json={"date": "2026-02-10", "region_id": 2}).status_code == 403


def test_viewer_cannot_remind(client, monkeypatch):
    setup_people(monkeypatch)
    v = mk_staff(client, "view1", "viewer")
    assert v.post("/api/notify/remind", json={"dry": False}).status_code == 403


def test_region_manager_is_reminded_with_the_list(client, monkeypatch):
    from app import people
    from app.db import tx
    sent, (f1, f2, f3, f4) = setup_people(monkeypatch)
    with tx() as c:
        people.add_tg_user(c, "20001", "Региональный")
        people.assign_region(c, {"id": 1, "role": "super_admin", "regions": None}, "20001", 2)
    r = client.post("/api/notify/remind", json={"date": "2026-02-10", "dry": False}).json()
    mgr = [t for c, t in sent if c == "20001"]
    assert len(mgr) == 1 and "C" in mgr[0] and "D" in mgr[0]
    assert r["no_responsible_total"] == 0          # D now has a responsible person: the region manager
