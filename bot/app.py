"""Jerrekt's Garage bot.

Owners log work on their cars from Discord (slash commands) or from the site
after signing in with Discord. This server holds the cars, visits, odometer readings and intervals in
SQLite, works out what is due, and answers the public and private sites over
a small read API.

Who can do what:
  - Discord users on the allow list (DISCORD_USERS) can add cars and log work.
    A car added by anyone but the admin starts "pending" until the admin runs
    /garage approve. Pending cars accept logs but are hidden from every list
    except the owner's and the admin's.
  - Every write and every read of a car checks the owner. Friends never see
    each other's cars. The admin sees all.
  - The public export (/api/public) carries only cars flagged public, and
    never VINs, plates or owners' Discord IDs. Nothing here stores a VIN.

Every setting comes from environment variables (see deploy/bot.env.example).
No secret is ever written in this repo.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from starlette.concurrency import run_in_threadpool

log = logging.getLogger("garage-bot")

WORK_TYPES = ("preventive", "corrective", "diagnostic", "upgrade")
SYSTEMS = ("engine", "cooling", "drivetrain", "suspension", "steering", "brakes", "tires", "body", "electrical", "other")
DISCORD_MAX_AGE = 300
WEBHOOK_PREFIXES = ("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")
MAX_TEXT = 200
SOON = 0.15  # "due soon" inside this fraction of the interval


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


class Config:
    @property
    def db_path(self): return env("GARAGE_DB", "garage.db")
    @property
    def discord_key(self): return env("DISCORD_PUBLIC_KEY")
    @property
    def admin_id(self): return env("GARAGE_ADMIN_ID")          # Discord user id of the owner
    @property
    def admin_name(self): return env("GARAGE_ADMIN_NAME", "Jerrekt")
    @property
    def webhook(self): return env("DISCORD_WEBHOOK_URL")
    @property
    def origin(self): return env("GARAGE_ALLOWED_ORIGIN", "https://garage.adsuaracloud.com")
    @property
    def kits_path(self): return env("GARAGE_KITS_PATH")         # JSON file of job kits (FCP links)
    @property
    def site_token(self): return env("GARAGE_SITE_TOKEN")       # secret that signs the site's session cookies
    @property
    def client_id(self): return env("DISCORD_CLIENT_ID")        # Discord OAuth2 (sign in on the site)
    @property
    def client_secret(self): return env("DISCORD_CLIENT_SECRET")

    @property
    def discord_users(self) -> dict[str, str]:
        """DISCORD_USERS="1234:Branden,5678:Jason" -> {"1234": "Branden", ...}"""
        out = {}
        for pair in env("DISCORD_USERS").split(","):
            if ":" in pair:
                uid, name = pair.split(":", 1)
                if uid.strip().isdigit() and name.strip():
                    out[uid.strip()] = name.strip()
        return out


CFG = Config()


# ---------- helpers ----------

def clean(text, limit: int = MAX_TEXT) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]", " ", str(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", clean(text, 40).lower()).strip("-")
    return s or "car"


def parse_miles(v) -> int:
    try:
        m = int(str(v).replace(",", "").strip())
    except ValueError:
        raise HTTPException(400, "Miles must be a whole number.")
    if not 0 <= m <= 2_000_000:
        raise HTTPException(400, "Miles out of range.")
    return m


def parse_date(v) -> str:
    """Accept YYYY-MM-DD or YYYY-MM; today when empty."""
    v = clean(v, 10)
    if not v:
        return date.today().isoformat()
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(v, fmt).date().isoformat() if fmt == "%Y-%m-%d" else v
        except ValueError:
            pass
    raise HTTPException(400, "Date must be YYYY-MM-DD or YYYY-MM.")


class Limiter:
    def __init__(self):
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def over(self, key: str, limit: int, window: float) -> bool:
        now = time.time()
        with self.lock:
            q = self.hits[key]
            while q and q[0] <= now - window:
                q.popleft()
            return len(q) >= limit

    def add(self, key: str):
        with self.lock:
            self.hits[key].append(time.time())

    def reset(self):
        with self.lock:
            self.hits.clear()


LIMITS = Limiter()
WRITE_LIMIT, WRITE_WINDOW = 30, 600
FEED_LIMIT, FEED_WINDOW = 120, 3600


# ---------- database ----------

_db_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS cars(
  id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, owner_name TEXT NOT NULL,
  name TEXT NOT NULL, chassis TEXT NOT NULL DEFAULT '', year INTEGER,
  status TEXT NOT NULL DEFAULT 'pending', public INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS odometer(
  id INTEGER PRIMARY KEY AUTOINCREMENT, car_id TEXT NOT NULL, miles INTEGER NOT NULL,
  on_date TEXT NOT NULL, source TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS visits(
  id INTEGER PRIMARY KEY AUTOINCREMENT, car_id TEXT NOT NULL, on_date TEXT, miles INTEGER,
  raw TEXT NOT NULL DEFAULT '', created_by TEXT NOT NULL, via TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, visit_id INTEGER NOT NULL, name TEXT NOT NULL,
  system TEXT NOT NULL DEFAULT 'other', work_type TEXT, parts TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS plans(
  car_id TEXT NOT NULL, job TEXT NOT NULL, match TEXT NOT NULL, miles INTEGER, months INTEGER,
  safety INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(car_id, job));
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT, car_id TEXT, actor TEXT, via TEXT, action TEXT, detail TEXT, at REAL);
"""

