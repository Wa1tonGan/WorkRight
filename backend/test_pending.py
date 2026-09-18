"""Tests for list_pending_requests — the capability whose absence made
'any pending requests?' return nothing."""

from backend.conftest import CLEAN_REASON
from backend.tools import (
    decide_request,
    list_pending_requests,
    submit_fwa_request,
    submit_leave_request,
)

# Wei Jie (WR-0002) reports to Siti (WR-0003); Ravi (WR-0007) is HR.


def make_pending_leave(employee_no="WR-0002", dates=("2026-11-02", "2026-11-03")):
    r = submit_leave_request(leave_type="annual", start_date=dates[0],
                             end_date=dates[1], reason=CLEAN_REASON,
                             caller_employee_no=employee_no)
    assert r["status"] == "created", r
    return r["request_no"]


def make_pending_sick(employee_no="WR-0002"):
    r = submit_leave_request(leave_type="sick", start_date="2026-11-09",
                             end_date="2026-11-09", reason=CLEAN_REASON,
                             caller_employee_no=employee_no)
    assert r["status"] == "created", r
    return r["request_no"]


def make_pending_fwa(employee_no="WR-0002"):
    r = submit_fwa_request(requested_arrangement="WFH Tue/Thu",
                           proposed_start_date="2027-01-04",
                           change_place=True, employee_reason=CLEAN_REASON,
                           caller_employee_no=employee_no)
    assert r["status"] == "created", r
    return r["request_no"]


def numbers(result):
    return {i["request_no"] for i in result["pending"]}


def test_manager_sees_direct_reports_pending_manager_requests():
    leave = make_pending_leave()          # Wei Jie's, manager stage
    result = list_pending_requests(caller_employee_no="WR-0003")
    assert leave in numbers(result)
    assert all(i["status"] == "pending_manager" for i in result["pending"])


def test_manager_does_not_see_hr_stage_requests():
    sick = make_pending_sick()            # goes straight to pending_hr
    result = list_pending_requests(caller_employee_no="WR-0003")
    assert sick not in numbers(result)


def test_hr_sees_everything_pending():
    leave = make_pending_leave()
    sick = make_pending_sick()
    fwa = make_pending_fwa()
    result = list_pending_requests(caller_employee_no="WR-0007")
    assert {leave, sick, fwa} <= numbers(result)


def test_employee_sees_only_their_own_pending():
    own = make_pending_leave(employee_no="WR-0001")
    other = make_pending_leave(employee_no="WR-0002")
    result = list_pending_requests(caller_employee_no="WR-0001")
    assert own in numbers(result)
    assert other not in numbers(result)


def test_decided_requests_disappear_from_the_list():
    request_no = make_pending_leave()
    assert request_no in numbers(list_pending_requests(caller_employee_no="WR-0003"))
    decide_request(request_no, "approved", caller_employee_no="WR-0003")
    assert request_no not in numbers(list_pending_requests(caller_employee_no="WR-0003"))


def test_no_caller_rejected():
    assert list_pending_requests()["status"] == "rejected"
