"""WorkRight backend entry point.

The API surface:
  GET  /health  — liveness + database layers
  POST /chat    — the agent's front door (question in, answer + trace out)
"""

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import text

from .agent import run_agent
from .database import engine

app = FastAPI(title="WorkRight backend")


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


class ChatRequest(BaseModel):
    message: str
    employee_no: str  # who is talking (e.g. WR-0002)


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    """One question in, one answer out — through the full agent loop.

    TRUST NOTE (V1 placeholder): there is no login yet, so employee_no is
    taken at face value. All respect for the caller happens inside the tools
    (permission checks, session injection) — a real deployment replaces this
    line with authentication; the agent itself does not change.

    NOTE: the loop takes seconds (2–4 local LLM calls); `def` (not async)
    keeps FastAPI serving other requests meanwhile.
    """
    try:
        return run_agent(request.message, request.employee_no)
    except Exception:
        return {"status": "error",
                "reason": "agent or local model unavailable — try again"}