DEFAULT_PLANS = [  # placeholders until the owner sets their own; same as the mock
    ("Oil change", "oil change", 5000, 12, 0),
    ("Coolant", "coolant", None, 24, 0),
    ("Brake fluid", "brake fluid", None, 24, 1),
    ("Engine air filter", "air filter", 15000, 36, 0),
    ("Spark plugs", "spark plug", 30000, None, 0),
    ("Diff oil", "diff oil", 30000, 48, 0),
    ("Alignment", "alignment", 12000, None, 0),
    ("Brake pads", "pads", 30000, None, 1),
]


def db() -> sqlite3.Connection:
    con = sqlite3.connect(CFG.db_path, timeout=5)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def audit(con, car_id, actor, via, action, detail=""):
    con.execute("INSERT INTO audit(car_id, actor, via, action, detail, at) VALUES(?,?,?,?,?,?)",
                (car_id, actor, via, action, clean(detail, 300), time.time()))


# ---------- cars and access ----------

class Who:
    def __init__(self, uid: str, name: str):
        self.id, self.name = uid, name
        self.is_admin = bool(CFG.admin_id) and uid == CFG.admin_id


def get_car(con, car_id: str, who: Who) -> sqlite3.Row:
    car = con.execute("SELECT * FROM cars WHERE id=?", (slug(car_id),)).fetchone()
    if car is None or (car["owner_id"] != who.id and not who.is_admin):
        # Same answer whether it is missing or someone else's: no probing.
        raise HTTPException(404, f"No car called {slug(car_id)} that you can see.")
    return car


def visible_cars(con, who: Who) -> list[sqlite3.Row]:
    if who.is_admin:
        return con.execute("SELECT * FROM cars ORDER BY created_at").fetchall()
    return con.execute("SELECT * FROM cars WHERE owner_id=? ORDER BY created_at", (who.id,)).fetchall()


def known_user(con, uid: str, fallback_name: str = "") -> Who | None:
    """Who this Discord user is to the garage: on the allow list, or the owner of a car
    that is not rejected (someone who signed in on the site and added one)."""
    name = CFG.discord_users.get(uid)
    if not name:
        r = con.execute("SELECT owner_name FROM cars WHERE owner_id=? AND status!='rejected' ORDER BY created_at LIMIT 1", (uid,)).fetchone()
        name = r["owner_name"] if r else ""
    return Who(uid, name or fallback_name) if name else None


def add_car(who: Who, name: str, chassis: str = "", year=None, miles=None, via="discord") -> dict:
    name = clean(name, 60)
    if not name:
        raise HTTPException(400, "Give the car a name, like 2008 Civic Si.")
    base = slug(chassis or name)
    with _db_lock, db() as con:
        # Someone not on the allow list may have one car waiting for approval, not a pile.
        if not who.is_admin and who.id not in CFG.discord_users and \
                con.execute("SELECT 1 FROM cars WHERE owner_id=? AND status='pending'", (who.id,)).fetchone():
            raise HTTPException(403, f"You already have a car waiting for {CFG.admin_name}.")
        cid, n = base, 2
        while con.execute("SELECT 1 FROM cars WHERE id=?", (cid,)).fetchone():
            cid, n = f"{base}-{n}", n + 1
        status = "active" if who.is_admin else "pending"
        now = time.time()
        con.execute("INSERT INTO cars(id, owner_id, owner_name, name, chassis, year, status, public, created_at) VALUES(?,?,?,?,?,?,?,0,?)",
                    (cid, who.id, who.name, name, clean(chassis, 20), int(year) if year else None, status, now))
        for job, match, mi, mo, safe in DEFAULT_PLANS:
            con.execute("INSERT OR IGNORE INTO plans(car_id, job, match, miles, months, safety) VALUES(?,?,?,?,?,?)",
                        (cid, job, match, mi, mo, safe))
        if miles is not None:
            m = parse_miles(miles)
            con.execute("INSERT INTO odometer(car_id, miles, on_date, source, at) VALUES(?,?,?,?,?)",
                        (cid, m, date.today().isoformat(), via, now))
        audit(con, cid, who.name, via, "addcar", f"{name} {status}")
        return car_dict(con, con.execute("SELECT * FROM cars WHERE id=?", (cid,)).fetchone())


