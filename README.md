# WorkRight

A local AI-agent learning project for Malaysian HR leave and flexible working arrangements.

We will build WorkRight one phase at a time, explaining each component and reviewing its behaviour before moving on. The repository currently contains planning documents, a project-local Python 3.12 virtual environment with FastAPI and Uvicorn installed, and a first backend step: `backend/main.py` with a `GET /health` endpoint. No database or models have been installed by this project setup.

## Project direction

- Run the answering LLM and embedding model locally, without paid AI APIs.
- Use a single agent with a manually implemented tool-calling loop.
- Store employee records, requests, saved case state, and policy vectors in one PostgreSQL database with pgvector.
- Use fictional employees and company policies alongside verified public legal sources.
- Keep calculations, permissions, and approvals enforced by backend code.
- Learn RAG through small, inspectable exercises before integrating it into the full application.

The intended V1 scope is private-sector employment in Peninsular Malaysia and Labuan, covering annual leave, sick and hospitalisation leave, and flexible working arrangements. Unsupported cases will be referred to HR. WorkRight is an educational prototype, not an official government service or legal advice.

## Proposed stack

| Part | Choice |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| Backend | Python, FastAPI, Pydantic |
| Local model runner | Ollama, running directly on macOS |
| Agent LLM | Qwen3 8B, initial evaluation candidate |
| Embeddings | BGE-M3, initial evaluation candidate |
| Model integration | Ollama Python library |
| Database | PostgreSQL with pgvector |
| Database access and migrations | SQLAlchemy and Alembic |
| Testing | pytest and a small agent/retrieval evaluation dataset |
| Dependency management | uv for Python, npm for frontend |
| Database runtime | Native PostgreSQL planned; OrbStack and Docker deferred |

Model choices will be tested on the development Mac and on English/Malay WorkRight examples. Docker is optional. No paid inference provider is required by the planned architecture.

## Repository map

```text
WorkRight/
├── README.md
├── .gitignore
├── .python-version
├── pyproject.toml           # Project details and direct dependencies
├── uv.lock                  # Exact resolved dependency versions
├── docs/
│   ├── DEVELOPMENT_ROADMAP.md
│   ├── RAG_LEARNING_GUIDE.md
│   └── ORIGINAL_PROPOSAL.md
├── backend/                 # Python application (first endpoint: backend/main.py)
├── frontend/                # Future React interface
├── knowledge/
│   ├── law/                # Future verified public legal sources
│   └── company/            # Future fictional company policies
└── evals/                   # Future retrieval and agent evaluation cases
```

Empty folders contain `.gitkeep` placeholders so Git can track the structure. These are not application files.

## Reading order

1. [Development roadmap](docs/DEVELOPMENT_ROADMAP.md): phases, learning checkpoints, and current progress.
2. [RAG learning guide](docs/RAG_LEARNING_GUIDE.md): embeddings, pgvector, tuning, evaluation, and Docker choices.
3. [Original proposal](docs/ORIGINAL_PROPOSAL.md): an unchanged copy of the supplied project brief for reference.

The original proposal recommends OpenAI APIs. Our agreed direction has since changed to local Ollama models and embeddings, as recorded here and in the roadmap. Suggestions in the original proposal do not authorize installing or implementing anything automatically.

## How we will work

For each phase, explain the goal and relevant concepts, implement a small step when the user is ready, inspect the result together, and record what was learned. Keep the implementation paced for learning rather than completing later phases in advance.

The environment inventory is complete. A project-local `.venv` has been created with the existing Python 3.12.14 installation, and `.python-version` records the project's Python 3.12 preference. FastAPI and Uvicorn are installed, recorded in `pyproject.toml`, and resolved in `uv.lock`. OrbStack and Docker are deferred. The first health endpoint is implemented and verified (`GET /health` returns `{"status":"ok"}`); the next learning step is the PostgreSQL decision and database connection.

## Using the Python environment

From this repository folder, activate the environment in your terminal:

```sh
source .venv/bin/activate
python --version
```

Activation makes this environment's Python the default for that terminal session. Other terminals and projects are unaffected. Leaving the project folder does not automatically deactivate it; run `deactivate` when finished.

You can also use the environment without activation:

```sh
.venv/bin/python --version
```

The environment keeps project packages separate from global Python packages. It uses the existing base Python installation and is not a security sandbox. The `.venv/` directory is ignored by Git; `.python-version`, `pyproject.toml`, and `uv.lock` are intended to be versioned.

## Understanding dependencies

- `pyproject.toml` declares the project's metadata, supported Python versions, and direct dependencies. FastAPI defines API endpoints; Uvicorn runs the server that receives requests.
- `uv.lock` records exact resolved versions, including supporting dependencies such as Pydantic and Starlette.
- `.venv/` contains the packages actually installed for this project.

We added the initial dependencies with `uv add fastapi uvicorn`. To recreate the environment from the checked-in lockfile, use:

```sh
uv sync --locked
```

This checks that the lockfile agrees with the project declaration and installs the required packages into the project environment. Downloads may be needed on a fresh machine. A separate manually maintained `requirements.txt` is unnecessary for this workflow.
