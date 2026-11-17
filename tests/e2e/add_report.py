import sys; import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app import db, reports
db.init_db()
with db.tx() as c:
    f = c.execute("SELECT id FROM facilities WHERE id NOT IN (SELECT facility_id FROM reports WHERE report_date=?) LIMIT 1", (db.today().isoformat(),)).fetchone()
    vals = dict(beds_total=100, beds_flu=40, beds_occupied=20, visits=50, severe=5, occ_pregnant=1, occ_children=1, extreme=1, extreme_pregnant=0, extreme_children=0, hosp=10, disch=6)
    reports.admin_save(c, f["id"], db.today().isoformat(), vals, "bot", {"kind": "tg", "id": 1, "name": "bot"})
print("report added for facility", f["id"])
