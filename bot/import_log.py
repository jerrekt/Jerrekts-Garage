#!/usr/bin/env python3
"""Import a service log JSON (data/logs/<car>.json) into the garage database.

Run on the garage container as the bot user, with GARAGE_DB set:
    runuser -u bot-garage -- env GARAGE_DB=/var/lib/garage-bot/garage.db \
        /opt/garage-bot/venv/bin/python /opt/garage-bot/src/bot/import_log.py \
        /opt/garage-bot/src/data/logs/e36.json --owner-id <discord id> --owner-name Jerrekt

Idempotent: everything this script wrote earlier for the same car (via='import') is
removed and written again, so re-running after fixing the JSON is safe. Work logged
from Discord is left alone. The car is created (active) if it does not exist.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app as g  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--owner-id", required=True)
    ap.add_argument("--owner-name", default="Jerrekt")
    ap.add_argument("--public", action="store_true", help="flag the car public (default: leave as is)")
    a = ap.parse_args()
    data = json.loads(Path(a.file).read_text())
    car, visits = data["car"], data["visits"]
    cid = g.slug(car["id"])
    now = time.time()
    with g._db_lock, g.db() as con:
        row = con.execute("SELECT id FROM cars WHERE id=?", (cid,)).fetchone()
        if row is None:
            con.execute("INSERT INTO cars(id, owner_id, owner_name, name, chassis, year, status, public, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                        (cid, a.owner_id, a.owner_name, car["name"], car.get("chassis", ""), car.get("year"), "active", 1 if a.public else 0, now))
            for job, match, miles, months, safety in g.DEFAULT_PLANS:
                con.execute("INSERT OR IGNORE INTO plans(car_id, job, match, miles, months, safety) VALUES(?,?,?,?,?,?)",
                            (cid, job, match, miles, months, safety))
            print(f"created {cid} ({car['name']})")
        elif a.public:
            con.execute("UPDATE cars SET public=1 WHERE id=?", (cid,))
        old = con.execute("SELECT id FROM visits WHERE car_id=? AND via='import'", (cid,)).fetchall()
        if old:
            con.executemany("DELETE FROM jobs WHERE visit_id=?", [(r["id"],) for r in old])
            con.execute("DELETE FROM visits WHERE car_id=? AND via='import'", (cid,))
            con.execute("DELETE FROM odometer WHERE car_id=? AND source='import'", (cid,))
            print(f"replaced {len(old)} earlier imported visits")
        n_jobs = 0
        for v in visits:
            raw = v.get("raw") or "; ".join(j["name"] for j in v["jobs"])
            cur = con.execute("INSERT INTO visits(car_id, on_date, miles, raw, created_by, via, at) VALUES(?,?,?,?,?,?,?)",
                              (cid, v.get("date"), v.get("miles"), g.clean(raw, 300), a.owner_name, "import", now))
            for j in v["jobs"]:
                con.execute("INSERT INTO jobs(visit_id, name, system, work_type, parts) VALUES(?,?,?,?,?)",
                            (cur.lastrowid, g.clean(j["name"], 120), j.get("system") or g.guess_system(j["name"]), j.get("type"), g.clean(j.get("parts", ""), 300)))
                n_jobs += 1
            if v.get("miles") is not None:
                con.execute("INSERT INTO odometer(car_id, miles, on_date, source, at) VALUES(?,?,?,?,?)",
                            (cid, v["miles"], v.get("date") or "", "import", now))
        g.audit(con, cid, a.owner_name, "import", "import", f"{len(visits)} visits, {n_jobs} jobs from {Path(a.file).name}")
        miles, _ = g.current_miles(con, cid)
        print(f"{cid}: {len(visits)} visits, {n_jobs} jobs; odometer now {miles:,} mi" if miles else f"{cid}: {len(visits)} visits, {n_jobs} jobs")
        for d in g.due_list(con, cid):
            print(f"  {d['label']:9} {d['job']}: {d['text']}")


if __name__ == "__main__":
    main()
