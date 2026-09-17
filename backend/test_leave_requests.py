"""Tests for the leave ledger: working-day math, balance wiring, and the
INSERT-only submit tool.

LESSON (2026-09-17): the first version of these tests assumed an EMPTY
ledger — the moment the live agent created a real request (LV-2026-0001,
Wei Jie, Christmas), six of them broke. They now assert INVARIANTS and
DELTAS instead of absolute numbers, so real data in the dev database can
never make them lie.
"""

from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.conftest import CLEAN_REASON
from backend.database import engine
from backend.models import LeaveRequest
from backend.tools import (
    annual_leave_entitlement,
    submit_leave_request,
    working_days_between,
)

AS_OF = date(2026, 9, 15)
# dates far from any plausible demo activity, so "first create" can't collide
# with real rows the agent created; each test wipes its own rows afterwards
FRESH = ("2027-01-05", "2027-01-06")          # Tue–Wed = 2 working days


def sub(**kwargs):
    kwargs.setdefault("reason", CLEAN_REASON)
    return submit_leave_request(**kwargs)


def balance(employee_no: str = "WR-0002") -> dict:
    return annual_leave_entitlement(employee_no, as_of=AS_OF)


# ── the calculator ────────────────────────────────────────────────────────────

def test_working_days_counter_weekends_excluded():
    assert working_days_between(date(2026, 12, 24), date(2026, 12, 25)) == 2   # Thu–Fri
    assert working_days_between(date(2026, 12, 26), date(2026, 12, 27)) == 0   # Sat–Sun
    assert working_days_between(date(2026, 12, 25), date(2026, 12, 28)) == 2   # Fri–Mon


# ── submit tool: happy paths ──────────────────────────────────────────────────

def test_submit_creates_pending_row_with_computed_days():
    r = sub(leave_type="annual", start_date=FRESH[0],
            end_date=FRESH[1], caller_employee_no="WR-0002")
    assert r["status"] == "created"
    assert r["days"] == 2.0
    assert r["route"] == "pending_manager"
    with Session(engine) as s:
        row = s.scalar(select(LeaveRequest)
                       .where(LeaveRequest.request_no == r["request_no"]))
        assert row.status == "pending_manager"      # never born approved
        assert row.leave_type == "annual"


def test_half_day_single_day_creates_half():
    r = sub(leave_type="annual", start_date="2026-12-24",
            end_date="2026-12-24", day_portion="am",
            caller_employee_no="WR-0002")
    assert r["status"] == "created" and r["days"] == 0.5


def test_sick_leave_routes_to_hr():
    r = sub(leave_type="sick", start_date="2026-12-28",
            end_date="2026-12-28", caller_employee_no="WR-0002")
    assert r["status"] == "created" and r["route"] == "pending_hr"


# ── submit tool: refusals ─────────────────────────────────────────────────────

def test_weekend_only_range_rejected():
    r = sub(leave_type="annual", start_date="2026-12-26",
            end_date="2026-12-27", caller_employee_no="WR-0002")
    assert r["status"] == "rejected" and "no working days" in r["reason"]


def test_half_day_multi_day_rejected():
    r = sub(leave_type="annual", start_date="2026-12-24",
            end_date="2026-12-25", day_portion="am",
            caller_employee_no="WR-0002")
    assert r["status"] == "rejected"


def test_unknown_leave_type_rejected():
    r = sub(leave_type="marriage", start_date="2026-12-24",
            end_date="2026-12-24", caller_employee_no="WR-0002")
    assert r["status"] == "rejected"


def test_no_caller_rejected():
    r = submit_leave_request(leave_type="annual", start_date="2026-12-24",
                             end_date="2026-12-24")
    assert r["status"] == "rejected"


def test_insufficient_balance_rejected_with_numbers():
    # Feb 2027 has 20 weekdays — beyond anyone's balance
    r = sub(leave_type="annual", start_date="2027-02-01",
            end_date="2027-02-26", caller_employee_no="WR-0002")
    assert r["status"] == "rejected"
    assert "insufficient balance" in r["reason"]


def test_sabah_employee_escalates_and_creates_nothing():
    r = sub(leave_type="annual", start_date="2026-12-24",
            end_date="2026-12-25", caller_employee_no="WR-0006")
    assert r["status"] == "escalate"
    with Session(engine) as s:
        n = s.scalar(select(func.count()).select_from(LeaveRequest)
                     .where(LeaveRequest.reason == CLEAN_REASON))
        assert n == 0                       # the refusal left no residue


def test_duplicate_active_request_blocked_by_database():
    first = sub(leave_type="annual", start_date=FRESH[0],
                end_date=FRESH[1], caller_employee_no="WR-0002")
    second = sub(leave_type="annual", start_date=FRESH[0],
                 end_date=FRESH[1], caller_employee_no="WR-0002")
    assert first["status"] == "created"
    assert second["status"] == "rejected"
    assert "already exists" in second["reason"]


# ── balance wiring: deltas, never absolutes (real rows may exist) ────────────

def test_available_formula_invariant_always_holds():
    b = balance()
    assert b["available_days"] == (
        b["entitled_days"] - b["approved_days"] - b["pending_days"]
    )


def test_pending_holds_days_but_not_remaining():
    base = balance()
    # must be IN YEAR of AS_OF: usage is attributed by calendar year of start
    sub(leave_type="annual", start_date="2026-11-02",
        end_date="2026-11-06", caller_employee_no="WR-0002")   # Mon–Fri = 5
    after = balance()
    assert after["pending_days"] == base["pending_days"] + 5.0
    assert after["remaining_days"] == base["remaining_days"]    # nothing decided
    assert after["available_days"] == base["available_days"] - 5.0  # yet held


def test_approved_days_reduce_remaining():
    base = balance()
    created = sub(leave_type="annual", start_date="2026-11-09",
                  end_date="2026-11-13", caller_employee_no="WR-0002")  # 5 days
    # simulate Siti's human decision (the agent has no tool that can do this)
    with Session(engine) as s:
        s.execute(update(LeaveRequest)
                  .where(LeaveRequest.request_no == created["request_no"])
                  .values(status="approved"))
        s.commit()
    after = balance()
    assert after["approved_days"] == base["approved_days"] + 5.0
    assert after["remaining_days"] == base["remaining_days"] - 5.0
    assert after["available_days"] == base["available_days"] - 5.0


def test_rejected_requests_do_not_count_anywhere():
    base = balance()
    created = sub(leave_type="annual", start_date="2026-11-16",
                  end_date="2026-11-20", caller_employee_no="WR-0002")
    with Session(engine) as s:
        s.execute(update(LeaveRequest)
                  .where(LeaveRequest.request_no == created["request_no"])
                  .values(status="rejected"))
        s.commit()
    after = balance()
    assert after["approved_days"] == base["approved_days"]
    assert after["pending_days"] == base["pending_days"]
    assert after["available_days"] == base["available_days"]
