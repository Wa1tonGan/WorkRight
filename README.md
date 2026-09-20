# WorkRight

A local AI agent for Malaysian HR — leave and flexible working arrangements,
with every calculation, permission, and approval enforced by backend code and
every answer grounded in the company's own documents.

Everything runs on your machine: the LLM (Qwen3 via Ollama), the embeddings
(BGE-M3), and the database (PostgreSQL + pgvector). No paid APIs.

> Educational prototype with fictional employees and policies. Not an
> official government service and not legal advice.

## What it can do

- **Answer questions** from employees: leave balances, entitlements, policy
  details, with citations to the exact policy chunk (`HB-004 §4.1`, `LAW-003 s.60E`).
- **Book leave** — annual, sick, and hospitalisation kept as separate legal
  categories, half-days supported, duplicates blocked by a database index.
- **File flexible-working requests** (hours / days / place) with both deadline
  clocks computed at submission (30-day company target, 60-day statutory).
- **Route approvals** — managers decide for their direct reports; HR finalizes
  the second stage of FWA and handles sick/hospitalisation. The agent can
  never approve anything itself.
- **Enforce access control** — employees see their own data, managers their
  reports', HR everything. Enforced in code, not in prompts.
- **Escalate honestly** — Sabah/Sarawak, part-time, and unsupported cases are
  referred to HR instead of being answered with the wrong law.
- **Keep audit trails** — every decision records who, when, and why; every
  conversation is stored with the tool calls that produced it.

## Architecture

```
browser (React + Vite, :5173)
   │  session cookie
   ▼
FastAPI (:8000) ── /auth /chat /chat/stream /requests /pending /policy
   │
   ▼
agent loop (backend/agent.py)
   │  the model REQUESTS tools; only this code executes them
   ├── get_employee · annual_leave_entitlement · search_policy
   ├── submit_leave_request · submit_fwa_request
   ├── list_pending_requests · decide_request
   │
   ├──▶ PostgreSQL + pgvector — employees, requests, approvals,
   │                            policy chunks + embeddings, conversations
   └──▶ Ollama — qwen2.5:3b (chat) · bge-m3 (embeddings)
```

Design rule throughout: **facts come from the database, decisions from code,
sentences from the model.** The LLM interprets and speaks; it cannot compute
balances, cannot see data without a tool, and cannot approve anything.

## Quick start

Prerequisites: Python 3.12 + [uv](https://docs.astral.sh/uv/),
Node 18+, PostgreSQL 17 with pgvector, [Ollama](https://ollama.com).

```sh
# 1. backend dependencies + database schema
uv sync
createdb workright
psql -d workright -c "CREATE EXTENSION IF NOT EXISTS vector;"
uv run alembic upgrade head

# 2. seed the fictional company (7 employees) + demo login passwords
uv run python -c "import sys; sys.path.insert(0,'.'); from backend.seed import seed, set_demo_passwords; seed(); set_demo_passwords()"

# 3. models (once)
ollama pull qwen2.5:3b
ollama pull bge-m3

# 4. knowledge base: chunk + embed the policy documents
uv run python -m backend.load_chunks

# 5. run it
uv run uvicorn backend.main:app --port 8000        # terminal 1
cd frontend && npm install && npm run dev          # terminal 2
```

Open **http://localhost:5173** and sign in as anyone below
(password for all: `workright123`).

| Login | Who | Try |
| --- | --- | --- |
| `weijie.lim@example.my` | Wei Jie, employee | "how many leave days do I have left?" |
| `siti.yusof@example.my` | Siti, manager | "any pending requests?" → Approvals page |
| `ravi.kumar@example.my` | Ravi, HR | approve the HR stage of a WFH request |
| `jelin.ujin@example.my` | Jelin, Sabah | ask anything — watch it escalate |
| `danial.rahim@example.my` | Danial, new joiner | ask about a colleague's balance — refused |

## Adding a new policy

One command — the document is chunked on its own headings, embedded, and
searchable immediately:

```sh
uv run python -m backend.ingest_policy knowledge/company/my_policy.md \
    --title "Work From Home Equipment Policy" --version 1.0 \
    --effective-from 2026-09-01
```

Only the new chunks are embedded; existing documents are untouched. A policy
dated in the future is correctly invisible to search until it takes effect.

## Testing

```sh
uv run pytest backend/ -q          # 98 tests: tools, permissions, approvals,
                                   # balance deltas, conversations, access scoping
uv run python -m backend.evaluate_retrieval   # retrieval eval: 8 cases + MRR
```

`docs/UI_TEST_CASES.md` has 12 executable browser scenarios with expected
outcomes — including the refusal paths.

## Repository map

```text
backend/            FastAPI app, agent loop, tools, permissions, auth,
                    conversations, migrations support, tests
alembic/            8 migrations: employees → requests → approvals → FWA
                    → auth → conversations
frontend/           React + Vite + TypeScript UI (chat, requests, approvals,
                    policies)
knowledge/          the source policy documents (law corpus + handbook)
docs/               roadmap, V1 schema design, UI test cases, RAG guide
evals/              retrieval evaluation harness
```

## Working agreement

Built one phase at a time — explain, implement, verify together, record what
was learned. Current state and history live in
[docs/DEVELOPMENT_ROADMAP.md](docs/DEVELOPMENT_ROADMAP.md); the data model is
in [docs/FINAL_SCHEMA_V1.sql](docs/FINAL_SCHEMA_V1.sql).

## Known limitations

- Public holidays are not yet excluded from leave-day counting (weekends are).
- The legal corpus is a normalized summary pending verification against the
  official JTKSM text.
- Carry-forward of unused leave is policy-defined but not yet computed.
- One retrieval eval case (RAG-007, Sabah scope) currently misses `LAW-001`.
