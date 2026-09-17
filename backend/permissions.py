"""Access control — handbook §9 ("must not expose another employee's
private HR data") as BACKEND enforcement, not an instruction to the LLM.

Two layers:
- allowed(...)  pure truth table — testable with zero database
- can_see(...)  resolves roles/manager links from the DB, then asks the table
"""

from sqlalchemy.orm import Session

from .database import engine
from .models import Employee


def allowed(caller_role: str, caller_employee_no: str,
            target_employee_no: str, target_manager_no: str | None) -> bool:
    # own data always OK
    if caller_employee_no == target_employee_no:
        return True
    # HR and admin see everything
    if caller_role in ("hr", "admin"):
        return True
    # managers see their DIRECT reports only (transitive chains = future need)
    if caller_role == "manager" and target_manager_no == caller_employee_no:
        return True
    return False


def can_see(caller_employee_no: str, target_employee_no: str) -> bool:
    """False if either person doesn't exist — unknowns get no access anywhere."""
    with Session(engine) as session:
        caller = session.query(Employee).filter_by(
            employee_no=caller_employee_no).one_or_none()
        target = session.query(Employee).filter_by(
            employee_no=target_employee_no).one_or_none()
        if caller is None or target is None:
            return False
        return allowed(
            caller.role.value,
            caller.employee_no,
            target.employee_no,
            target.manager.employee_no if target.manager else None,
        )


def can_decide_leave(caller_employee_no: str, requester_employee_no: str,
                     level: str) -> bool:
    """Authority to RECORD a decision on someone's leave request.

    'manager' level: the requester's own direct manager, or HR/admin.
    'hr' level:      HR/admin only — managers cannot do HR's verification job.
    Self-decision is NEVER allowed, even for HR on their own request
    (an independent human must decide; handbook §8 flow).
    """
    if caller_employee_no == requester_employee_no:
        return False
    with Session(engine) as session:
        caller = session.query(Employee).filter_by(
            employee_no=caller_employee_no).one_or_none()
        requester = session.query(Employee).filter_by(
            employee_no=requester_employee_no).one_or_none()
        if caller is None or requester is None:
            return False
        if caller.role.value in ("hr", "admin"):
            return True
        if level == "hr":
            return False
        return (
            caller.role.value == "manager"
            and requester.manager is not None
            and requester.manager.employee_no == caller_employee_no
        )
