"""Agent tools — deterministic facts for the (future) LLM loop.

Phase 1 rule of the house: the LLM may REQUEST a tool; only this code DECIDES.
Every function here is plain Python + the database — no model, no chat, no
framework. When the loop lands, it will call exactly these functions and
nothing else.

Two layers, deliberately separated:
- pure calculators (completed_years, statutory_annual_days) — testable without
  the database;
- DB-backed tools (get_employee, annual_leave_entitlement) — look up one
  person's facts and apply the V1 scope + LAW-002 precedence.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from ollama import embed
from sqlalchemy import func, select, text as sa_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import engine
from .models import (
    Approval,
    Employee,
    EmploymentStatus,
    EmploymentType,
    FlexibleWorkRequest,
    Jurisdiction,
    LeaveRequest,
    PolicyDocument,
)
from .permissions import can_decide_leave, can_see

EMBEDDING_MODEL = "bge-m3"

# eligibility first (your 12 metadata fields), geometry second (<=> = cosine).
SEARCH_SQL = sa_text("""
    SELECT chunk_id, topic, subtopic, section, source_type, authority,
           round((1 - (embedding <=> CAST(:q AS vector)))::numeric, 3) AS similarity,
           text
    FROM policy_chunks
    WHERE (CAST(:juris AS TEXT) IS NULL
           OR CAST(:juris AS TEXT) = ANY(jurisdiction))
      AND effective_from <= CAST(:as_of AS DATE)
      AND (effective_to IS NULL OR effective_to >= CAST(:as_of AS DATE))
    ORDER BY embedding <=> CAST(:q AS vector)
    LIMIT :k
