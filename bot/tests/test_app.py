import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from nacl.signing import SigningKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ADMIN, JASON, STRANGER = "111", "222", "333"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    key = SigningKey.generate()
    monkeypatch.setenv("GARAGE_DB", str(tmp_path / "g.db"))
    monkeypatch.setenv("DISCORD_PUBLIC_KEY", key.verify_key.encode().hex())
    monkeypatch.setenv("DISCORD_USERS", f"{ADMIN}:Branden,{JASON}:Jason")
    monkeypatch.setenv("GARAGE_ADMIN_ID", ADMIN)
    monkeypatch.setenv("GARAGE_SITE_TOKEN", "tok")
    monkeypatch.setenv("GARAGE_KITS_PATH", str(Path(__file__).resolve().parents[2] / "data" / "kits.json"))
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "")
    monkeypatch.setenv("GARAGE_ALLOWED_ORIGIN", "http://testserver")
    monkeypatch.setenv("DISCORD_CLIENT_ID", "app123")
    monkeypatch.setenv("DISCORD_CLIENT_SECRET", "shh")
    import app as mod
    mod.LIMITS.reset()
    mod._kits.update(data=None, at=0)
    yield mod, key


def signed(client, key, payload):
    body = json.dumps(payload).encode()
    ts = str(int(time.time()))
    sig = key.sign(ts.encode() + body).signature.hex()
    return client.post("/discord/interactions", content=body,
                       headers={"x-signature-ed25519": sig, "x-signature-timestamp": ts, "content-type": "application/json"})


def cmd(client, key, uid, sub, **opts):
    payload = {"type": 2, "member": {"user": {"id": uid}},
               "data": {"name": "garage", "options": [{"type": 1, "name": sub,
                        "options": [{"name": k, "value": v} for k, v in opts.items()]}]}}
    r = signed(client, key, payload)
    assert r.status_code == 200, r.text
    return r.json()["data"]["content"]


def test_signature_required(env):
    mod, key = env
    c = TestClient(mod.app)
    r = c.post("/discord/interactions", content=b"{}", headers={"x-signature-ed25519": "00", "x-signature-timestamp": "1"})
    assert r.status_code == 401
    assert signed(c, key, {"type": 1}).json() == {"type": 1}


def test_stranger_is_refused(env):
    mod, key = env
    c = TestClient(mod.app)
    assert "not on the garage list" in cmd(c, key, STRANGER, "cars")


def test_admin_car_is_active_and_friend_car_pending(env):
    mod, key = env
    c = TestClient(mod.app)
    out = cmd(c, key, ADMIN, "addcar", name="BMW E36 M3", chassis="e36", year=1997, miles=193500)
    assert "Added `e36`" in out and "pending" not in out
    out = cmd(c, key, JASON, "addcar", name="2008 Civic Si", chassis="civic", miles=112000)
    assert "pending" in out
    assert "civic" in cmd(c, key, JASON, "cars")
    assert "pending" in cmd(c, key, ADMIN, "cars")
    assert "now active" in cmd(c, key, ADMIN, "approve", car="civic")
    assert "Only" in cmd(c, key, JASON, "approve", car="civic")


def test_friend_cannot_see_or_touch_other_cars(env):
    mod, key = env
    c = TestClient(mod.app)
    cmd(c, key, ADMIN, "addcar", name="BMW E36 M3", chassis="e36", miles=193500)
    assert "No car called e36" in cmd(c, key, JASON, "odo", car="e36", miles=1)
    assert "No car called e36" in cmd(c, key, JASON, "due", car="e36")
    assert "No car called e36" in cmd(c, key, JASON, "remove", car="e36")
    assert "e36" not in cmd(c, key, JASON, "cars")


def test_log_and_due(env):
    mod, key = env
    c = TestClient(mod.app)
    cmd(c, key, ADMIN, "addcar", name="BMW E36 M3", chassis="e36", miles=193500)
    out = cmd(c, key, ADMIN, "log", car="e36", job="Oil change 5W-40", miles=193500, date="2025-07-01")
    assert "Logged Oil change 5W-40" in out and "engine" in out
    due = cmd(c, key, ADMIN, "due", car="e36")
    assert "Oil change" in due and ("Overdue" in due or "Due soon" in due or "OK" in due)
    assert "Brake fluid" in due and "No record" in due
    # time rule: 12 months from 2025-07 is overdue by now
    with mod.db() as con:
        items = {d["job"]: d for d in mod.due_list(con, "e36", today=date(2026, 11, 5))}
    assert items["Oil change"]["status"] == "overdue"
    assert "mi left" in items["Oil change"]["text"]
    assert items["Brake fluid"]["status"] == "unknown"


def test_odometer_lower_is_kept_but_flagged(env):
    mod, key = env
    c = TestClient(mod.app)
    cmd(c, key, ADMIN, "addcar", name="E90", chassis="e90", miles=163500)
    out = cmd(c, key, ADMIN, "odo", car="e90", miles=160000)
    assert "Lower than the last reading" in out


def test_parts_kit(env):
    mod, key = env
    c = TestClient(mod.app)
    out = cmd(c, key, JASON, "parts", job="valve-cover")
    assert "11120034108KT" in out and "fcpeuro.com" in out
    assert "No kit called" in cmd(c, key, JASON, "parts", job="nope")


