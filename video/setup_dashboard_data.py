"""Demo data for the recording: 14 days of reports, today's reports from about two thirds of the facilities, Telegram users on the rest."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import cli, db, people, reports  # noqa: E402

db.init_db()
cli.demo()
rnd = random.Random(11)
ADJ = {"Республика Каракалпакстан": "Нукусская", "Андижанская область": "Андижанская", "Бухарская область": "Бухарская", "Джизакская область": "Джизакская", "Кашкадарьинская область": "Кашкадарьинская",
       "Навоийская область": "Навоийская", "Наманганская область": "Наманганская", "Самаркандская область": "Самаркандская", "Сурхандарьинская область": "Сурхандарьинская",
       "Сырдарьинская область": "Сырдарьинская", "Ташкентская область": "Ташкентская", "Ферганская область": "Ферганская", "Хорезмская область": "Хорезмская"}
by = {"kind": "staff", "id": 0, "name": "демо"}
with db.tx() as c:
    for r in c.execute("SELECT id, name_ru FROM regions").fetchall():
        fs = c.execute("SELECT f.id FROM facilities f JOIN districts d ON d.id=f.district_id WHERE d.region_id=? ORDER BY f.id", (r["id"],)).fetchall()
        names = (["Городская клиническая больница №1", "Инфекционная больница №2", "Детская городская больница №3"] if r["name_ru"] == "город Ташкент"
                 else [f"{ADJ[r['name_ru']]} областная инфекционная больница", f"{ADJ[r['name_ru']]} городская больница №1", f"{ADJ[r['name_ru']]} многопрофильная больница"])
        for f, n in zip(fs, names):
            c.execute("UPDATE facilities SET name_ru=? WHERE id=?", (n, f["id"]))
    # today: about two thirds have reported
    today = db.today().isoformat()
    yday = (db.today().__class__.fromordinal(db.today().toordinal() - 1)).isoformat()
    fids = [r["id"] for r in c.execute("SELECT id FROM facilities ORDER BY id")]
    rnd.shuffle(fids)
    cut = int(len(fids) * 0.66)
    for fid in fids[:cut]:
        rep = reports.find(c, fid, yday)
        if not rep:
            continue
        v = reports.values_of(c, rep["id"])
        v["visits"] = max(v["visits"] + rnd.randint(-3, 9), 5)
        v["severe"] = min(v["severe"] + rnd.randint(0, 2), v["visits"] // 2)
        v["hosp"] = max(v["hosp"] + rnd.randint(-1, 3), 0)
        v["beds_occupied"] = min(v["beds_occupied"] + rnd.randint(-2, 3), v["beds_flu"])
        reports.admin_save(c, fid, today, v, "демо", by)
    names = ["Мадина Юсупова", "Азиз Каримов", "Шахноза Рахимова", "Бобур Тошматов", "Дилноза Исмоилова", "Жасур Алиев", "Нигора Саидова", "Фарход Умаров", "Гулнора Хасанова", "Рустам Назаров"]
    for i, fid in enumerate(fids[cut:]):
        tid = str(500100 + i // 2)
        if i % 2 == 0:
            people.add_tg_user(c, tid, names[(i // 2) % len(names)])
        people.assign(c, {"id": 1, "role": "super_admin", "regions": None}, tid, fid)
print("ok", len(fids), "facilities;", len(fids) - cut, "not reported today")
