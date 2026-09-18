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
from sqlalchemy import text

from . import auth
from .agent import run_agent
from .database import engine

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
    # NOTE: no employee_no — identity comes from the session cookie ONLY.
    # The old body-supplied identity was a documented V1 placeholder; the
    # sessions table replaced it. The agent and its tools are unchanged.


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
    try:
        return run_agent(body.message, identity["employee_no"])
    except Exception:
        return {"status": "error",
                "reason": "agent or local model unavailable — try again"}


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

    events: queue.Queue = queue.Queue()

    def worker() -> None:
        try:
            run_agent(body.message, identity["employee_no"],
                      on_event=events.put)
        except Exception:
            events.put({"type": "error",
                        "reason": "agent or local model unavailable"})
        finally:
            events.put(None)   # sentinel: stream ends

    threading.Thread(target=worker, daemon=True).start()

    async def event_source():
        while True:
            event = await asyncio.to_thread(events.get)
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
