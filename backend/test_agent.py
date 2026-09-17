"""Offline tests for the loop's doorman logic — no LLM involved."""

from datetime import date

from backend.agent import MENU, TOOL_SPECS, _execute, _clean_answer


def test_menu_advertises_only_safe_args():
    # the whole security model depends on caller NEVER being on the menu
    for spec in TOOL_SPECS:
        props = spec["function"]["parameters"]["properties"]
        assert "caller_employee_no" not in props


def test_unknown_tool_rejected_with_menu_feedback():
    r = _execute("get_leave_balance", {"employee_no": "WR-0001"}, "WR-0001")
    assert r["status"] == "rejected"
    assert "annual_leave_entitlement" in r["reason"]  # shows the real menu


def test_missing_required_arg_rejected():
    r = _execute("get_employee", {}, "WR-0001")
    assert r["status"] == "rejected"
    assert "employee_no" in r["reason"]


def test_model_cannot_spoof_the_caller():
    """Even if the model sneakily passes caller_employee_no (not on the menu,
    but models improvise), the session-injected value wins."""
    r = _execute("get_employee",
                 {"employee_no": "WR-0003", "caller_employee_no": "WR-0007"},
                 "WR-0001")                          # real caller: Danial
    assert r["status"] == "forbidden"    # not HR-access via the spoofed arg


def test_self_call_still_works():
    r = _execute("annual_leave_entitlement", {"employee_no": "WR-0001"},
                 "WR-0001")
    assert r["status"] == "ok"


def test_clean_answer_unwraps_json_and_passes_text():
    assert _clean_answer('{"answer": "hello"}') == "hello"
    assert _clean_answer("plain words") == "plain words"
    assert _clean_answer("{not json") == "{not json"


def test_submit_routes_through_execute_with_injected_caller():
    r = _execute("submit_leave_request",
                 {"leave_type": "annual", "start_date": "2027-03-01",
                  "end_date": "2027-03-01", "reason": "pytest-run"},
                 "WR-0002")
    assert r["status"] == "created"
    assert r["route"] == "pending_manager"


def test_submit_spoof_cannot_borrow_hr_identity():
    """Model passes a fake caller for Jelin to bypass the Sabah escalation —
    the injected session caller (WR-0006) must still win → escalate."""
    r = _execute("submit_leave_request",
                 {"leave_type": "annual", "start_date": "2026-12-24",
                  "end_date": "2026-12-25", "reason": "pytest-run",
                  "caller_employee_no": "WR-0007"},
                 "WR-0006")
    assert r["status"] == "escalate"
