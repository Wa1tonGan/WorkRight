"""Shared test fixtures."""

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.database import engine
from backend.models import LeaveRequest

# every test-created row carries this reason so cleanup is surgical
CLEAN_REASON = "pytest-run"


@pytest.fixture(autouse=True)
def _wipe_pytest_rows():
    """Remove test-created leave rows before AND after each test, so the
    suite leaves the real ledger exactly as it found it."""

    def wipe() -> None:
        with Session(engine) as session:
            session.execute(
                delete(LeaveRequest).where(LeaveRequest.reason == CLEAN_REASON)
            )
            session.commit()

    wipe()
    yield
    wipe()
