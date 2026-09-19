"""Read models for the UI pages: my requests, pending decisions, audit trails.

Scoping rule: pending items reuse tools.list_pending_requests — ONE source of
truth for who may decide what. This module only enriches with audit rows and
shapes the payloads for the browser.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import engine
from .models import Approval, Employee, FlexibleWorkRequest, LeaveRequest


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _audit_rows(session: Session, *, leave_request_id=None,
                fwa_request_id=None) -> list[dict]:
    """Decision history for one request, oldest first, with approver names."""
    query = select(Approval, Employee).join(
        Employee, Employee.id == Approval.approver_employee_id)
    if leave_request_id is not None:
        query = query.where(Approval.leave_request_id == leave_request_id)
    else:
        query = query.where(Approval.fwa_request_id == fwa_request_id)
    rows = session.execute(query.order_by(Approval.created_at)).all()
    return [
        {
            "level": a.approval_level,
            "approver": emp.full_name,
            "decision": a.decision,
            "reason": a.reason,
            "decided_at": _iso(a.decided_at),
        }
        for a, emp in rows
    ]


def audit_for(request_no: str) -> list[dict]:
    with Session(engine) as session:
        leave = session.scalar(
            select(LeaveRequest).where(LeaveRequest.request_no == request_no))
        if leave is not None:
            return _audit_rows(session, leave_request_id=leave.id)
        fwa = session.scalar(
            select(FlexibleWorkRequest).where(FlexibleWorkRequest.request_no == request_no))
        if fwa is not None:
            return _audit_rows(session, fwa_request_id=fwa.id)
    return []


def my_requests(employee_no: str) -> list[dict]:
    """Every request this employee has ever made, newest first, with audit."""
    with Session(engine) as session:
        emp = session.scalar(
            select(Employee).where(Employee.employee_no == employee_no))
        if emp is None:
            return []
        items: list[dict] = []

        for req in session.scalars(
            select(LeaveRequest).where(LeaveRequest.employee_id == emp.id)
        ):
            portion = f" ({req.day_portion})" if req.day_portion else ""
            items.append({
                "request_no": req.request_no,
                "kind": "leave",
                "summary": f"{req.leave_type} · {req.start_date} → {req.end_date} "
                           f"· {float(req.requested_days)} day(s){portion}",
                "status": req.status,
                "submitted_at": _iso(req.submitted_at),
                "decided_at": _iso(req.decided_at),
                # leave has no decision_reason column — a rejection's reason
                # lives in the audit row (that's the single source of truth)
                "audit": _audit_rows(session, leave_request_id=req.id),
            })

        for req in session.scalars(
            select(FlexibleWorkRequest)
            .where(FlexibleWorkRequest.employee_id == emp.id)
        ):
            dims = ", ".join(
                name for name, flag in (("hours", req.change_hours),
                                        ("days", req.change_days),
                                        ("place", req.change_place)) if flag)
            items.append({
                "request_no": req.request_no,
                "kind": "flexible_work",
                "summary": f"change {dims} · {req.requested_arrangement} "
                           f"· from {req.proposed_start_date}"
                           + (f" to {req.proposed_end_date}" if req.proposed_end_date else ""),
                "status": req.status,
                "submitted_at": _iso(req.submitted_at),
                "decided_at": _iso(req.decided_at),
                "decision_reason": req.decision_reason,
                "statutory_due": _iso(req.decision_due_at),
                "company_target": _iso(req.target_decision_at),
                "audit": _audit_rows(session, fwa_request_id=req.id),
            })

    items.sort(key=lambda i: i["submitted_at"] or "", reverse=True)
    return items


def pending_for(employee_no: str) -> list[dict]:
    """Items awaiting this caller's decision — same scoping as the agent tool,
    enriched with any audit rows recorded so far (e.g. the manager stage of an
    FWA that now sits with HR)."""
    from .tools import list_pending_requests

    result = list_pending_requests(caller_employee_no=employee_no)
    if result["status"] != "ok":
        return []
    with Session(engine) as session:
        for item in result["pending"]:
            item["audit"] = audit_for(item["request_no"])
    return result["pending"]
