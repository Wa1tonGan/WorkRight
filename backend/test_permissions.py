"""Tests for access control (permissions + the forbidden status on tools)."""

from datetime import date

from backend.permissions import allowed, can_see
from backend.tools import annual_leave_entitlement, get_employee, search_policy


def test_allowed_truth_table():
    assert allowed("employee", "A", "A", "B") is True          # own data
    assert allowed("hr", "R", "A", "B") is True
    assert allowed("admin", "X", "A", "B") is True
    assert allowed("manager", "M", "A", "M") is True           # direct report
    assert allowed("manager", "M", "A", "OTHER") is False      # not their report
    assert allowed("employee", "P", "A", "M") is False         # curious peer
    assert allowed("employee", "P", "P", None) is True         # self, no manager


def test_can_see_with_seeded_cast():
    assert can_see("WR-0001", "WR-0001") is True     # danial, himself
    assert can_see("WR-0003", "WR-0001") is True     # siti manages danial
    assert can_see("WR-0001", "WR-0003") is False    # danial may NOT see siti
    assert can_see("WR-0007", "WR-0006") is True     # HR sees all
    assert can_see("WR-9999", "WR-0001") is False    # unknown caller
    assert can_see("WR-0001", "WR-9999") is False    # unknown target


def test_forbidden_response_leaks_no_target_data():
    r = annual_leave_entitlement("WR-0003", caller_employee_no="WR-0001",
                                 as_of=date(2026, 9, 15))
    assert r["status"] == "forbidden"
    assert "Siti" not in str(r)          # not even the name escapes
    assert "entitled_days" not in r


def test_manager_can_check_direct_report():
    r = annual_leave_entitlement("WR-0001", caller_employee_no="WR-0003",
                                 as_of=date(2026, 9, 15))
    assert r["status"] == "ok"


def test_hr_can_see_anyone():
    assert get_employee("WR-0006", caller_employee_no="WR-0007")["status"] == "ok"


def test_self_default_still_works():
    assert get_employee("WR-0001")["status"] == "ok"   # no caller → self


def test_search_policy_forbidden_for_peers():
    r = search_policy("annual leave", "WR-0003", caller_employee_no="WR-0001")
    assert r["status"] == "forbidden"
    assert "results" not in r
