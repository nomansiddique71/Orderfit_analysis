"""Demo login: sign-up with an emailed (demo inbox) code, log-in, profile,
change and forgotten password. Codes come from the demo inbox only."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import auth  # noqa: E402
from test_api import client  # noqa: E402

PW = "orders2026"


def _code(mail):
    return re.search(r"\b(\d{6})\b", mail["subject"]).group(1)


def _signup(email="rina@example.com", username="rina"):
    r = client.post("/api/auth/signup", json={"name": "Rina", "username": username,
                                              "email": email, "password": PW})
    assert r.status_code == 200, r.text
    return r.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_signup_needs_the_code_then_logs_in():
    s = _signup()
    assert "no real email" in s["demo_inbox"]["note"].lower()
    bad = client.post("/api/auth/verify", json={"pending_id": s["pending_id"], "code": "000000"})
    assert bad.status_code in (400, 429) or _code(s["demo_inbox"]) == "000000"
    ok = client.post("/api/auth/verify", json={"pending_id": s["pending_id"], "code": _code(s["demo_inbox"])})
    assert ok.status_code == 200
    token = ok.json()["token"]
    me = client.get("/api/auth/me", headers=_auth(token)).json()["user"]
    assert me["email"] == "rina@example.com" and me["verified"] and "pw" not in str(me).lower()
    # log in by email or by username
    assert client.post("/api/auth/login", json={"login": "RINA@example.com", "password": PW}).status_code == 200
    assert client.post("/api/auth/login", json={"login": "rina", "password": PW}).status_code == 200
    assert client.post("/api/auth/login", json={"login": "rina", "password": "wrong-pass1"}).status_code == 401
    # duplicate email / username
    assert client.post("/api/auth/signup", json={"name": "R", "username": "rina2", "email": "rina@example.com",
                                                 "password": PW}).status_code == 409
    assert client.post("/api/auth/signup", json={"name": "R", "username": "Rina", "email": "x@example.com",
                                                 "password": PW}).status_code == 409


def test_input_rules_and_code_attempt_limit():
    for body, msg in [({"password": "short1"}, "8 characters"), ({"email": "nope"}, "valid email"),
                      ({"username": "a b"}, "Username")]:
        r = client.post("/api/auth/signup", json={"name": "A", "username": "abc_1", "email": "a1@example.com",
                                                  "password": PW, **body})
        assert r.status_code == 400 and msg in r.json()["detail"]
    s = _signup("lim@example.com", "lim")
    real = _code(s["demo_inbox"])
    wrong = "111111" if real != "111111" else "222222"
    codes = [client.post("/api/auth/verify", json={"pending_id": s["pending_id"], "code": wrong}).status_code
             for _ in range(auth.CODE_ATTEMPTS + 1)]
    assert codes[-1] == 429
    assert client.post("/api/auth/verify", json={"pending_id": s["pending_id"], "code": real}).status_code == 404


def test_profile_change_and_forgot_password():
    s = _signup("ali@example.com", "ali")
    token = client.post("/api/auth/verify", json={"pending_id": s["pending_id"],
                                                  "code": _code(s["demo_inbox"])}).json()["token"]
    u = client.post("/api/auth/profile", json={"name": "Ali K", "business": "Ali Traders"},
                    headers=_auth(token)).json()["user"]
    assert u["name"] == "Ali K" and u["business"] == "Ali Traders"
    assert client.post("/api/auth/password", json={"old_password": "bad", "new_password": "newpass123"},
                       headers=_auth(token)).status_code == 401
    assert client.post("/api/auth/password", json={"old_password": PW, "new_password": "newpass123"},
                       headers=_auth(token)).status_code == 200
    # forgot password: unknown email looks the same, known email gets a code
    unknown = client.post("/api/auth/forgot", json={"email": "nobody@example.com"}).json()
    assert unknown["demo_inbox"] is None and unknown["pending_id"]
    f = client.post("/api/auth/forgot", json={"email": "ali@example.com"}).json()
    r = client.post("/api/auth/reset", json={"pending_id": f["pending_id"], "code": _code(f["demo_inbox"]),
                                             "new_password": "reset2026x"})
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 401  # old sessions ended
    assert client.post("/api/auth/login", json={"login": "ali", "password": "reset2026x"}).status_code == 200


def test_demo_account_and_logout():
    r = client.post("/api/auth/demo").json()
    assert r["user"]["demo"] and r["user"]["email"].endswith("@solvorder.example")
    assert client.get("/api/auth/me", headers=_auth(r["token"])).status_code == 200
    client.post("/api/auth/logout", headers=_auth(r["token"]))
    assert client.get("/api/auth/me", headers=_auth(r["token"])).status_code == 401
    assert client.get("/api/auth/me").status_code == 401
