"""Unit tests for the agent tools.

Pure calculators need nothing; the DB-backed ones need Postgres running with
the seeded employees (backend/seed.py). Deterministic: fixed as_of dates.

Run:  uv run pytest backend/test_tools.py -q
"""

from datetime import date

import pytest

from backend.tools import (
    annual_leave_entitlement,
    completed_years,
    get_employee,
    statutory_annual_days,
)


def test_completed_years_anniversary_boundary():
    # joined 2016-09-15: the day BEFORE is still year 9, the 15th flips to 10
    assert completed_years(date(2016, 9, 15), date(2026, 9, 14)) == 9
    assert completed_years(date(2016, 9, 15), date(2026, 9, 15)) == 10
    assert completed_years(date(2016, 9, 15), date(2025, 9, 14)) == 8


def test_statutory_tiers_s60E():
    # 8 / 8 / 12 / 16 with boundaries at 5 and 10 completed years
    assert [statutory_annual_days(y) for y in (0, 1, 4)] == [8, 8, 8]
    assert [statutory_annual_days(y) for y in (5, 9)] == [12, 12]
    assert [statutory_annual_days(y) for y in (10, 30)] == [16, 16]


def test_get_employee_found_shape():
    r = get_employee("WR-0001")          # no caller = asking about yourself
    assert r["status"] == "ok"
    facts = r["facts"]
    assert facts["name"] == "Ahmad Danial bin Rahim"
    assert facts["jurisdiction"] == "peninsular_malaysia"
    assert facts["manager_no"] == "WR-0003"


def test_get_employee_missing_returns_not_found():
    assert get_employee("WR-9999")["status"] == "not_found"


AS_OF = date(2026, 9, 15)  # deterministic "today" for the seeded cast


@pytest.mark.parametrize(
    ("employee_no", "expected"),
    [
        # <2y service → statutory 8; company 18 governs
        ("WR-0001", {"status": "ok", "entitled": 18, "statutory": 8}),
        # 7y → statutory 12; company 18 governs
        ("WR-0002", {"status": "ok", "entitled": 18, "statutory": 12}),
        # 12y → statutory 16; company 18 governs
        ("WR-0003", {"status": "ok", "entitled": 18, "statutory": 16}),
    ],
)
def test_full_time_peninsular_entitlements(employee_no, expected):
    r = annual_leave_entitlement(employee_no, as_of=AS_OF)
    assert r["status"] == expected["status"]
    assert r["entitled_days"] == expected["entitled"]
    assert r["statutory_days"] == expected["statutory"]
    assert r["governed_by"].startswith("company_policy")


@pytest.mark.parametrize(
    ("employee_no", "reason_fragment"),
    [
        ("WR-0004", "part_time"),          # part-timer → escalate
        ("WR-0005", "contract"),           # contract → escalate
        ("WR-0006", "Sabah/Sarawak"),      # wrong jurisdiction → escalate
    ],
)
def test_out_of_scope_escalates(employee_no, reason_fragment):
    r = annual_leave_entitlement(employee_no, as_of=AS_OF)
    assert r["status"] == "escalate"
    assert any(reason_fragment in reason for reason in r["reasons"])
    assert "entitled_days" not in r  # escalated answers carry NO computed number


def test_unknown_employee_not_found():
    r = annual_leave_entitlement("WR-XXXX", as_of=AS_OF)
    assert r["status"] == "not_found"


# ── search_policy (step 4: the librarian tool) ──────────────────────────────

import inspect

from backend.tools import search_policy


def test_search_policy_found_with_citations_and_verbatim_text():
    r = search_policy("how much annual leave am I entitled to", "WR-0002")
    assert r["status"] == "found"
    assert r["jurisdiction_used"] == "peninsular_malaysia"
    assert 1 <= len(r["results"]) <= 4
    top = r["results"][0]
    assert top["chunk_id"] and top["authority"]          # citable labels
    assert isinstance(top["similarity"], float)
    assert top["text"].startswith(("#", "##"))           # verbatim, unedited
    # a leave question must retrieve leave material
    assert any("annual_leave" == res["topic"] for res in r["results"])


def test_search_policy_sabah_employees_get_nothing_applicable():
    r = search_policy("how much annual leave am I entitled to", "WR-0006")
    assert r["status"] == "nothing_applicable"
    assert "escalate" in r["next"]
    assert "results" not in r  # no passages leak to a non-applicable employee


def test_search_policy_unknown_employee():
    assert search_policy("anything", "WR-XXXX")["status"] == "not_found"


def test_search_policy_cannot_be_told_a_different_jurisdiction():
    """The LLM writes every argument this tool receives — so the signature
    must make 'claim a friendlier jurisdiction' impossible, not discouraged."""
    assert "jurisdiction" not in inspect.signature(search_policy).parameters
