"""WorkRight backend entry point.

The API surface:
  GET  /health        — liveness + database layers
  POST /auth/login    — email + password → session cookie
  POST /auth/logout   — revoke the session
  GET  /auth/me       — who am I?
  POST /chat          — the agent's front door (session-identified)
  POST /chat/stream   — same, but streams the agent's progress as SSE
"""

import asyncio
import json
import queue
import threading

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session as OrmSession

from . import auth, conversations
from .agent import run_agent
from .database import engine
from .models import PolicyChunk, PolicyDocument

app = FastAPI(title="WorkRight backend")

SESSION_COOKIE = "wr_session"


@app.get("/health")
def health() -> dict:
    try:
        with engine.connect() as conn:
            pg_version = conn.execute(
                text("SHOW server_version;")
            ).scalar_one()
            vector_version = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
            ).scalar_one()
        return {
            "status": "ok",
            "database": "up",
            "postgres": pg_version,
            "pgvector": vector_version,
        }
    except Exception:
        # Never leak connection details or error text to a public endpoint.
        return {"status": "degraded", "database": "down"}


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/auth/login")
def login_endpoint(body: LoginRequest, response: Response) -> dict:
    """Verify credentials; the session token goes into an httpOnly cookie."""
    result = auth.login(body.email, body.password)
    if result["status"] != "ok":
        # one message for both wrong-email and wrong-password (no user probing)
        raise HTTPException(status_code=401, detail="invalid email or password")
    response.set_cookie(
        SESSION_COOKIE,
        result["token"],
        httponly=True,          # JavaScript cannot read it (XSS mitigation)
        samesite="lax",         # basic CSRF mitigation
        max_age=auth.SESSION_LIFETIME_DAYS * 24 * 3600,
    )
    return {
        "employee_no": result["employee_no"],
        "name": result["name"],
        "role": result["role"],
    }


@app.post("/auth/logout")
def logout_endpoint(request: Request, response: Response) -> dict:
    auth.logout(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE)
    return {"status": "logged_out"}


@app.get("/auth/me")
def me_endpoint(request: Request) -> dict:
    identity = auth.resolve(request.cookies.get(SESSION_COOKIE))
    if identity is None:
        raise HTTPException(status_code=401, detail="not logged in")
    return identity


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    # NOTE: no employee_no — identity comes from the session cookie ONLY.
    # conversation_id (optional): continue an existing conversation; its
    # history is loaded from the database and fed to the model. Omit to
    # start a new one — the server creates it and returns its id.


@app.post("/chat")
def chat(request: Request, body: ChatRequest) -> dict:
    """One question in, one answer out — as the LOGGED-IN person.

    NOTE: the loop takes seconds (2–4 local LLM calls); `def` (not async)
    keeps FastAPI serving other requests meanwhile.
    """
    identity = auth.resolve(request.cookies.get(SESSION_COOKIE))
    if identity is None:
        raise HTTPException(status_code=401,
                            detail="login required — POST /auth/login first")

    conversation_id = body.conversation_id
    if conversation_id:
        if not conversations.owns(conversation_id, identity["employee_no"]):
            raise HTTPException(status_code=404, detail="conversation not found")
    else:
        conversation_id = conversations.create_conversation(identity["employee_no"])

    history = conversations.history_for_prompt(conversation_id)
    conversations.append_message(conversation_id, "user", body.message)
    try:
        result = run_agent(body.message, identity["employee_no"], history=history)
    except Exception:
        return {"status": "error",
                "reason": "agent or local model unavailable — try again"}
    conversations.append_message(conversation_id, "assistant", result["answer"],
                                 trace=result["trace"])
    result["conversation_id"] = str(conversation_id)
    return result


