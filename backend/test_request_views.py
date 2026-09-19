"""Tests for the UI read models: my_requests, pending_for, audit trails."""

from backend.conftest import CLEAN_REASON
from backend.request_views import audit_for, my_requests, pending_for
from backend.tools import decide_request, submit_leave_request


def make_request(employee_no="WR-0002") -> str:
    r = submit_leave_request(leave_type="annual", start_date="2026-11-02",
                             end_date="2026-11-03", reason=CLEAN_REASON,
                             caller_employee_no=employee_no)
    assert r["status"] == "created", r
    return r["request_no"]


def numbers(items):
    return {i["request_no"] for i in items}


def test_my_requests_scoped_to_the_owner():
    mine = make_request("WR-0002")
    assert mine in numbers(my_requests("WR-0002"))
    assert mine not in numbers(my_requests("WR-0001"))


def test_pending_for_manager_includes_the_report_request():
    request_no = make_request()
    assert request_no in numbers(pending_for("WR-0003"))


def test_audit_appears_after_a_decision_with_approver_name():
    request_no = make_request()
    decide_request(request_no, "approved", caller_employee_no="WR-0003")

    (item,) = [i for i in my_requests("WR-0002") if i["request_no"] == request_no]
    assert item["status"] == "approved"
    assert len(item["audit"]) == 1
    (row,) = item["audit"]
    assert row["level"] == "manager"
    assert row["decision"] == "approved"
    assert row["approver"] == "Siti Nurhaliza binti Yusof"    # a NAME, not an id
    assert row["decided_at"]


def test_audit_for_unknown_request_is_empty():
    assert audit_for("XX-9999-0001") == []


def test_pending_for_employee_is_empty():
    make_request("WR-0002")
    assert pending_for("WR-0001") == []      # peers have nothing to decide