def set_status(who: Who, car_id: str, status: str, via="discord") -> dict:
    if not who.is_admin:
        raise HTTPException(403, f"Only {CFG.admin_name} can do that.")
    with _db_lock, db() as con:
        car = con.execute("SELECT * FROM cars WHERE id=?", (slug(car_id),)).fetchone()
        if car is None:
            raise HTTPException(404, "No such car.")
        con.execute("UPDATE cars SET status=? WHERE id=?", (status, car["id"]))
        audit(con, car["id"], who.name, via, status)
        return car_dict(con, con.execute("SELECT * FROM cars WHERE id=?", (car["id"],)).fetchone())


def remove_car(who: Who, car_id: str, via="discord") -> str:
    with _db_lock, db() as con:
        car = get_car(con, car_id, who)
        for t in ("odometer", "visits", "plans"):
            con.execute(f"DELETE FROM {t} WHERE car_id=?", (car["id"],))
        con.execute("DELETE FROM jobs WHERE visit_id NOT IN (SELECT id FROM visits)")
        con.execute("DELETE FROM cars WHERE id=?", (car["id"],))
        audit(con, car["id"], who.name, via, "remove")
        return car["id"]


# ---------- odometer, visits, due ----------

def current_miles(con, car_id: str):
    r = con.execute("SELECT miles, on_date FROM odometer WHERE car_id=? ORDER BY miles DESC, at DESC LIMIT 1", (car_id,)).fetchone()
    return (r["miles"], r["on_date"]) if r else (None, None)


def log_odo(who: Who, car_id: str, miles, on_date="", via="discord") -> dict:
    m = parse_miles(miles)
    d = parse_date(on_date)
    with _db_lock, db() as con:
        car = get_car(con, car_id, who)
        cur, _ = current_miles(con, car["id"])
        warn = ""
        if cur is not None and m < cur:
            warn = f" Lower than the last reading ({cur:,}); kept, but check it."
        con.execute("INSERT INTO odometer(car_id, miles, on_date, source, at) VALUES(?,?,?,?,?)",
                    (car["id"], m, d, via, time.time()))
        audit(con, car["id"], who.name, via, "odo", str(m))
        return {"car": car["id"], "miles": m, "date": d, "warning": warn.strip()}


def log_work(who: Who, car_id: str, job: str, miles=None, on_date="", work_type="", system="", parts="", via="discord") -> dict:
    job = clean(job, 120)
    if not job:
        raise HTTPException(400, "Say what you did, like Oil change 5W-40.")
    if work_type and work_type not in WORK_TYPES:
        raise HTTPException(400, "Type must be preventive, corrective, diagnostic or upgrade.")
    system = system if system in SYSTEMS else guess_system(job)
    d = parse_date(on_date)
    with _db_lock, db() as con:
        car = get_car(con, car_id, who)
        m = parse_miles(miles) if miles not in (None, "") else current_miles(con, car["id"])[0]
        now = time.time()
        cur = con.execute("INSERT INTO visits(car_id, on_date, miles, raw, created_by, via, at) VALUES(?,?,?,?,?,?,?)",
                          (car["id"], d, m, job, who.name, via, now))
        vid = cur.lastrowid
        con.execute("INSERT INTO jobs(visit_id, name, system, work_type, parts) VALUES(?,?,?,?,?)",
                    (vid, job, system, work_type or None, clean(parts, 300)))
        if m is not None:
            con.execute("INSERT INTO odometer(car_id, miles, on_date, source, at) VALUES(?,?,?,?,?)",
                        (car["id"], m, d, "log", now))
        audit(con, car["id"], who.name, via, "log", f"{job} @ {m}")
        nxt = next_due_for(con, car["id"], job)
        return {"car": car["id"], "visit": vid, "job": job, "miles": m, "date": d, "system": system, "next": nxt}