@app.post("/chat/stream")
async def chat_stream(request: Request, body: ChatRequest) -> StreamingResponse:
    """Same agent, same rules — but the loop's progress streams live (SSE).

    The agent runs in a worker thread (it is blocking: 2–4 local LLM calls);
    its on_event callbacks land in a queue which this generator drains into
    Server-Sent Events. Each event is one line: data: {...}\n\n
    """
    identity = auth.resolve(request.cookies.get(SESSION_COOKIE))
    if identity is None:
        raise HTTPException(status_code=401,
                            detail="login required — POST /auth/login first")

    conversation_id = body.conversation_id
    if conversation_id:
        if not conversations.owns(conversation_id, identity["employee_no"]):
            raise HTTPException(status_code=404, detail="conversation not found")
    else:
        conversation_id = conversations.create_conversation(identity["employee_no"])

    # memory: last N turns from the DATABASE, assembled before this message
    history = conversations.history_for_prompt(conversation_id)
    conversations.append_message(conversation_id, "user", body.message)

    events: queue.Queue = queue.Queue()

    def worker() -> None:
        try:
            result = run_agent(body.message, identity["employee_no"],
                               on_event=events.put, history=history)
            conversations.append_message(conversation_id, "assistant",
                                         result["answer"], trace=result["trace"])
        except Exception:
            events.put({"type": "error",
                        "reason": "agent or local model unavailable"})
        finally:
            events.put(None)   # sentinel: stream ends

    threading.Thread(target=worker, daemon=True).start()

    async def event_source():
        yield f"data: {json.dumps({'type': 'conversation', 'conversation_id': str(conversation_id)})}\n\n"
        while True:
            event = await asyncio.to_thread(events.get)
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")


@app.get("/policy")
def policy_endpoint(request: Request) -> dict:
    """The knowledge base, readable: documents with their chunks.

    Same session requirement as /chat — who may read policy is a logged-in
    person; nothing here is employee-private, but the door stays consistent.
    """
    identity = auth.resolve(request.cookies.get(SESSION_COOKIE))
    if identity is None:
        raise HTTPException(status_code=401, detail="login required")

    with OrmSession(engine) as session:
        documents = []
        for doc in session.scalars(
            select(PolicyDocument).order_by(PolicyDocument.created_at)
        ):
            chunks = session.scalars(
                select(PolicyChunk)
                .where(PolicyChunk.document_id == doc.id)
                .order_by(PolicyChunk.chunk_id)
            ).all()
            documents.append({
                "title": doc.title,
                "source_type": doc.source_type,
                "version": doc.version,
                "authority": doc.authority,
                "effective_from": doc.effective_from.isoformat() if doc.effective_from else None,
                "effective_to": doc.effective_to.isoformat() if doc.effective_to else None,
                "source_url": doc.source_url,
                "chunk_count": len(chunks),
                "chunks": [
                    {
                        "chunk_id": c.chunk_id,
                        "topic": c.topic,
                        "subtopic": c.subtopic,
                        "section": c.section,
                        "authority": c.authority,
                        "jurisdiction": c.jurisdiction,
                        "text": c.text,
                        # the coordinates — the 1024 numbers BGE-M3 produced
                        # from this text (rounded for display; the DB keeps
                        # full precision)
                        "embedding": [round(float(x), 5) for x in c.embedding]
                        if c.embedding is not None else None,
                    }
                    for c in chunks
                ],
            })
    return {"documents": documents}


@app.get("/conversations")
def conversations_endpoint(request: Request) -> dict:
    """This employee's recent conversations (for the chat switcher)."""
    identity = auth.resolve(request.cookies.get(SESSION_COOKIE))
    if identity is None:
        raise HTTPException(status_code=401, detail="login required")
    return {"conversations": conversations.list_conversations(identity["employee_no"])}


@app.get("/conversations/{conversation_id}/messages")
def conversation_messages_endpoint(request: Request, conversation_id: str) -> dict:
    """Full transcript of one conversation — 404 unless it belongs to you."""
    identity = auth.resolve(request.cookies.get(SESSION_COOKIE))
    if identity is None:
        raise HTTPException(status_code=401, detail="login required")
    messages = conversations.messages_of(conversation_id, identity["employee_no"])
    if messages is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"conversation_id": conversation_id, "messages": messages}
