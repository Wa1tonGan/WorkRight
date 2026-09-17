"""Tests for login, sessions, and the session-identified /chat contract.

Auth tests manage their own session rows (no shared fixtures beyond pytest),
so they never disturb real logins beyond their own tokens."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend import auth
from backend.database import engine
from backend.models import Employee, Session as LoginSession

WRONG_PW = "definitely-not-it"


@pytest.fixture(autouse=True)
def cleanup_sessions():
    """Delete only the session rows this module creates (tracked by token)."""
    created: list[str] = []
    yield created
    with Session(engine) as s:
        for token in created:
            s.execute(delete(LoginSession).where(
                LoginSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
        s.commit()


def do_login(tracked: list[str], email="weijie.lim@example.my",
             password=auth.DEMO_PASSWORD):
    result = auth.login(email, password)
    if result["status"] == "ok":
        tracked.append(result["token"])
    return result


def test_password_hash_roundtrip():
    h = auth.hash_password("secret123")
    assert h != "secret123"                       # never plaintext
    assert auth.verify_password("secret123", h)
    assert not auth.verify_password("secret124", h)
    assert not auth.verify_password("anything", None)


def test_login_success_returns_identity(cleanup_sessions):
    r = do_login(cleanup_sessions)
    assert r["status"] == "ok"
    assert r["employee_no"] == "WR-0002"
    assert r["name"] == "Lim Wei Jie"


def test_login_wrong_password_and_unknown_email_get_same_answer(cleanup_sessions):
    wrong_pw = do_login(cleanup_sessions, password=WRONG_PW)
    unknown = do_login(cleanup_sessions, email="nobody@example.my")
    assert wrong_pw["status"] == unknown["status"] == "invalid_credentials"


def test_resolve_returns_identity_for_valid_token(cleanup_sessions):
    token = do_login(cleanup_sessions)["token"]
    me = auth.resolve(token)
    assert me is not None and me["employee_no"] == "WR-0002"


def test_resolve_rejects_garbage_and_missing_tokens(cleanup_sessions):
    assert auth.resolve(None) is None
    assert auth.resolve("not-a-real-token") is None


def test_logout_revokes_session(cleanup_sessions):
    token = do_login(cleanup_sessions)["token"]
    assert auth.resolve(token) is not None
    auth.logout(token)
    assert auth.resolve(token) is None            # revoked, not just cookie-cleared
    auth.logout(token)                            # idempotent, no error


def test_expired_session_is_rejected(cleanup_sessions):
    token = do_login(cleanup_sessions)["token"]
    with Session(engine) as s:                    # age it beyond expiry
        s.execute(LoginSession.__table__.update()
                  .where(LoginSession.token_hash
                         == hashlib.sha256(token.encode()).hexdigest())
                  .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
        s.commit()
    assert auth.resolve(token) is None


def test_database_stores_only_the_token_hash(cleanup_sessions):
    token = do_login(cleanup_sessions)["token"]
    with Session(engine) as s:
        raw = s.scalar(select(LoginSession)
                       .where(LoginSession.token_hash == token))
        hashed = s.scalar(select(LoginSession).where(
            LoginSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    assert raw is None                            # raw token never stored
    assert hashed is not None                     # digest is
