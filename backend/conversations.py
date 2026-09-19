"""Conversation memory — where short-term memory is kept.

Design (agreed): durable STORAGE for short-term NATURE. The database is the
truth, same as everywhere else; the model never decides what is remembered —
this module and the loop code do.

Security fence: a conversation belongs to ONE employee; every load checks
ownership, so a conversation id can never pull someone else's words into a
prompt.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import engine
from .models import Conversation, Employee, Message

HISTORY_WINDOW = 10   # messages fed back to the model (bounded: tokens = speed)


def create_conversation(employee_no: str) -> str | None:
    """Open a new conversation for this employee. Returns its id."""
    with Session(engine) as session:
        employee_id = session.scalar(
            select(Employee.id).where(Employee.employee_no == employee_no)
        )
        if employee_id is None:
            return None
        conv = Conversation(employee_id=employee_id)
        session.add(conv)
        session.commit()
        return conv.id


def owns(conversation_id: str, employee_no: str) -> bool:
    """True only if this conversation belongs to this employee."""
    with Session(engine) as session:
        return session.scalar(
            select(Conversation.id)
            .join(Employee, Employee.id == Conversation.employee_id)
            .where(Conversation.id == conversation_id,
                   Employee.employee_no == employee_no)
        ) is not None


def append_message(conversation_id: str, role: str, content: str,
                   trace: list | None = None) -> None:
    """Write one turn and keep the conversation's activity fresh.

    The trace (tool calls, args, statuses) makes every chat replayable —
    the same accountability idea as the approvals table.
    """
    with Session(engine) as session:
        session.add(Message(conversation_id=conversation_id, role=role,
                            content=content, trace=trace))
        session.execute(
            Conversation.__table__.update()
            .where(Conversation.id == conversation_id)
            .values(last_active_at=func.now(),
                    title=func.coalesce(
                        Conversation.title,
                        func.left(content, 60) if role == "user" else None,
                    ))
        )
        session.commit()


def history_for_prompt(conversation_id: str, limit: int = HISTORY_WINDOW) -> list[dict]:
    """The last `limit` turns, oldest-first, ready for the model."""
    with Session(engine) as session:
        rows = session.execute(
            select(Message.role, Message.content)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        ).all()
    return [{"role": r, "content": c} for r, c in reversed(rows)]


def list_conversations(employee_no: str, limit: int = 20) -> list[dict]:
    """This employee's recent conversations (newest activity first)."""
    with Session(engine) as session:
        rows = session.execute(
            select(Conversation)
            .join(Employee, Employee.id == Conversation.employee_id)
            .where(Employee.employee_no == employee_no)
            .order_by(Conversation.last_active_at.desc())
            .limit(limit)
        ).scalars().all()
        return [
            {
                "id": str(c.id),
                "title": c.title,
                "started_at": c.started_at.isoformat(),
                "last_active_at": c.last_active_at.isoformat(),
            }
            for c in rows
        ]


def messages_of(conversation_id: str, employee_no: str) -> list[dict] | None:
    """Full transcript — None if the conversation isn't this employee's."""
    if not owns(conversation_id, employee_no):
        return None
    with Session(engine) as session:
        rows = session.execute(
            select(Message.role, Message.content, Message.trace, Message.created_at)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        ).all()
    return [
        {"role": r, "content": c, "trace": t, "created_at": ts.isoformat()}
        for r, c, t, ts in rows
    ]