def guess_system(job: str) -> str:
    j = job.lower()
    table = [("cooling", ("radiator", "coolant", "hose", "thermostat", "water pump", "fan")),
             ("brakes", ("brake", "rotor", "pad", "caliper")),
             ("tires", ("tire", "wheel", "rotation")),
             ("steering", ("steering", "tie rod", "rack")),
             ("suspension", ("coilover", "shock", "strut", "sway", "control arm", "bushing", "ball joint", "alignment", "camber")),
             ("drivetrain", ("diff", "clutch", "transmission", "driveshaft", "axle", "guibo")),
             ("electrical", ("battery", "alternator", "sensor", "coil", "bulb", "wiring")),
             ("engine", ("oil", "spark", "plug", "valve", "gasket", "filter", "belt", "manifold", "vanos", "injector", "throttle", "timing"))]
    for sys_, words in table:
        if any(w in j for w in words):
            return sys_
    return "other"


def due_list(con, car_id: str, today: date | None = None) -> list[dict]:
    today = today or date.today()
    miles_now, _ = current_miles(con, car_id)
    plans = con.execute("SELECT * FROM plans WHERE car_id=? ORDER BY job", (car_id,)).fetchall()
    out = []
    for p in plans:
        last = con.execute("""SELECT v.on_date, v.miles FROM jobs j JOIN visits v ON v.id=j.visit_id
            WHERE v.car_id=? AND lower(j.name) LIKE ? ORDER BY v.miles DESC, v.at DESC LIMIT 1""",
                           (car_id, f"%{p['match']}%")).fetchone()
        item = {"job": p["job"], "miles": p["miles"], "months": p["months"], "safety": bool(p["safety"])}
        if last is None:
            item.update(status="unknown", label="No record", text="Never logged", last=None)
            out.append(item)
            continue
        worst, parts = 1.0, []
        if p["miles"] and last["miles"] is not None and miles_now is not None:
            left = last["miles"] + p["miles"] - miles_now
            worst = min(worst, left / p["miles"])
            parts.append(f"{abs(left):,} mi {'over' if left < 0 else 'left'}")
        if p["months"] and last["on_date"]:
            try:
                ld = datetime.strptime(last["on_date"][:10] if len(last["on_date"]) > 7 else last["on_date"] + "-01", "%Y-%m-%d").date()
                dd = ld + timedelta(days=round(p["months"] * 30.44))
                days = (dd - today).days
                worst = min(worst, days / (p["months"] * 30.44))
                parts.append(f"{abs(days) // 30} months over" if days < 0 else f"by {dd.strftime('%b %Y')}")
            except ValueError:
                pass
        if not parts:
            item.update(status="unknown", label="No record", text="Mileage or date missing")
        else:
            st = "overdue" if worst < 0 else "soon" if worst < SOON else "ok"
            item.update(status=st, label={"overdue": "Overdue", "soon": "Due soon", "ok": "OK"}[st], text=", ".join(parts))
        item["last"] = {"date": last["on_date"], "miles": last["miles"]}
        out.append(item)
    order = {"overdue": 0, "soon": 1, "unknown": 2, "ok": 3}
    return sorted(out, key=lambda x: order[x["status"]])


def next_due_for(con, car_id: str, job: str) -> str:
    for d in due_list(con, car_id):
        if d["status"] != "unknown" and d["job"].lower().split()[0] in job.lower():
            return d["text"]
    return ""


def car_dict(con, car) -> dict:
    miles, on_date = current_miles(con, car["id"])
    return {"id": car["id"], "name": car["name"], "chassis": car["chassis"], "year": car["year"],
            "owner": car["owner_name"], "status": car["status"], "public": bool(car["public"]),
            "odometer": {"miles": miles, "date": on_date}}


def car_full(con, car) -> dict:
    d = car_dict(con, car)
    visits = con.execute("SELECT * FROM visits WHERE car_id=? ORDER BY miles DESC, on_date DESC, id DESC", (car["id"],)).fetchall()
    out = []
    for v in visits:
        jobs = con.execute("SELECT name, system, work_type, parts FROM jobs WHERE visit_id=?", (v["id"],)).fetchall()
        out.append({"id": v["id"], "date": v["on_date"], "miles": v["miles"], "raw": v["raw"],
                    "jobs": [dict(j) for j in jobs]})
    d.update(visits=out, due=due_list(con, car["id"]))
    return d


# ---------- kits (FCP job kits, read-only JSON) ----------

