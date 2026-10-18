"""Demo accounts for SolvOrder: sign-up with an email code, log-in, profile,
forgot / change password.

This is a DEMONSTRATION login, as agreed for the hackathon:
  * accounts live in server memory (lost on restart; nothing is persisted)
  * the 6-digit code is "emailed" to an on-screen demo inbox -- no real email
    is sent (SolvOrder has no real-email capability anywhere; see T3 in sandbox.py)
  * passwords are still handled properly: PBKDF2-SHA256 with a per-user salt,
    compared in constant time, never logged or returned
It gates the web UI; the analysis API itself stays session-based.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
from dataclasses import dataclass, field

CODE_TTL = 10 * 60  # seconds
CODE_ATTEMPTS = 5
TOKEN_TTL = 12 * 3600
PBKDF2_ROUNDS = 200_000
MAX_USERS = 2000
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,30}$")
# Currencies a business can choose on its profile (ISO codes). Amounts are never
# converted: the owner types and reads every number in this one currency.
CURRENCIES = ("BDT", "INR", "USD", "GBP", "EUR")
ROLES = ("seller", "buyer")  # seller: I sell to a customer; buyer: I buy from a supplier
MAX_APPROVED = 50  # approved plans kept per account (in memory)


class AuthError(ValueError):
    """User-facing auth failure (message is safe to show)."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class User:
    email: str
    username: str
    name: str
    salt: bytes
    pw_hash: bytes
    created: float = field(default_factory=time.time)
    business: str = ""
    demo: bool = False
    # Company profile: who the owner is in a deal and the currency the business runs in.
    company_email: str = ""
    role: str = "seller"
    currency: str = "USD"
    approved_plans: list = field(default_factory=list)  # newest first; see server.notify

    def to_json(self) -> dict:
        return {"email": self.email, "username": self.username, "name": self.name,
                "business": self.business, "verified": True, "demo": self.demo,
                "company_email": self.company_email, "role": self.role, "currency": self.currency,
                "member_since": time.strftime("%d %b %Y", time.localtime(self.created))}


@dataclass
class PendingCode:
    purpose: str  # signup | reset
    email: str
    code_hash: bytes
    expires: float
    attempts: int = 0
    data: dict = field(default_factory=dict)  # signup: name, username, salt, pw_hash


def _hash_pw(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)


def _hash_code(code: str) -> bytes:
    return hashlib.sha256(code.encode()).digest()


def _check_password(pw: str) -> None:
    if len(pw) < 8 or not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        raise AuthError("Use at least 8 characters with letters and a number.")
    if len(pw) > 128:
        raise AuthError("Password is too long.")


