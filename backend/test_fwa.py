"""Tests for phase 4 flexible-work requests: submission validation, the
two-stage manager→HR decision flow, and the refusal matrix.

Created rows carry employee_reason = CLEAN_REASON so conftest wipes them
(and cascades their approvals) after every test."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.conftest import CLEAN_REASON
from backend.database import engine
from backend.models import Approval, FlexibleWorkRequest
from backend.tools import decide_request, submit_fwa_request, submit_leave_request


def wfh(**kwargs):
    """A valid single-dimension request for Wei Jie (WR-0002, reports to Siti)."""
    kwargs.setdefault("requested_arrangement", "Work from home Mon/Wed/Fri, 9am-6pm")
    kwargs.setdefault("proposed_start_date", "2027-01-04")
    kwargs.setdefault("change_place", True)
    kwargs.setdefault("employee_reason", CLEAN_REASON)
    kwargs.setdefault("caller_employee_no", "WR-0002")
    return submit_fwa_request(**kwargs)


def fwa_row(request_no: str) -> FlexibleWorkRequest:
    with Session(engine) as s:
        return s.scalar(select(FlexibleWorkRequest)
                        .where(FlexibleWorkRequest.request_no == request_no))


def audit_rows(fwa_id: str) -> list[Approval]:
    with Session(engine) as s:
        return list(s.scalars(
            select(Approval).where(Approval.fwa_request_id == fwa_id)
            .order_by(Approval.created_at)
        ))


# ── submission ────────────────────────────────────────────────────────────────

def test_submission_sets_both_clocks_and_provenance():
    r = wfh()
    assert r["status"] == "created"
    assert r["route"].startswith("pending_manager")
    row = fwa_row(r["request_no"])
    assert row.status == "pending_manager"
    assert row.decision_due_at - row.submitted_at == timedelta(days=60)   # statutory
    assert row.target_decision_at - row.submitted_at == timedelta(days=30)  # company
    assert row.decision_basis_policy_id is not None    # provenance recorded

def test_multi_dimension_request_allowed():
    r = wfh(change_hours=True, change_place=True, requested_arrangement="10am start, at home")
    assert r["status"] == "created"
    assert set(r["dimensions"]) == {"hours", "place"}


def test_zero_dimensions_rejected():
    r = wfh(change_place=False)
    assert r["status"] == "rejected"
    assert "at least one" in r["reason"]


def test_missing_arrangement_rejected():
    r = wfh(requested_arrangement="   ")
    assert r["status"] == "rejected"


def test_missing_start_date_rejected():
    r = wfh(proposed_start_date=None)
    assert r["status"] == "rejected"
    assert "start_date" in r["reason"]


def test_end_before_start_rejected():
    r = wfh(proposed_end_date="2026-12-01")     # before the 2027 start
    assert r["status"] == "rejected"


def test_out_of_scope_employees_escalate_and_create_nothing():
    for employee in ("WR-0004", "WR-0006"):     # part-time, Sabah
        r = wfh(caller_employee_no=employee)
        assert r["status"] == "escalate", r
    with Session(engine) as s:
        n = s.scalar(select(FlexibleWorkRequest)
                     .where(FlexibleWorkRequest.employee_reason == CLEAN_REASON))
        assert n is None        # nothing was created


# ── the two-stage decision flow ──────────────────────────────────────────────

def test_manager_approval_advances_to_hr_not_final():
    request_no = wfh()["request_no"]
    r = decide_request(request_no, "approved", caller_employee_no="WR-0003")
    assert r["status"] == "advanced"
    assert r["new_status"] == "pending_hr"
    row = fwa_row(request_no)
    assert row.decided_at is None               # NOT a final decision
    (audit,) = audit_rows(row.id)
    assert (audit.approval_level, audit.decision) == ("manager", "approved")


def test_hr_stage_finalizes_with_second_audit_row():
    request_no = wfh()["request_no"]
    decide_request(request_no, "approved", caller_employee_no="WR-0003")
    r = decide_request(request_no, "approved", caller_employee_no="WR-0007")
    assert r["status"] == "decided"
    assert r["new_status"] == "approved"
    row = fwa_row(request_no)
    assert row.decided_at is not None
    levels = [(a.approval_level, a.decision) for a in audit_rows(row.id)]
    assert levels == [("manager", "approved"), ("hr", "approved")]


def test_manager_rejects_ends_it_with_reason():
    request_no = wfh()["request_no"]
    r = decide_request(request_no, "rejected",
                       reason="coverage impossible on those days",
                       caller_employee_no="WR-0003")
    assert r["status"] == "decided"
    row = fwa_row(request_no)
    assert row.status == "rejected"
    assert row.decision_reason == "coverage impossible on those days"


def test_double_decide_rejected():
    request_no = wfh()["request_no"]
    decide_request(request_no, "approved", caller_employee_no="WR-0003")
    decide_request(request_no, "approved", caller_employee_no="WR-0007")
    third = decide_request(request_no, "rejected", reason="nope",
                           caller_employee_no="WR-0007")
    assert third["status"] == "rejected"


# ── refusals ──────────────────────────────────────────────────────────────────

def test_peer_cannot_decide_fwa():
    request_no = wfh()["request_no"]
    r = decide_request(request_no, "approved", caller_employee_no="WR-0001")
    assert r["status"] == "forbidden"
    assert fwa_row(request_no).status == "pending_manager"    # unchanged


def test_manager_cannot_decide_hr_stage():
    request_no = wfh()["request_no"]
    decide_request(request_no, "approved", caller_employee_no="WR-0003")
    r = decide_request(request_no, "approved", caller_employee_no="WR-0003")
    assert r["status"] == "forbidden"


# ── routing ───────────────────────────────────────────────────────────────────

def test_decide_request_routes_leave_requests_to_leave_logic():
    created = submit_leave_request(leave_type="annual", start_date="2026-11-02",
                                   end_date="2026-11-03", reason=CLEAN_REASON,
                                   caller_employee_no="WR-0002")
    r = decide_request(created["request_no"], "approved",
                       caller_employee_no="WR-0003")
    assert r["status"] == "decided"
    assert r["approval_level"] == "manager"


def test_unknown_request_prefix_rejected():
    r = decide_request("XX-2026-0001", "approved", caller_employee_no="WR-0003")
    assert r["status"] == "rejected"
