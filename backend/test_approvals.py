"""Tests for Phase 4 approvals: who may decide, what gets recorded, and how
balances move after a real decision. Uses fresh in-year dates and wipes its
own rows (conftest), so the real ledger is never disturbed."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.conftest import CLEAN_REASON
from backend.database import engine
from backend.models import Approval, LeaveRequest
from backend.tools import (
    annual_leave_entitlement,
    decide_leave_request,
    submit_leave_request,
)

AS_OF = date(2026, 9, 15)

# Wei Jie (WR-0002) reports to Siti (WR-0003); Ravi (WR-0007) is HR.
# Nov dates: in-year for AS_OF, never used by the real demo row (Dec 24-25).


def pending_annual(days_span=("2026-11-02", "2026-11-06")) -> str:
    r = submit_leave_request(leave_type="annual", start_date=days_span[0],
                             end_date=days_span[1], reason=CLEAN_REASON,
                             caller_employee_no="WR-0002")
    assert r["status"] == "created", r
    return r["request_no"]


def pending_sick() -> str:
    r = submit_leave_request(leave_type="sick", start_date="2026-11-09",
                             end_date="2026-11-09", reason=CLEAN_REASON,
                             caller_employee_no="WR-0002")
    assert r["status"] == "created", r
    return r["request_no"]


def balance() -> dict:
    return annual_leave_entitlement("WR-0002", as_of=AS_OF)


# ── the happy paths ───────────────────────────────────────────────────────────

def test_manager_approves_and_audit_row_is_written():
    request_no = pending_annual()
    base = balance()
    r = decide_leave_request(request_no, "approved", caller_employee_no="WR-0003")
    assert r["status"] == "decided"
    assert r["approval_level"] == "manager"
    with Session(engine) as s:
        req = s.scalar(select(LeaveRequest).where(LeaveRequest.request_no == request_no))
        assert req.status == "approved"
        assert req.decided_at is not None
        audit = s.scalar(select(Approval).where(Approval.leave_request_id == req.id))
        assert audit.decision == "approved"
        assert audit.approval_level == "manager"
        assert audit.requested_at is not None      # when approval was requested
    after = balance()
    assert after["approved_days"] == base["approved_days"] + 5.0
    assert after["pending_days"] == base["pending_days"] - 5.0   # moved out of pending
    assert after["remaining_days"] == base["remaining_days"] - 5.0


def test_manager_rejects_with_reason():
    request_no = pending_annual()
    base = balance()
    r = decide_leave_request(request_no, "rejected",
                             reason="team coverage that week", caller_employee_no="WR-0003")
    assert r["status"] == "decided"
    after = balance()
    assert after["approved_days"] == base["approved_days"]
    assert after["pending_days"] == base["pending_days"] - 5.0   # released
    assert after["available_days"] == base["available_days"] + 5.0  # days released


def test_rejection_requires_a_reason():
    request_no = pending_annual()
    r = decide_leave_request(request_no, "rejected", caller_employee_no="WR-0003")
    assert r["status"] == "rejected"
    assert "reason" in r["reason"].lower()


def test_hr_can_decide_manager_level():
    request_no = pending_annual()
    r = decide_leave_request(request_no, "approved", caller_employee_no="WR-0007")
    assert r["status"] == "decided"


def test_hr_decides_pending_hr_sick_request():
    request_no = pending_sick()
    r = decide_leave_request(request_no, "approved", caller_employee_no="WR-0007")
    assert r["status"] == "decided"
    assert r["approval_level"] == "hr"


# ── the refusals (this is why the phase exists) ──────────────────────────────

def test_peer_cannot_decide():
    request_no = pending_annual()
    r = decide_leave_request(request_no, "approved", caller_employee_no="WR-0001")
    assert r["status"] == "forbidden"
    with Session(engine) as s:                  # and nothing changed
        req = s.scalar(select(LeaveRequest).where(LeaveRequest.request_no == request_no))
        assert req.status == "pending_manager"


def test_self_decision_forbidden_even_for_manager():
    # Siti (manager, no manager of her own) asks for leave herself
    created = submit_leave_request(leave_type="annual", start_date="2026-11-16",
                                   end_date="2026-11-16", reason=CLEAN_REASON,
                                   caller_employee_no="WR-0003")
    request_no = created["request_no"]
    r = decide_leave_request(request_no, "approved", caller_employee_no="WR-0003")
    assert r["status"] == "forbidden"


def test_manager_cannot_decide_hr_level():
    request_no = pending_sick()
    r = decide_leave_request(request_no, "approved", caller_employee_no="WR-0003")
    assert r["status"] == "forbidden"


def test_decide_twice_rejected():
    request_no = pending_annual()
    assert decide_leave_request(request_no, "approved",
                                caller_employee_no="WR-0003")["status"] == "decided"
    second = decide_leave_request(request_no, "rejected", reason="changed mind",
                                  caller_employee_no="WR-0003")
    assert second["status"] == "rejected"
    assert "pending" in second["reason"]


def test_unknown_request_not_found():
    assert decide_leave_request("LV-9999-0001", "approved",
                                caller_employee_no="WR-0003")["status"] == "not_found"


def test_bad_decision_value_rejected():
    request_no = pending_annual()
    r = decide_leave_request(request_no, "maybe", caller_employee_no="WR-0003")
    assert r["status"] == "rejected"


def test_no_caller_rejected():
    request_no = pending_annual()
    assert decide_leave_request(request_no, "approved")["status"] == "rejected"