_kits = {"data": None, "at": 0.0}


def load_kits() -> list[dict]:
    if not CFG.kits_path:
        return []
    if _kits["data"] is not None and time.time() - _kits["at"] < 60:
        return _kits["data"]
    try:
        data = json.loads(Path(CFG.kits_path).read_text())
        _kits.update(data=data.get("jobs", []), at=time.time())
    except Exception as e:
        log.warning("kits load failed: %s", e)
        if _kits["data"] is None:
            return []
    return _kits["data"]


# ---------- feed ----------

def post_feed(text: str):
    url = CFG.webhook
    if not url.startswith(WEBHOOK_PREFIXES):
        return
    if LIMITS.over("feed", FEED_LIMIT, FEED_WINDOW):
        log.warning("feed cap reached, not posting")
        return
    LIMITS.add("feed")
    try:
        httpx.post(url, json={"content": text[:1900], "allowed_mentions": {"parse": []}}, timeout=8)
    except Exception as e:
        log.warning("feed post failed: %s", e)


# ---------- app ----------

app = FastAPI(title="Jerrekt's Garage", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(CORSMiddleware, allow_origins=[CFG.origin], allow_methods=["GET"],
                   allow_headers=["Content-Type"], max_age=600)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/public")
def api_public():
    """What the public page may show: public cars, no owners, no ids beyond the slug."""
    with _db_lock, db() as con:
        cars = con.execute("SELECT * FROM cars WHERE public=1 AND status='active'").fetchall()
        out = []
        for c in cars:
            d = car_full(con, c)
            d.pop("owner", None)
            out.append(d)
    return JSONResponse({"cars": out, "generated": time.time()}, headers={"Cache-Control": "no-store"})


# ---------- the site: Discord sign-in, session cookie, private API ----------
# One URL for everyone. The public part needs no sign-in. "Sign in with Discord"
# sends the browser to Discord (scope: identify only), Discord sends it back here
# with a code, we swap the code for the user's id and name, and set a signed,
# HttpOnly cookie. No password, nothing from Discord stored beyond id and name.

SESSION_COOKIE, STATE_COOKIE = "garage_s", "garage_o"
SESSION_DAYS = 30
DISCORD_API = "https://discord.com/api/v10"


def _sign(payload: dict, ttl: int) -> str:
    body = json.dumps({**payload, "exp": int(time.time()) + ttl}, separators=(",", ":")).encode()
    b = base64.urlsafe_b64encode(body).decode().rstrip("=")
    mac = hmac.new(CFG.site_token.encode(), b.encode(), hashlib.sha256).hexdigest()
    return f"{b}.{mac}"


def _verify(token: str) -> dict | None:
    if not token or "." not in token or not CFG.site_token:
        return None
    b, mac = token.rsplit(".", 1)
    want = hmac.new(CFG.site_token.encode(), b.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, want):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)))
    except Exception:
        return None
    return data if data.get("exp", 0) > time.time() else None


def _secure() -> bool:
    return CFG.origin.startswith("https://")


def set_cookie(resp: Response, name: str, value: str, max_age: int):
    resp.set_cookie(name, value, max_age=max_age, httponly=True, secure=_secure(), samesite="lax", path="/")


def session(request: Request) -> dict | None:
    return _verify(request.cookies.get(SESSION_COOKIE, ""))


def web_user(request: Request) -> Who:
    """Signed-in and known to the garage; the private API needs both."""
    sess = session(request)
    if not sess:
        raise HTTPException(401, "Not signed in.")
    with _db_lock, db() as con:
        who = known_user(con, str(sess.get("uid", "")), sess.get("name", ""))
    if who is None:
        raise HTTPException(403, "Not on the list yet.")
    return who


def same_site(request: Request):
    """Writes must come from our own page: the custom header forces a CORS preflight for
    anyone else, and the Origin must match. Together with SameSite=Lax that stops CSRF."""
    if request.headers.get("x-garage-web") != "1":
        raise HTTPException(403, "Bad request origin.")
    origin = request.headers.get("origin", "")
    if origin and origin != CFG.origin:
        raise HTTPException(403, "Bad request origin.")