def test_public_export_hides_everything_not_public(env):
    mod, key = env
    c = TestClient(mod.app)
    cmd(c, key, ADMIN, "addcar", name="BMW E36 M3", chassis="e36", miles=193500)
    cmd(c, key, JASON, "addcar", name="2008 Civic Si", chassis="civic", miles=112000)
    cmd(c, key, ADMIN, "approve", car="civic")
    assert c.get("/api/public").json()["cars"] == []
    cmd(c, key, ADMIN, "public", car="e36", show=True)
    pub = c.get("/api/public").json()["cars"]
    assert [x["id"] for x in pub] == ["e36"]
    assert "owner" not in pub[0]
    assert "Only" in cmd(c, key, JASON, "public", car="civic", show=True)


def signin(c, mod, uid, name):
    c.cookies.set(mod.SESSION_COOKIE, mod._sign({"uid": uid, "name": name}, 3600))


def act(c, **o):
    return c.post("/api/act", json=o, headers={"x-garage-web": "1", "origin": "http://testserver"})


def test_site_needs_sign_in_and_scopes_by_user(env):
    mod, key = env
    c = TestClient(mod.app)
    cmd(c, key, ADMIN, "addcar", name="BMW E36 M3", chassis="e36")
    cmd(c, key, JASON, "addcar", name="Civic", chassis="civic")
    assert c.get("/api/me").json() == {"signed_in": False, "login": True}
    assert act(c, action="log", car="e36", job="x").status_code == 401
    signin(c, mod, JASON, "jason")
    mine = c.get("/api/me").json()
    assert mine["known"] and [x["id"] for x in mine["cars"]] == ["civic"] and mine["admin"] is False
    assert act(c, action="log", car="e36", job="Oil change").status_code == 404
    assert act(c, action="approve", car="civic").status_code == 403
    signin(c, mod, ADMIN, "whatever")
    all_ = c.get("/api/me").json()
    assert sorted(x["id"] for x in all_["cars"]) == ["civic", "e36"] and all_["admin"] is True and all_["user"]["name"] == "Branden"
    assert act(c, action="approve", car="civic").json()["car"]["status"] == "active"
    assert act(c, action="log", car="e36", job="Oil change 5W-40", miles=193600).json()["system"] == "engine"
    assert act(c, action="public", car="e36", show=True).json()["public"] is True
    assert c.get("/api/public").json()["cars"][0]["id"] == "e36"


def test_site_writes_need_our_header_and_origin(env):
    mod, key = env
    c = TestClient(mod.app)
    signin(c, mod, ADMIN, "b")
    assert c.post("/api/act", json={"action": "addcar", "name": "x"}).status_code == 403
    assert c.post("/api/act", json={"action": "addcar", "name": "x"}, headers={"x-garage-web": "1", "origin": "https://evil.example"}).status_code == 403
    bad = mod._sign({"uid": ADMIN, "name": "b"}, 3600)[:-2] + "zz"
    c.cookies.set(mod.SESSION_COOKIE, bad)
    assert c.get("/api/me").json()["signed_in"] is False


def test_stranger_may_add_one_car_then_is_known(env):
    mod, key = env
    c = TestClient(mod.app)
    signin(c, mod, STRANGER, "newguy")
    me = c.get("/api/me").json()
    assert me["signed_in"] and me["known"] is False and me["user"]["name"] == "newguy"
    assert act(c, action="log", car="e36", job="x").status_code == 403
    r = act(c, action="addcar", name="2008 Civic Si", chassis="civic", miles=112000)
    assert r.status_code == 200 and r.json()["car"]["status"] == "pending"
    assert act(c, action="addcar", name="Another").status_code == 403
    me = c.get("/api/me").json()
    assert me["known"] and me["cars"][0]["id"] == "civic" and me["user"]["name"] == "newguy"
    # now the slash commands work for them too, on their own car only
    assert "civic" in cmd(c, key, STRANGER, "cars")
    assert "No car called e36" in cmd(c, key, STRANGER, "due", car="e36")
    assert "not on the garage list" in cmd(c, key, "444", "cars")


def test_oauth_login_redirect_and_bad_callback(env):
    mod, key = env
    c = TestClient(mod.app, follow_redirects=False)
    r = c.get("/auth/login")
    assert r.status_code == 302 and "discord.com/oauth2/authorize" in r.headers["location"] and "scope=identify" in r.headers["location"]
    assert mod.STATE_COOKIE in r.cookies
    r = c.get("/auth/callback?code=abc&state=wrong")
    assert r.status_code == 302 and r.headers["location"].endswith("signin=failed")
    r = c.post("/auth/logout", headers={"x-garage-web": "1"})
    assert r.status_code == 200


def test_remove_deletes_log(env):
    mod, key = env
    c = TestClient(mod.app)
    cmd(c, key, JASON, "addcar", name="Civic", chassis="civic", miles=1000)
    cmd(c, key, JASON, "log", car="civic", job="Oil change", miles=1000)
    assert "Removed `civic`" in cmd(c, key, JASON, "remove", car="civic")
    with mod.db() as con:
        assert con.execute("SELECT count(*) FROM visits").fetchone()[0] == 0
        assert con.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
