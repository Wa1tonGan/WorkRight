"""Login, sessions, and identity resolution.

Who you are is decided by a SESSION ROW IN THE DATABASE — never by a value
in a request body. That single rule is what turns /chat from "trust the
caller" into an actual system:

    request ──cookie──▶ token ──sha256──▶ sessions row ──▶ employee
                              (raw token never stored server-side)

Passwords are bcrypt hashes (salt rounds built in). The raw session token
exists only in the user's httpOnly cookie; the DB holds its SHA-256 digest.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .database import engine
from .models import Employee, Session

SESSION_LIFETIME_DAYS = 7
DEMO_PASSWORD = "workright123"  # fictional employees; printed in the docs


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def login(email: str, password: str) -> dict:
    """Verify credentials and create a session.

    status: ok | invalid_credentials
    Deliberately ONE failure message for both wrong-email and wrong-password:
    distinguishing them tells attackers which emails exist.
    """
    with OrmSession(engine) as session:
        emp = session.scalar(
            select(Employee).where(Employee.email == (email or "").strip().lower())
        )
        if emp is None or not verify_password(password or "", emp.password_hash):
            return {"status": "invalid_credentials"}

        token = secrets.token_urlsafe(32)
        session.add(Session(
            token_hash=_token_hash(token),
            employee_id=emp.id,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=SESSION_LIFETIME_DAYS),
        ))
        session.commit()
        return {
            "status": "ok",
            "token": token,
            "employee_no": emp.employee_no,
            "name": emp.full_name,
            "role": emp.role.value,
            "email": emp.email,
        }


def resolve(token: str | None) -> dict | None:
    """Token → identity, or None if missing / unknown / expired / revoked."""
    if not token:
        return None
    with OrmSession(engine) as session:
        row = session.scalar(
            select(Session).where(Session.token_hash == _token_hash(token))
        )
        if row is None or row.revoked_at is not None:
            return None
        if row.expires_at < datetime.now(timezone.utc):
            return None
        emp = session.get(Employee, row.employee_id)
        if emp is None:
            return None
        return {
            "employee_no": emp.employee_no,
            "name": emp.full_name,
            "role": emp.role.value,
            "email": emp.email,
        }


def logout(token: str | None) -> None:
    """Revoke the session (idempotent; unknown tokens are ignored)."""
    if not token:
        return
    with OrmSession(engine) as session:
        row = session.scalar(
            select(Session).where(Session.token_hash == _token_hash(token))
        )
        if row is not None and row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            session.commit()