@app.get("/auth/login")
def auth_login():
    if not CFG.client_id:
        raise HTTPException(503, "Sign-in is not set up.")
    state = secrets.token_urlsafe(24)
    q = urlencode({"client_id": CFG.client_id, "response_type": "code", "scope": "identify",
                   "redirect_uri": CFG.origin + "/auth/callback", "state": state, "prompt": "none"})
    resp = RedirectResponse("https://discord.com/oauth2/authorize?" + q, status_code=302)
    set_cookie(resp, STATE_COOKIE, _sign({"s": state}, 600), 600)
    return resp


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    st = _verify(request.cookies.get(STATE_COOKIE, ""))
    if error or not code or not st or not hmac.compare_digest(st.get("s", ""), state):
        return RedirectResponse("/?signin=failed", status_code=302)
    if LIMITS.over("oauth", 60, 600):
        raise HTTPException(429, "Too many sign-ins right now.")
    LIMITS.add("oauth")
    try:
        async with httpx.AsyncClient(timeout=10) as cl:
            tok = await cl.post(f"{DISCORD_API}/oauth2/token", data={
                "grant_type": "authorization_code", "code": code, "redirect_uri": CFG.origin + "/auth/callback"},
                auth=(CFG.client_id, CFG.client_secret))
            tok.raise_for_status()
            me = await cl.get(f"{DISCORD_API}/users/@me", headers={"Authorization": "Bearer " + tok.json()["access_token"]})
            me.raise_for_status()
            u = me.json()
    except Exception as e:
        log.warning("discord sign-in failed: %s", e)
        return RedirectResponse("/?signin=failed", status_code=302)
    uid = str(u.get("id", ""))
    if not uid.isdigit():
        return RedirectResponse("/?signin=failed", status_code=302)
    name = clean(u.get("global_name") or u.get("username") or "someone", 32)
    resp = RedirectResponse("/#garage", status_code=302)
    set_cookie(resp, SESSION_COOKIE, _sign({"uid": uid, "name": name}, SESSION_DAYS * 86400), SESSION_DAYS * 86400)
    resp.delete_cookie(STATE_COOKIE, path="/")
    return resp


@app.post("/auth/logout")
def auth_logout(request: Request):
    same_site(request)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@app.get("/api/me")
def api_me(request: Request):
    """Everything the signed-in person may see. Not signed in: just that. Signed in but
    unknown: their name, so the page can offer to add a car (which makes them known, pending)."""
    sess = session(request)
    hdr = {"Cache-Control": "no-store"}
    if not sess:
        return JSONResponse({"signed_in": False, "login": bool(CFG.client_id)}, headers=hdr)
    uid, dname = str(sess.get("uid", "")), sess.get("name", "")
    with _db_lock, db() as con:
        who = known_user(con, uid, dname)
        if who is None:
            return JSONResponse({"signed_in": True, "known": False, "user": {"name": dname}, "admin_name": CFG.admin_name}, headers=hdr)
        cars = [car_full(con, c) for c in visible_cars(con, who)]
    return JSONResponse({"signed_in": True, "known": True, "user": {"name": who.name}, "admin": who.is_admin,
                         "admin_name": CFG.admin_name, "cars": cars, "kits": load_kits()}, headers=hdr)


@app.post("/api/act")
async def api_act(request: Request, bg: BackgroundTasks):
    """Writes from the page. Same actions as the slash commands, same checks."""
    same_site(request)
    sess = session(request)
    if not sess:
        raise HTTPException(401, "Not signed in.")
    uid, dname = str(sess.get("uid", "")), sess.get("name", "")
    if LIMITS.over("web:" + uid, WRITE_LIMIT, WRITE_WINDOW):
        raise HTTPException(429, "Too many changes. Wait a few minutes.")
    LIMITS.add("web:" + uid)
    try:
        o = await request.json()
    except Exception:
        raise HTTPException(400, "Bad JSON.")
    if not isinstance(o, dict):
        raise HTTPException(400, "Bad JSON.")
    act = o.get("action", "")
    return await run_in_threadpool(web_action, uid, dname, act, o, bg)