""")

# Handbook §2: automated V1 covers ACTIVE FULL-TIME in Peninsular/Labuan.
ESCALATE_JURISDICTIONS = {Jurisdiction.SABAH.value, Jurisdiction.SARAWAK.value}
ESCALATE_EMPLOYMENT_TYPES = {
    EmploymentType.PART_TIME.value,
    EmploymentType.CONTRACT.value,
}
COMPANY_ANNUAL_DAYS = 18  # Handbook §4.1 (chunk HB-004) — active full-time
HOSPITALISATION_CAP_DAYS = 60  # EA 1955 s.60F, separate pool (LAW-005)


def completed_years(join: date, as_of: date) -> int:
    """Whole years of continuous service = count of anniversaries passed.

    Exact calendar math, not days/365.25: an employee joins on the 15th, the
    14th is still year N-1. Statutory tiers hinge on these boundaries.
    """
    years = as_of.year - join.year
    if (as_of.month, as_of.day) < (join.month, join.day):
        years -= 1
    return max(years, 0)


def statutory_annual_days(years: int) -> int:
    """Employment Act 1955 s.60E minimums (LAW-003, corrected): 8/8/12/16."""
    if years < 5:
        return 8
    if years < 10:
        return 12
    return 16


def statutory_sick_days(years: int) -> int:
    """EA 1955 s.60F ordinary sick-leave minimums (LAW-005): 14/18/22."""
    if years < 2:
        return 14
    if years < 5:
        return 18
    return 22


def working_days_between(start: date, end: date) -> int:
    """Weekday (Mon–Fri) count, inclusive. Weekends are additional to annual
    leave (LAW-004), so they are never deducted. Public holidays are NOT yet
    excluded — the holiday calendar is a pending Phase 3 task (HB §4.6:
    the CALCULATOR, not the LLM, decides deductible days)."""
    return sum(
        1
        for offset in range((end - start).days + 1)
        if (start + timedelta(days=offset)).weekday() < 5
    )


def _usage(employee_no: str, leave_type: str, year: int) -> tuple[Decimal, Decimal]:
    """(approved_days, pending_days) for one leave type and calendar year.

    Year attribution uses start_date (a range crossing New Year counts wholly
    to its start year — documented V1 simplification).
    """
    with Session(engine) as session:
        rows = session.execute(
            select(LeaveRequest.status, func.sum(LeaveRequest.requested_days))
            .join(Employee, Employee.id == LeaveRequest.employee_id)
            .where(
                Employee.employee_no == employee_no,
                LeaveRequest.leave_type == leave_type,
                func.extract("year", LeaveRequest.start_date) == year,
            )
            .group_by(LeaveRequest.status)
        ).all()
    approved = sum((d for s, d in rows if s == "approved"), Decimal(0))
    pending = sum(
        (d for s, d in rows if s in ("pending_manager", "pending_hr")), Decimal(0)
    )
    return approved, pending


def _scope_escalation(facts: dict, today: date) -> list[str]:
    """Reasons this employee sits outside automated V1 ([] = in scope).

    Shared by the balance tool and the submit tool so the two can never
    disagree about who is allowed to play.
    """
    reasons = []
    if facts["jurisdiction"] in ESCALATE_JURISDICTIONS:
        reasons.append("jurisdiction outside V1: Sabah/Sarawak have separate ordinances")
    if facts["employment_type"] in ESCALATE_EMPLOYMENT_TYPES:
        reasons.append(f"{facts['employment_type']} employment outside automated scope (HB §2)")
    if facts["employment_status"] != EmploymentStatus.ACTIVE.value:
        reasons.append(f"employment not active ({facts['employment_status']})")
    if facts["join_date"] > today.isoformat():
        reasons.append("join_date is in the future — data error, needs HR fix")
    return reasons


def _facts(employee_no: str) -> dict | None:
    """Raw DB lookup — internal helper; the public tool wraps it in status."""
    with Session(engine) as session:
        emp = (
            session.query(Employee)
            .filter_by(employee_no=employee_no)
            .one_or_none()
        )
        if emp is None:
            return None
        return {
            "employee_no": emp.employee_no,
            "name": emp.full_name,
            "role": emp.role.value,
            "department": emp.department,
            "manager_no": emp.manager.employee_no if emp.manager else None,
            "join_date": emp.join_date.isoformat(),
            "employment_type": emp.employment_type.value,
            "jurisdiction": emp.jurisdiction.value,
            "employment_status": emp.employment_status.value,
        }


def _check_access(employee_no: str, caller_employee_no: str | None) -> dict | None:
    """Return a forbidden response, or None when access is allowed.

    caller_employee_no=None means "the person asking is the subject" (self).
    The session layer (agent loop) always injects the real caller — the LLM
    is never trusted to name whose permissions apply.

    V1 trade-off (documented on purpose): returning not_found vs forbidden
    distinguishes "no such person" from "exists, hidden from you" — an
    existence leak to unauthorized callers. A real product would collapse
    both into one indistinguishable refusal; fine for a single-company demo.
    """
    caller = caller_employee_no or employee_no
    if caller != employee_no and not can_see(caller, employee_no):
        return {
            "status": "forbidden",
            "reason": "HR data is visible only to the employee themselves, "
                      "their direct manager, or HR/admin (handbook §9)",
            "next": "if genuinely needed, ask HR to review",
        }
    return None


def get_employee(employee_no: str, *, caller_employee_no: str | None = None) -> dict:
    """Fact lookup, access-checked. status: ok | forbidden | not_found."""
    forbidden = _check_access(employee_no, caller_employee_no)
    if forbidden:
        return forbidden
    facts = _facts(employee_no)
    if facts is None:
        return {"status": "not_found", "employee_no": employee_no}
    return {"status": "ok", "facts": facts}


def annual_leave_entitlement(
    employee_no: str,
    *,
    caller_employee_no: str | None = None,
    as_of: date | None = None,
) -> dict:
    """The decision-ready answer for "how much annual leave do I get?".

    status is one of:
      ok         — entitled_days computed, governed_by says which rule wins
      forbidden  — caller may not see this employee's HR data (§9)
      escalate   — reasons[] list; automation must stop here (handbook §8.5)
      not_found  — no such employee
    """
    today = as_of or date.today()
    forbidden = _check_access(employee_no, caller_employee_no)
    if forbidden:
        return forbidden          # deliberately carries NO target data
    facts = _facts(employee_no)
    if facts is None:
        return {"status": "not_found", "employee_no": employee_no}

    reasons = _scope_escalation(facts, today)
    if reasons:
        return {
            "status": "escalate",
            "employee_no": employee_no,
            "name": facts["name"],
            "reasons": reasons,
            "next": "route to HR review (handbook §8.5)",
        }

    yrs = completed_years(date.fromisoformat(facts["join_date"]), today)
    statutory = statutory_annual_days(yrs)
    # LAW-002: compare, the more favourable valid term governs.
    if COMPANY_ANNUAL_DAYS > statutory:
        entitled, governed = COMPANY_ANNUAL_DAYS, "company_policy HB-004 §4.1"
    else:  # (never today with 18 — kept for future policy versions, honestly)
        entitled, governed = statutory, "statutory LAW-003 s.60E"

    # the ledger speaks: approved counts as taken, pending holds days
    approved, pending = _usage(employee_no, "annual", today.year)
    remaining = entitled - approved            # after decisions
    available = remaining - pending            # minus what awaits a decision

    return {
        "status": "ok",
        "employee_no": employee_no,
        "name": facts["name"],
        "as_of": today.isoformat(),
        "years_of_service": yrs,
        "statutory_days": statutory,
        "company_days": COMPANY_ANNUAL_DAYS,
        "entitled_days": entitled,
        "approved_days": float(approved),
        "pending_days": float(pending),
        "remaining_days": float(remaining),
        "available_days": float(available),
        "governed_by": governed,
        "note": "available = entitled − approved − pending; pending requests "
                "await a human decision and already hold their days",
    }


# ── step 4: the librarian tool ────────────────────────────────────────────────

def search_chunks(
    question: str,
    jurisdiction: str | None = None,
    k: int = 4,
    as_of: date | None = None,
) -> list[dict]:
    """Low-level search: fingerprint the question (BGE-M3), let Postgres pick.

    jurisdiction=None skips the eligibility filter (demo/testing only —
    tools exposed to the agent always pass one).
    """
    qvec = embed(model=EMBEDDING_MODEL, input=[question],
                 keep_alive="30m")["embeddings"][0]
    keys = ("chunk_id", "topic", "subtopic", "section", "source_type",
            "authority", "similarity", "text")
    with Session(engine) as session:
        rows = session.execute(SEARCH_SQL, {
            "q": str(qvec),
            "juris": jurisdiction,
            "as_of": as_of or date.today(),
            "k": k,
        }).fetchall()
    return [
        {**dict(zip(keys, row)), "similarity": float(row[6])}
        for row in rows
    ]


def search_policy(
    question: str,
    employee_no: str,
    *,
    caller_employee_no: str | None = None,
    k: int = 4,
) -> dict:
    """Find policy/law passages that EXPLAIN a topic to this employee.

    Note the signature: there is NO jurisdiction parameter on purpose.
    The employee's legal context is read from their DB row, so the LLM —
    which writes every argument it passes — can never "claim" a different
    jurisdiction to unlock rules that don't apply to them. caller is
    likewise session-injected and checked before anything is searched.

    status: found | forbidden | nothing_applicable | not_found
    Result text is VERBATIM (citations must be quotable); this tool explains
    rules, it never computes numbers — entitlement answers belong to
    annual_leave_entitlement, and on any conflict that one governs.
    """
    forbidden = _check_access(employee_no, caller_employee_no)
    if forbidden:
        return forbidden
    facts = _facts(employee_no)
    if facts is None:
        return {"status": "not_found", "employee_no": employee_no}

    results = search_chunks(question, jurisdiction=facts["jurisdiction"], k=k)
    # Cap the text sent to the answering model: prompt processing is the main
    # latency cost on a local 3B model, and the top passages carry the answer.
    # The database keeps the full text; this is a context-window economy.
    for r in results:
        if len(r["text"]) > 1000:
            r["text"] = r["text"][:1000] + " […truncated for context]"
    if not results:
        return {
            "status": "nothing_applicable",
            "employee_no": employee_no,
            "jurisdiction": facts["jurisdiction"],
            "reason": "no V1-eligible policy or law passages cover this "
                      "question for this employee's context",
            "next": "escalate to HR review (handbook §8.5)",
        }
    return {
        "status": "found",
        "question": question,
        "asked_for": employee_no,
        "jurisdiction_used": facts["jurisdiction"],
        "results": results,
        "note": "explanatory passages with citations; all numbers must come "
                "from the deterministic tools",
    }


# ── step 2 of phase 3: the writing hand ──────────────────────────────────────

SUBMITTABLE_TYPES = ("annual", "sick", "hospitalisation")


def _coerce_bool(value) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "yes", "1")


def submit_leave_request(
    leave_type: str,
    start_date: str,
    end_date: str,
    *,
    caller_employee_no: str | None = None,
    day_portion: str | None = None,
    reason: str | None = None,
    medical_certificate_provided: bool | str | None = None,
    medical_certificate_reference: str | None = None,
    employee_notified_at: str | None = None,
    as_of: date | None = None,
) -> dict:
    """Create ONE pending leave request for the caller. INSERT-ONLY by design:
    there is no code path here that can approve, reject, cancel or modify.

    Route by type (handbook §8): annual → pending_manager; sick and
    hospitalisation → pending_hr (medical verification).

    status: created | rejected | escalate | not_found
    """
    today = as_of or date.today()

    if not caller_employee_no:
        return {"status": "rejected",
                "reason": "a request must have an owner — no caller identity"}
    if leave_type not in SUBMITTABLE_TYPES:
        return {"status": "rejected",
                "reason": f"leave_type must be one of {list(SUBMITTABLE_TYPES)}"}
    try:
        start = date.fromisoformat(str(start_date))
        end = date.fromisoformat(str(end_date))
    except ValueError:
        return {"status": "rejected",
                "reason": "dates must be ISO format, e.g. 2026-12-24"}
    if end < start:
        return {"status": "rejected", "reason": "end_date is before start_date"}

    facts = _facts(caller_employee_no)
    if facts is None:
        return {"status": "not_found", "employee_no": caller_employee_no}
    reasons = _scope_escalation(facts, today)
    if reasons:
        return {"status": "escalate", "reasons": reasons,
                "next": "route to HR review (handbook §8.5) — nothing was created"}

    # deductible days — the CALCULATOR decides, never the LLM (HB §4.6)
    if day_portion:
        if day_portion not in ("am", "pm") or start != end:
            return {"status": "rejected",
                    "reason": "day_portion applies only to a single-day request"}
        requested = Decimal("0.5") if start.weekday() < 5 else Decimal("0")
    else:
        requested = Decimal(working_days_between(start, end))
    if requested <= 0:
        return {"status": "rejected",
                "reason": "range contains no working days (weekends are "
                          "always excluded; public holidays not yet tracked)"}

    yrs = completed_years(date.fromisoformat(facts["join_date"]), today)
    approved, pending = _usage(caller_employee_no, leave_type, start.year)
    if leave_type == "annual":
        cap = max(COMPANY_ANNUAL_DAYS, statutory_annual_days(yrs))
        route = "pending_manager"
    elif leave_type == "sick":
        cap = statutory_sick_days(yrs)
        route = "pending_hr"
    else:
        cap = HOSPITALISATION_CAP_DAYS
        route = "pending_hr"
    available = Decimal(cap) - approved - pending

    if requested > available:
        return {
            "status": "rejected",
            "reason": f"insufficient balance: requested {float(requested)} days, "
                      f"available {float(available)} (cap {cap}, "
                      f"approved {float(approved)}, pending {float(pending)})",
            "next": "offer fewer dates, other dates, or HR review (HB §4.5)",
        }

    notified = None
    if employee_notified_at:
        try:
            notified = datetime.fromisoformat(str(employee_notified_at))
        except ValueError:
            return {"status": "rejected",
                    "reason": "employee_notified_at must be an ISO datetime"}

    with Session(engine) as session:
        year_count = session.scalar(
            select(func.count()).select_from(LeaveRequest)
            .where(LeaveRequest.request_no.like(f"LV-{start.year}-%"))
        )
        employee_id = session.scalar(
            select(Employee.id).where(Employee.employee_no == caller_employee_no)
        )
        row = LeaveRequest(
            request_no=f"LV-{start.year}-{year_count + 1:04d}",
            employee_id=employee_id,
            leave_type=leave_type,
            start_date=start,
            end_date=end,
            requested_days=requested,
            day_portion=day_portion,
            reason=reason,
            medical_certificate_provided=_coerce_bool(medical_certificate_provided),
            medical_certificate_reference=medical_certificate_reference,
            employee_notified_at=notified,
            status=route,
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return {"status": "rejected",
                    "reason": "a live request for the same dates and type "
                              "already exists for this employee"}
        request_no = row.request_no

    return {
        "status": "created",
        "request_no": request_no,
        "leave_type": leave_type,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "days": float(requested),
        "route": route,
        "note": "submitted for a human decision — the assistant cannot "
                "approve, reject or cancel it",
    }


# ── phase 4: the decision recorder ───────────────────────────────────────────

def decide_leave_request(
    request_no: str,
    decision: str,
    *,
    caller_employee_no: str | None = None,
    reason: str | None = None,
) -> dict:
    """Record a HUMAN decision (approved/rejected) on a pending leave request.

    The agent never decides — it only writes down what an authorized human
    said, after the backend checks that the caller really holds that
    authority (permissions.can_decide_leave):
      pending_manager → the requester's direct manager, or HR/admin
      pending_hr      → HR/admin only
    Self-decision is never allowed. A rejection requires a reason (it becomes
    the employee-facing explanation in the audit trail).

    status: decided | forbidden | rejected | not_found
    """
    if not caller_employee_no:
        return {"status": "rejected",
                "reason": "a decision must have an identified human caller"}
    if decision not in ("approved", "rejected"):
        return {"status": "rejected",
                "reason": "decision must be 'approved' or 'rejected'"}
    if decision == "rejected" and not (reason or "").strip():
        return {"status": "rejected",
                "reason": "a rejection needs a reason — it is recorded for "
                          "the employee"}

    with Session(engine) as session:
        req = session.scalar(
            select(LeaveRequest).where(LeaveRequest.request_no == request_no)
        )
        if req is None:
            return {"status": "not_found", "request_no": request_no}
        if req.status not in ("pending_manager", "pending_hr"):
            return {"status": "rejected",
                    "reason": f"request is '{req.status}' — only pending "
                              f"requests can be decided"}

        requester = session.get(Employee, req.employee_id)
        level = "manager" if req.status == "pending_manager" else "hr"
        if not can_decide_leave(caller_employee_no, requester.employee_no, level):
            return {
                "status": "forbidden",
                "reason": f"this is a '{level}'-level decision and you do not "
                          f"hold that authority for {requester.employee_no}",
                "next": "the employee's direct manager, or HR, must decide",
            }

        approver = session.scalar(
            select(Employee).where(Employee.employee_no == caller_employee_no)
        )
        session.add(Approval(
            leave_request_id=req.id,
            approval_level=level,
            approver_employee_id=approver.id,
            decision=decision,
            reason=reason,
            requested_at=req.submitted_at,
        ))
        req.status = decision
        req.decided_at = func.now()
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return {"status": "rejected",
                    "reason": "this request already has a recorded decision "
                              "at that level"}

        return {
            "status": "decided",
            "request_no": request_no,
            "decision": decision,
            "approval_level": level,
            "decided_by": caller_employee_no,
            "employee_no": requester.employee_no,
            "reason": reason,
            "note": "recorded with full audit trail — balances now reflect "
                    "this decision",
        }


# ── phase 4 part 2: flexible working arrangements ────────────────────────────

FWA_STATUTORY_DAYS = 60      # EA 1955 s.60Q, per the legal corpus (LAW-008)
FWA_COMPANY_TARGET_DAYS = 30  # Handbook §7.5 internal service target


def submit_fwa_request(
    requested_arrangement: str,
    *,
    caller_employee_no: str | None = None,
    change_hours: bool | str = False,
    change_days: bool | str = False,
    change_place: bool | str = False,
    proposed_start_date: str | None = None,
    proposed_end_date: str | None = None,
    employee_reason: str | None = None,
    as_of: date | None = None,
) -> dict:
    """Create ONE pending flexible-working request for the caller.

    INSERT-only, like leave. Both deadline clocks are computed HERE, by code,
    from the submission moment (handbook §7.5) and never by the LLM; the
    statutory basis row is recorded for provenance. A request must change at
    least one dimension (hours/days/place) — that check exists in both the
    tool and the database.

    status: created | rejected | escalate | not_found
    """
    today = as_of or date.today()
    if not caller_employee_no:
        return {"status": "rejected",
                "reason": "a request must have an owner — no caller identity"}
    flags = {k: _coerce_bool(v) for k, v in (
        ("hours", change_hours), ("days", change_days), ("place", change_place),
    )}
    if not any(flags.values()):
        return {"status": "rejected",
                "reason": "a flexible-work request must change at least one of: "
                          "hours, days, place of work"}
    if not (requested_arrangement or "").strip():
        return {"status": "rejected",
                "reason": "requested_arrangement describing the desired "
                          "arrangement is required"}

    start = end = None
    if proposed_start_date:
        try:
            start = date.fromisoformat(str(proposed_start_date))
        except ValueError:
            return {"status": "rejected",
                    "reason": "proposed_start_date must be ISO format YYYY-MM-DD"}
    else:
        return {"status": "rejected",
                "reason": "proposed_start_date is required (handbook §7.3) — "
                          "ask the employee when it should begin"}
    if proposed_end_date:
        try:
            end = date.fromisoformat(str(proposed_end_date))
        except ValueError:
            return {"status": "rejected",
                    "reason": "proposed_end_date must be ISO format YYYY-MM-DD"}
        if end < start:
            return {"status": "rejected",
                    "reason": "proposed_end_date is before proposed_start_date"}

    facts = _facts(caller_employee_no)
    if facts is None:
        return {"status": "not_found", "employee_no": caller_employee_no}
    reasons = _scope_escalation(facts, today)
    if reasons:
        return {"status": "escalate", "reasons": reasons,
                "next": "route to HR review (handbook §8.5) — nothing was created"}

    submitted = datetime.now(timezone.utc)
    decision_due = submitted + timedelta(days=FWA_STATUTORY_DAYS)
    company_target = submitted + timedelta(days=FWA_COMPANY_TARGET_DAYS)

    with Session(engine) as session:
        basis_id = session.scalar(
            select(PolicyDocument.id).where(
                PolicyDocument.local_path == "knowledge/law/workright_legal_policy_v1.md"
            )
        )
        year_count = session.scalar(
            select(func.count()).select_from(FlexibleWorkRequest)
            .where(FlexibleWorkRequest.request_no.like(f"FW-{today.year}-%"))
        )
        employee_id = session.scalar(
            select(Employee.id).where(Employee.employee_no == caller_employee_no)
        )
        row = FlexibleWorkRequest(
            request_no=f"FW-{today.year}-{year_count + 1:04d}",
            employee_id=employee_id,
            change_hours=flags["hours"],
            change_days=flags["days"],
            change_place=flags["place"],
            requested_arrangement=requested_arrangement.strip(),
            employee_reason=employee_reason,
            proposed_start_date=start,
            proposed_end_date=end,
            submitted_at=submitted,
            decision_due_at=decision_due,
            target_decision_at=company_target,
            decision_basis_policy_id=basis_id,
            status="pending_manager",
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return {"status": "rejected",
                    "reason": "could not create the request — please retry"}
        request_no = row.request_no

    return {
        "status": "created",
        "request_no": request_no,
        "dimensions": [k for k, v in flags.items() if v],
        "requested_arrangement": requested_arrangement.strip(),
        "proposed_start_date": start.isoformat(),
        "proposed_end_date": end.isoformat() if end else None,
        "route": "pending_manager (then HR)",
        "statutory_due": decision_due.date().isoformat(),
        "company_target": company_target.date().isoformat(),
        "note": "submitted for human decisions — manager first, then HR. "
                "The assistant cannot decide.",
    }


def decide_request(
    request_no: str,
    decision: str,
    *,
    caller_employee_no: str | None = None,
    reason: str | None = None,
) -> dict:
    """Record a HUMAN decision on a leave (LV-) or flexible-work (FW-) request.

    Leave: one stage (manager for annual, HR for sick/hospitalisation).
    Flexible work: TWO stages — a manager 'approved' ADVANCES the request to
    pending_hr (status "advanced"); only the HR stage finalizes.

    Authority is verified by the backend (permissions.can_decide_leave);
    self-decision is never allowed; rejections require a reason.
    """
    if not isinstance(request_no, str):
        return {"status": "rejected", "reason": "request_no is required"}
    if request_no.startswith("LV-"):
        return decide_leave_request(request_no, decision,
                                    caller_employee_no=caller_employee_no,
                                    reason=reason)
    if not request_no.startswith("FW-"):
        return {"status": "rejected",
                "reason": "request_no must start with LV- (leave) or FW- "
                          "(flexible work)"}

    if not caller_employee_no:
        return {"status": "rejected",
                "reason": "a decision must have an identified human caller"}
    if decision not in ("approved", "rejected"):
        return {"status": "rejected",
                "reason": "decision must be 'approved' or 'rejected'"}
    if decision == "rejected" and not (reason or "").strip():
        return {"status": "rejected",
                "reason": "a rejection needs a reason — it is recorded for "
                          "the employee (handbook §7.6)"}

    with Session(engine) as session:
        req = session.scalar(
            select(FlexibleWorkRequest)
            .where(FlexibleWorkRequest.request_no == request_no)
        )
        if req is None:
            return {"status": "not_found", "request_no": request_no}
        if req.status not in ("pending_manager", "pending_hr"):
            return {"status": "rejected",
                    "reason": f"request is '{req.status}' — only pending "
                              f"requests can be decided"}

        requester = session.get(Employee, req.employee_id)
        level = "manager" if req.status == "pending_manager" else "hr"
        if not can_decide_leave(caller_employee_no, requester.employee_no, level):
            return {
                "status": "forbidden",
                "reason": f"this is a '{level}'-stage decision and you do not "
                          f"hold that authority for {requester.employee_no}",
                "next": "the employee's direct manager, or HR, must decide",
            }

        approver = session.scalar(
            select(Employee).where(Employee.employee_no == caller_employee_no)
        )
        session.add(Approval(
            fwa_request_id=req.id,
            approval_level=level,
            approver_employee_id=approver.id,
            decision=decision,
            reason=reason,
            requested_at=req.submitted_at,
        ))

        if decision == "rejected":
            req.status = "rejected"
            req.decision_reason = reason
            req.decided_at = func.now()
            outcome = "decided"
            note = "rejection recorded with full audit trail"
        elif level == "manager":
            req.status = "pending_hr"           # advances, NOT final
            outcome = "advanced"
            note = "manager stage recorded — the request now awaits HR"
        else:
            req.status = "approved"
            req.decision_reason = reason
            req.decided_at = func.now()
            outcome = "decided"
            note = "final approval recorded — both stages complete"

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return {"status": "rejected",
                    "reason": "this request already has a recorded decision "
                              "at that stage"}

        return {
            "status": outcome,
            "request_no": request_no,
            "decision": decision,
            "stage": level,
            "decided_by": caller_employee_no,
            "employee_no": requester.employee_no,
            "new_status": req.status,
            "reason": reason,
            "note": note,
        }


# ── the missing capability: finding requests that need a decision ────────────

def list_pending_requests(*, caller_employee_no: str | None = None) -> dict:
    """List requests that are AWAITING A DECISION, scoped to the caller.

    Why this tool exists: without it, nobody could DISCOVER request numbers —
    the agent could only fetch ones it was already told about. Asking
    "any pending requests?" returned nothing because the capability simply
    did not exist.

    Scope (backend-enforced):
      employee  → their OWN pending requests (awaiting decisions by others)
      manager   → their direct reports' pending-manager requests (to decide)
                  plus their own pending
      hr/admin  → everything pending (manager and HR stages)
    """
    if not caller_employee_no:
        return {"status": "rejected", "reason": "no caller identity"}
    caller_facts = _facts(caller_employee_no)
    if caller_facts is None:
        return {"status": "not_found", "employee_no": caller_employee_no}
    role = caller_facts["role"]

    items: list[dict] = []
    with Session(engine) as session:
        caller = session.scalar(
            select(Employee).where(Employee.employee_no == caller_employee_no)
        )
        pending_statuses = ("pending_manager", "pending_hr")

        for req, emp in session.execute(
            select(LeaveRequest, Employee)
            .join(Employee, Employee.id == LeaveRequest.employee_id)
            .where(LeaveRequest.status.in_(pending_statuses))
        ):
            if not (role in ("hr", "admin")
                    or emp.id == caller.id
                    or (role == "manager" and emp.manager_id == caller.id
                        and req.status == "pending_manager")):
                continue
            portion = f" ({req.day_portion})" if req.day_portion else ""
            items.append({
                "request_no": req.request_no,
                "kind": "leave",
                "employee_no": emp.employee_no,
                "employee_name": emp.full_name,
                "summary": f"{req.leave_type} {req.start_date} → {req.end_date} "
                           f"({float(req.requested_days)} days{portion})",
                "status": req.status,
                "submitted_at": req.submitted_at.isoformat() if req.submitted_at else None,
            })

        for req, emp in session.execute(
            select(FlexibleWorkRequest, Employee)
            .join(Employee, Employee.id == FlexibleWorkRequest.employee_id)
            .where(FlexibleWorkRequest.status.in_(pending_statuses))
        ):
            if not (role in ("hr", "admin")
                    or emp.id == caller.id
                    or (role == "manager" and emp.manager_id == caller.id
                        and req.status == "pending_manager")):
                continue
            dims = ", ".join(
                name for name, flag in (("hours", req.change_hours),
                                        ("days", req.change_days),
                                        ("place", req.change_place)) if flag
            )
            items.append({
                "request_no": req.request_no,
                "kind": "flexible_work",
                "employee_no": emp.employee_no,
                "employee_name": emp.full_name,
                "summary": f"change {dims}: {req.requested_arrangement} "
                           f"(from {req.proposed_start_date})",
                "status": req.status,
                "submitted_at": req.submitted_at.isoformat() if req.submitted_at else None,
            })

    items.sort(key=lambda i: i["submitted_at"] or "")
    scope = {"employee": "your own requests (others decide these)",
             "manager": "your direct reports' requests needing YOUR decision, "
                        "plus your own",
             "hr": "everything pending",
             "admin": "everything pending"}[role]
    return {
        "status": "ok",
        "scope": scope,
        "count": len(items),
        "pending": items,
        "note": ("to decide one, use decide_request with its request_no"
                 if items else "nothing is awaiting a decision"),
    }
