"""Command line: python -m app.cli init | password LOGIN | backup | verify | notify [--force] [--dry] | clear-data [--keep-facilities] [--yes]"""
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
    if cmd == "clear-data":
        return clear_data(keep_facilities="--keep-facilities" in argv, yes="--yes" in argv)
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
            did = c.execute("INSERT INTO districts(region_id, name_ru, name_uz) VALUES (?,?,?)", (rid, "Центральный район", "Markaziy tuman")).lastrowid
            for k in range(1, 4):
                fids.append(c.execute("INSERT INTO facilities(district_id, name_ru, name_uz, created_at) VALUES (?,?,?,datetime('now'))", (did, f"Больница №{k}", f"{k}-son shifoxona")).lastrowid)
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
                reports.admin_save(c, fid, d, {"beds_total": beds * 3, "beds_flu": beds, "beds_occupied": occ, "visits": visits, "severe": visits // 8, "occ_pregnant": min(1, occ), "occ_children": min(visits // 20, occ),
                                               "extreme": visits // 25, "extreme_pregnant": 0, "extreme_children": 0, "hosp": hosp, "disch": disch}, "демо", by)
    print("Добавлено учреждений:", len(fids))
    return 0




def clear_data(keep_facilities: bool = False, yes: bool = False) -> int:
    """Removes test data: all reports (with their version history) and, unless --keep-facilities, all facilities with their responsible-person links.
    Regions, districts, Telegram users and their region access, staff, settings and the audit log stay. Without --yes it only shows what would go.
    The immutability triggers of the history are lifted inside one transaction and put back; a backup is made first."""
    from . import db
    c = connect()
    try:
        cnt = lambda q: c.execute(q).fetchone()[0]
        plan = [("отчётов", cnt("SELECT COUNT(*) FROM reports")), ("записей истории версий", cnt("SELECT COUNT(*) FROM report_versions"))]
        if not keep_facilities:
            plan += [("учреждений", cnt("SELECT COUNT(*) FROM facilities")), ("привязок ответственных к учреждениям", cnt("SELECT COUNT(*) FROM assignments"))]
    finally:
        c.close()
    for what, n in plan:
        print(f"{'Будет удалено' if not yes else 'Удаляю'} {what}: {n}")
    if not yes:
        print("Ничего не изменено. Для удаления добавьте --yes (перед этим автоматически создаётся резервная копия).")
        return 0
    print("Резервная копия:", backup.make_now())
    with tx() as c:
        with db.history_unlocked(c):
            c.execute("DELETE FROM report_versions")
            c.execute("DELETE FROM report_values")
            c.execute("DELETE FROM reports")
        c.execute("DELETE FROM notify_log")
        c.execute("DELETE FROM bot_state")   # half-filled dialogues refer to the removed facilities
        if not keep_facilities:
            c.execute("DELETE FROM ministry_messages")
            c.execute("DELETE FROM assignments")
            c.execute("UPDATE access_requests SET facility_id=NULL WHERE facility_id IS NOT NULL")
            c.execute("DELETE FROM facilities")
        db.audit(c, "clear_data", "all", "", {"facilities": not keep_facilities}, actor="cli")
    print("Готово.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