def web_action(uid: str, dname: str, act: str, o: dict, bg: BackgroundTasks) -> dict:
    with _db_lock, db() as con:
        who = known_user(con, uid, dname)
        if who is None:
            if act != "addcar":
                raise HTTPException(403, "Not on the list yet.")
            who = Who(uid, clean(dname, 32) or "someone")  # add_car caps strangers at one pending car
    name = who.name
    if act == "addcar":
        c = add_car(who, o.get("name", ""), o.get("chassis", ""), o.get("year"), o.get("miles"), via="web")
        if c["status"] == "pending":
            bg.add_task(post_feed, f"**{name}** added **{c['name']}** (`{c['id']}`) on the site. {CFG.admin_name}: `/garage approve car:{c['id']}`")
        else:
            bg.add_task(post_feed, f"**{name}** added **{c['name']}** (`{c['id']}`).")
        return {"ok": True, "car": c}
    if act in ("approve", "reject"):
        c = set_status(who, o.get("car", ""), "active" if act == "approve" else "rejected", via="web")
        bg.add_task(post_feed, f"**{name}** {act}d **{c['name']}** (`{c['id']}`), owner {c['owner']}.")
        return {"ok": True, "car": c}
    if act == "odo":
        r = log_odo(who, o.get("car", ""), o.get("miles"), o.get("date", ""), via="web")
        return {"ok": True, **r}
    if act == "log":
        r = log_work(who, o.get("car", ""), o.get("job", ""), o.get("miles"), o.get("date", ""),
                     o.get("type", ""), o.get("system", ""), o.get("parts", ""), via="web")
        m = f"{r['miles']:,} mi" if r["miles"] is not None else "no mileage"
        bg.add_task(post_feed, f"**{name}** logged **{r['job']}** on `{r['car']}` at {m}." + (f" Next: {r['next']}." if r["next"] else ""))
        return {"ok": True, **r}
    if act == "remove":
        cid = remove_car(who, o.get("car", ""), via="web")
        bg.add_task(post_feed, f"**{name}** removed `{cid}` and its log.")
        return {"ok": True, "car": cid}
    if act == "public":
        if not who.is_admin:
            raise HTTPException(403, f"Only {CFG.admin_name} can change what's public.")
        with _db_lock, db() as con:
            car = get_car(con, o.get("car", ""), who)
            on = 1 if o.get("show") else 0
            con.execute("UPDATE cars SET public=? WHERE id=?", (on, car["id"]))
            audit(con, car["id"], name, "web", "public", str(on))
        return {"ok": True, "car": car["id"], "public": bool(on)}
    raise HTTPException(400, "Unknown action.")


# ---------- Discord interactions ----------

def verify_discord(body: bytes, sig: str, ts: str) -> None:
    key = CFG.discord_key
    if not key:
        raise HTTPException(503, "Discord is not set up.")
    try:
        if abs(time.time() - int(ts)) > DISCORD_MAX_AGE:
            raise ValueError("stale")
        VerifyKey(bytes.fromhex(key)).verify(ts.encode() + body, bytes.fromhex(sig))
    except (BadSignatureError, ValueError, TypeError):
        raise HTTPException(401, "invalid request signature")


def reply(text: str) -> dict:
    return {"type": 4, "data": {"content": text[:1900], "flags": 64, "allowed_mentions": {"parse": []}}}


@app.post("/discord/interactions")
async def discord(request: Request, bg: BackgroundTasks):
    body = await request.body()
    verify_discord(body, request.headers.get("x-signature-ed25519", ""), request.headers.get("x-signature-timestamp", ""))
    data = json.loads(body)
    if data.get("type") == 1:
        return {"type": 1}
    if data.get("type") != 2:
        return reply("Unsupported interaction.")
    return await run_in_threadpool(handle_command, data, bg)


def options(data: dict) -> tuple[str, dict]:
    d = data.get("data") or {}
    opts = d.get("options") or []
    # /garage <sub> ...  -> first option is the subcommand
    if opts and opts[0].get("type") == 1:
        sub = opts[0]
        return sub.get("name", ""), {o.get("name"): o.get("value") for o in sub.get("options") or []}
    return d.get("name", ""), {o.get("name"): o.get("value") for o in opts}