class AuthStore:
    """In-memory users, pending codes and login tokens (thread-safe)."""

    def __init__(self) -> None:
        self.users: dict[str, User] = {}  # email (lower) -> user
        self.pending: dict[str, PendingCode] = {}  # pending id -> code
        self.tokens: dict[str, tuple[str, float]] = {}  # token -> (email, expires)
        self.inbox: list[dict] = []  # demo inbox: what would have been emailed
        self._lock = threading.Lock()

    # ------------------------------------------------------------- helpers

    def _mail_code(self, email: str, purpose: str, data: dict | None = None) -> tuple[str, dict]:
        code = f"{secrets.randbelow(1_000_000):06d}"
        pid = secrets.token_urlsafe(12)
        self.pending[pid] = PendingCode(purpose, email, _hash_code(code), time.time() + CODE_TTL,
                                        data=data or {})
        what = "verify your email" if purpose == "signup" else "reset your password"
        msg = {"to": email, "subject": f"SolvOrder code: {code}",
               "body": f"Your SolvOrder code to {what} is {code}. It expires in 10 minutes.\n"
                       f"If you did not ask for this, ignore this message.",
               "time": time.strftime("%H:%M:%S"), "note": "Demo inbox: no real email was sent."}
        self.inbox.append(msg)
        return pid, msg

    def _take_code(self, pid: str, code: str, purpose: str) -> PendingCode:
        p = self.pending.get(pid)
        if p is None or p.purpose != purpose:
            raise AuthError("This code request was not found. Ask for a new code.", 404)
        if time.time() > p.expires:
            self.pending.pop(pid, None)
            raise AuthError("The code has expired. Ask for a new one.")
        p.attempts += 1
        if p.attempts > CODE_ATTEMPTS:
            self.pending.pop(pid, None)
            raise AuthError("Too many wrong codes. Ask for a new one.", 429)
        if not hmac.compare_digest(p.code_hash, _hash_code(code.strip())):
            raise AuthError(f"Wrong code. {CODE_ATTEMPTS - p.attempts} tries left.")
        self.pending.pop(pid, None)
        return p

    def _token(self, email: str) -> str:
        tok = secrets.token_urlsafe(24)
        self.tokens[tok] = (email, time.time() + TOKEN_TTL)
        return tok

    # --------------------------------------------------------------- flows

    def start_signup(self, name: str, username: str, email: str, password: str) -> tuple[str, dict]:
        name, username, email = name.strip(), username.strip(), email.strip().lower()
        if not 1 <= len(name) <= 80:
            raise AuthError("Enter your name.")
        if not USERNAME_RE.match(username):
            raise AuthError("Username: 3-30 letters, numbers, dots, dashes or underscores.")
        if not EMAIL_RE.match(email) or len(email) > 120:
            raise AuthError("Enter a valid email address.")
        _check_password(password)
        with self._lock:
            if email in self.users:
                raise AuthError("An account with this email already exists. Log in instead.", 409)
            if any(u.username.lower() == username.lower() for u in self.users.values()):
                raise AuthError("This username is taken.", 409)
            if len(self.users) >= MAX_USERS:
                raise AuthError("The demo is full right now. Use the demo account.", 503)
            salt = secrets.token_bytes(16)
            return self._mail_code(email, "signup", {"name": name, "username": username,
                                                     "salt": salt, "pw_hash": _hash_pw(password, salt)})

    def resend(self, pid: str) -> tuple[str, dict]:
        with self._lock:
            p = self.pending.pop(pid, None)
            if p is None:
                raise AuthError("This code request was not found. Start again.", 404)
            return self._mail_code(p.email, p.purpose, p.data)

    def verify_signup(self, pid: str, code: str) -> tuple[str, User]:
        with self._lock:
            p = self._take_code(pid, code, "signup")
            if p.email in self.users:
                raise AuthError("An account with this email already exists.", 409)
            d = p.data
            u = User(p.email, d["username"], d["name"], d["salt"], d["pw_hash"])
            self.users[u.email] = u
            return self._token(u.email), u

    def login(self, login: str, password: str) -> tuple[str, User]:
        login = login.strip().lower()
        with self._lock:
            u = self.users.get(login) or next(
                (x for x in self.users.values() if x.username.lower() == login), None)
            # same message and same work whether or not the account exists
            ok = u is not None and hmac.compare_digest(u.pw_hash, _hash_pw(password, u.salt))
            if u is None:
                _hash_pw(password, b"0" * 16)
            if not ok:
                raise AuthError("Email/username or password is wrong.", 401)
            return self._token(u.email), u

    def demo(self) -> tuple[str, User]:
        """A fresh guest account per visitor: no password, clearly marked as demo."""
        with self._lock:
            n = secrets.token_hex(3)
            salt = secrets.token_bytes(16)
            u = User(f"demo-{n}@solvorder.example", f"demo_{n}", "Demo owner", salt,
                     _hash_pw(secrets.token_urlsafe(16), salt), business="Acme Trading Co.", demo=True,
                     company_email="finance@acmetrading.example")
            self.users[u.email] = u
            return self._token(u.email), u

    def user_for(self, token: str | None) -> User:
        with self._lock:
            entry = self.tokens.get(token or "")
            if entry is None or time.time() > entry[1]:
                self.tokens.pop(token or "", None)
                raise AuthError("Please log in again.", 401)
            u = self.users.get(entry[0])
            if u is None:
                raise AuthError("Please log in again.", 401)
            return u

    def logout(self, token: str) -> None:
        with self._lock:
            self.tokens.pop(token, None)

    def update_profile(self, token: str, name: str, business: str, company_email: str | None = None,
                       role: str | None = None, currency: str | None = None) -> User:
        """Name and company profile. None keeps the current value of a company field."""
        u = self.user_for(token)
        if not 1 <= len(name.strip()) <= 80 or len(business) > 80:
            raise AuthError("Enter a name (and a business name up to 80 characters).")
        company_email = (company_email if company_email is not None else u.company_email).strip().lower()
        if company_email and (not EMAIL_RE.match(company_email) or len(company_email) > 120):
            raise AuthError("Enter a valid company email address (or leave it empty).")
        role = role if role is not None else u.role
        if role not in ROLES:
            raise AuthError("Role must be seller or buyer.")
        currency = (currency if currency is not None else u.currency).strip().upper()
        if currency not in CURRENCIES:
            raise AuthError(f"Choose one of: {', '.join(CURRENCIES)}.")
        u.name, u.business = name.strip(), business.strip()
        u.company_email, u.role, u.currency = company_email, role, currency
        return u

    def add_approved(self, token: str, record: dict) -> None:
        u = self.user_for(token)
        with self._lock:
            u.approved_plans.insert(0, record)
            del u.approved_plans[MAX_APPROVED:]

    def change_password(self, token: str, old: str, new: str) -> None:
        u = self.user_for(token)
        if not hmac.compare_digest(u.pw_hash, _hash_pw(old, u.salt)):
            raise AuthError("Your current password is wrong.", 401)
        _check_password(new)
        u.salt = secrets.token_bytes(16)
        u.pw_hash = _hash_pw(new, u.salt)

    def start_reset(self, email: str) -> tuple[str, dict | None]:
        """Always looks the same to the caller, whether or not the email exists."""
        email = email.strip().lower()
        with self._lock:
            if email in self.users:
                return self._mail_code(email, "reset")
            return secrets.token_urlsafe(12), None

    def finish_reset(self, pid: str, code: str, new: str) -> tuple[str, User]:
        _check_password(new)
        with self._lock:
            p = self._take_code(pid, code, "reset")
            u = self.users[p.email]
            u.salt = secrets.token_bytes(16)
            u.pw_hash = _hash_pw(new, u.salt)
            for t, (e, _) in list(self.tokens.items()):  # log out everywhere
                if e == u.email:
                    self.tokens.pop(t, None)
            return self._token(u.email), u
