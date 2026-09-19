"""Tests for conversation memory: ownership fence, window, ordering, title."""

import pytest

from backend import conversations


@pytest.fixture(autouse=True)
def cleanup_conversations():
    """Delete only the conversations this module creates."""
    created: list[str] = []
    yield created
    from sqlalchemy import delete
    from sqlalchemy.orm import Session
    from backend.database import engine
    from backend.models import Conversation
    if created:
        with Session(engine) as s:
            s.execute(delete(Conversation).where(Conversation.id.in_(created)))
            s.commit()


def new_conversation(cleanup, employee_no="WR-0002") -> str:
    conv_id = conversations.create_conversation(employee_no)
    assert conv_id is not None
    cleanup.append(conv_id)
    return conv_id


def test_create_returns_id_for_known_employee(cleanup_conversations):
    assert new_conversation(cleanup_conversations)


def test_create_returns_none_for_unknown_employee():
    assert conversations.create_conversation("WR-XXXX") is None


def test_ownership_fence(cleanup_conversations):
    conv_id = new_conversation(cleanup_conversations)          # Wei Jie's
    assert conversations.owns(conv_id, "WR-0002") is True
    assert conversations.owns(conv_id, "WR-0001") is False     # a peer: no
    assert conversations.owns(conv_id, "WR-0007") is False     # even HR: no


def test_messages_of_refuses_non_owner(cleanup_conversations):
    conv_id = new_conversation(cleanup_conversations)
    conversations.append_message(conv_id, "user", "hello")
    assert conversations.messages_of(conv_id, "WR-0001") is None
    assert len(conversations.messages_of(conv_id, "WR-0002")) == 1


def test_history_is_oldest_first_and_bounded(cleanup_conversations):
    conv_id = new_conversation(cleanup_conversations)
    for i in range(12):
        role = "user" if i % 2 == 0 else "assistant"
        conversations.append_message(conv_id, role, f"turn {i}")

    window = conversations.history_for_prompt(conv_id, limit=10)
    assert len(window) == 10
    assert window[0]["content"] == "turn 2"       # the LAST 10, not the first
    assert window[-1]["content"] == "turn 11"     # oldest-first ordering
    assert [m["role"] for m in window][:2] == ["user", "assistant"]


def test_title_is_taken_from_the_first_user_message(cleanup_conversations):
    conv_id = new_conversation(cleanup_conversations)
    conversations.append_message(conv_id, "user", "book my Christmas leave please")
    conversations.append_message(conv_id, "assistant", "done-ish")
    listed = [c for c in conversations.list_conversations("WR-0002")
              if c["id"] == str(conv_id)]        # ids come back as strings
    assert listed and listed[0]["title"].startswith("book my Christmas")


def test_list_conversations_scoped_to_owner(cleanup_conversations):
    mine = new_conversation(cleanup_conversations, "WR-0002")
    ids = {c["id"] for c in conversations.list_conversations("WR-0001")}
    assert str(mine) not in ids
