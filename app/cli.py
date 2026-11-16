"""Command line: python -m app.cli init | password LOGIN | backup | verify | notify [--force] [--dry]"""
import sys

from . import auth, backup, notify
from .db import connect, init_db, tx


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "init"
    if cmd == "init":
        init_db()
        return 0
    init_db()
    if cmd == "password" and len(argv) >= 2:
        pw = argv[2] if len(argv) > 2 else auth.generate_password()
        with tx() as c:
            if not c.execute("UPDATE staff SET password_hash=? WHERE login=?", (auth.hash_password(pw), auth.norm_login(argv[1]))).rowcount:
                print("Нет такого логина")
                return 1
        print(f"Пароль для {argv[1]}: {pw}")
        return 0
    if cmd == "backup":
        print(backup.make_now())
        return 0
    if cmd == "verify":
        r = backup.verify_latest()
        print(r)
        return 0 if r.get("ok") else 1
    if cmd == "notify":
        for x in notify.run_due(force="--force" in argv, dry="--dry" in argv):
            print(x)
        return 0
    if cmd == "demo":
        return demo()
    print(__doc__)
    return 2


def demo() -> int:
    """Test data: 3 facilities per region and 14 days of growing figures. Only for trying the system out."""
    import random
    from datetime import date, timedelta

    from . import reports
    from .db import today
    rnd = random.Random(7)
    by = {"kind": "staff", "id": 0, "name": "demo"}
    with tx() as c:
        if c.execute("SELECT COUNT(*) FROM facilities").fetchone()[0]:
            print("Учреждения уже есть, демо-данные не добавлены")
            return 1
        regs = [r["id"] for r in c.execute("SELECT id FROM regions ORDER BY sort")]
        fids = []
        for rid in regs:
            did = c.execute("INSERT INTO districts(region_id, name_ru) VALUES (?,?)", (rid, "Центральный район")).lastrowid
            for k in range(1, 4):
                fids.append(c.execute("INSERT INTO facilities(district_id, name_ru, created_at) VALUES (?,?,datetime('now'))", (did, f"Больница №{k}")).lastrowid)
        for i, fid in enumerate(fids):
            beds = rnd.randint(20, 80)
            occ = int(beds * rnd.uniform(.3, .7))
            for day in range(14, 0, -1):
                d = (today() - timedelta(days=day)).isoformat()
                if rnd.random() < .1:
                    continue
                visits = int(30 + (14 - day) * rnd.uniform(1, 3) + rnd.randint(0, 15))
                hosp, disch = rnd.randint(2, 10), rnd.randint(2, 9)
                occ = max(0, min(beds, occ + hosp - disch))
                reports.admin_save(c, fid, d, {"beds_total": beds * 3, "beds_flu": beds, "beds_occupied": occ, "visits": visits, "severe": visits // 8, "severe_pregnant": 1, "severe_children": visits // 20,
                                               "extreme": visits // 25, "extreme_pregnant": 0, "extreme_children": 0, "hosp": hosp, "disch": disch}, "демо", by)
    print("Добавлено учреждений:", len(fids))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