def handle_command(data: dict, bg: BackgroundTasks) -> dict:
    user = (data.get("member") or {}).get("user") or data.get("user") or {}
    uid = str(user.get("id", ""))
    with _db_lock, db() as con:
        who = known_user(con, uid)
    if who is None:
        return reply(f"You're not on the garage list yet. Ask {CFG.admin_name} to add you, or sign in on {CFG.origin} and add your car.")
    name = who.name
    if LIMITS.over("discord:" + uid, WRITE_LIMIT, WRITE_WINDOW):
        return reply("Too many commands. Wait a few minutes.")
    LIMITS.add("discord:" + uid)
    sub, o = options(data)
    try:
        if sub == "cars":
            with _db_lock, db() as con:
                cars = visible_cars(con, who)
                if not cars:
                    return reply("No cars yet. Add one with /garage addcar.")
                lines = []
                for c in cars:
                    m, d = current_miles(con, c["id"])
                    due = [x for x in due_list(con, c["id"]) if x["status"] == "overdue"]
                    line = f"`{c['id']}` {c['name']} · " + (f"{m:,} mi · {len(due)} overdue" if m is not None else "no mileage yet")
                    if c["status"] != "active":
                        line += f" · {c['status']}"
                    if who.is_admin and c["owner_id"] != who.id:
                        line += f" · {c['owner_name']}"
                    lines.append(line)
                return reply("\n".join(lines))
        if sub == "addcar":
            c = add_car(who, o.get("name", ""), o.get("chassis", ""), o.get("year"), o.get("miles"))
            if c["status"] == "pending":
                bg.add_task(post_feed, f"**{name}** added **{c['name']}** (`{c['id']}`). {CFG.admin_name}: `/garage approve car:{c['id']}`")
                return reply(f"Added `{c['id']}` {c['name']}. It's pending until {CFG.admin_name} approves it; you can log work meanwhile.")
            bg.add_task(post_feed, f"**{name}** added **{c['name']}** (`{c['id']}`).")
            return reply(f"Added `{c['id']}` {c['name']}.")
        if sub in ("approve", "reject"):
            c = set_status(who, o.get("car", ""), "active" if sub == "approve" else "rejected")
            bg.add_task(post_feed, f"**{name}** {sub}d **{c['name']}** (`{c['id']}`), owner {c['owner']}.")
            return reply(f"{c['id']} is now {c['status']}.")
        if sub == "odo":
            r = log_odo(who, o.get("car", ""), o.get("miles"), o.get("date", ""))
            return reply(f"`{r['car']}` at {r['miles']:,} mi ({r['date']}).{(' ' + r['warning']) if r['warning'] else ''}")
        if sub == "log":
            r = log_work(who, o.get("car", ""), o.get("job", ""), o.get("miles"), o.get("date", ""),
                         o.get("type", ""), o.get("system", ""), o.get("parts", ""))
            m = f"{r['miles']:,} mi" if r["miles"] is not None else "no mileage"
            nxt = f" Next: {r['next']}." if r["next"] else ""
            bg.add_task(post_feed, f"**{name}** logged **{r['job']}** on `{r['car']}` at {m}.{nxt}")
            return reply(f"Logged {r['job']} on `{r['car']}` at {m}, {r['system']}.{nxt}")
        if sub == "due":
            with _db_lock, db() as con:
                car = get_car(con, o.get("car", ""), who)
                items = due_list(con, car["id"])
            lines = [f"{'⚠️ ' if i['safety'] and i['status'] != 'ok' else ''}**{i['job']}** · {i['label']} · {i['text']}" for i in items]
            return reply(f"`{car['id']}` {car['name']}\n" + "\n".join(lines))
        if sub == "parts":
            want = slug(o.get("job", ""))
            kits = load_kits()
            k = next((j for j in kits if j.get("id") == want), None)
            if not k:
                have = ", ".join(j.get("id", "") for j in kits) or "none yet"
                return reply(f"No kit called `{want}`. Kits: {have}.")
            lines = [f"**{k['name']}**"]
            if k.get("kit"):
                lines.append(f"Whole kit {k['kit'].get('sku', '')} ${k['kit'].get('price', 0):.2f}: {k['kit'].get('url', '')}")
            for p in k.get("parts", []):
                lines.append(f"• {p['name']} ×{p.get('qty', 1)} `{p.get('pn', '')}`" + (f" {p['url']}" if p.get("url") else " (in kit)"))
            for e in k.get("extras", []):
                lines.append(f"+ {e['name']} ×{e.get('qty', 1)} `{e.get('pn', '')}` {e.get('url', '')}")
            return reply("\n".join(lines))
        if sub == "remove":
            cid = remove_car(who, o.get("car", ""))
            bg.add_task(post_feed, f"**{name}** removed `{cid}` and its log.")
            return reply(f"Removed `{cid}` and everything logged on it.")
        if sub == "public":
            if not who.is_admin:
                return reply(f"Only {CFG.admin_name} can change what's public.")
            with _db_lock, db() as con:
                car = get_car(con, o.get("car", ""), who)
                on = 1 if o.get("show") else 0
                con.execute("UPDATE cars SET public=? WHERE id=?", (on, car["id"]))
                audit(con, car["id"], name, "discord", "public", str(on))
            return reply(f"`{car['id']}` is now {'shown on' if on else 'hidden from'} the public page.")
        return reply("Try /garage cars, addcar, odo, log, due, parts, remove.")
    except HTTPException as e:
        return reply(str(e.detail))
