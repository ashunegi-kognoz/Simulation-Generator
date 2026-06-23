# The Allocation Room Platform

Role-authentic executive decision simulations. Leaders distribute **exactly 100 units**
across four options per decision; the platform measures *how* they allocate attention,
capital, and risk, then returns a deterministic **posture fingerprint** and a grounded
**debrief**.

The whole platform runs **end-to-end offline** with a built-in mock LLM provider — no API
key required. Switching to OpenAI is a configuration-only change.

---

## What it measures

Each decision carries one visible **dimension** — the kind of call being made:

- **MOVE** — commit resources / act
- **HOLD** — preserve optionality / wait
- **FRAME** — define the problem / set terms

Behind every decision sit four hidden **postures** — orthogonal stances, one per option:

- **Protect** · **Enable** · **Hybrid** · **Defer**

Participants never see postures. They see four options labelled **A–D** (shuffled per
session) and split 100 units across them. Only at debrief are the postures revealed, as a
fingerprint (posture mix, decisiveness, consistency, dimension sensitivity, reliability).

---

## Architecture

```
Authoring (facilitator)        Generation (async)              Runtime (participant)
─────────────────────         ────────────────────            ─────────────────────
SimulationInput  ─POST─▶  Job queue ─▶ in-process worker  ─▶  SimulationVersion + Decisions
                                  │  Foundation → Fan-out → Reduce        │
                                  │  forge → critic → revise (≤2)         │
                                  ▼                                       ▼
                          posture-tagged decisions            Session: options shuffled A–D,
                          (+ [REVIEW] flags)                   postures stripped
                                                                      │ 100-unit allocations
                                                                      ▼
                                                       letters → postures → score → debrief
```

- **Pipeline (Part 2)** — `app/pipeline/*`: a Foundation → Fan-out → Reduce graph with a
  forge/critic/revise loop (capped at 2 revisions, then a `[REVIEW]` flag), a balance gate,
  and a mock provider for offline runs.
- **Job runner (Part 3)** — `app/jobs/*`: an in-process async worker. Queued jobs are claimed
  with `SELECT … FOR UPDATE SKIP LOCKED` on PostgreSQL (a guarded update on SQLite), generated
  through a DB-backed checkpointer (job-level resume), and persisted.
- **Services (Part 3)** — `app/services/*`: intake/lifecycle, the render shuffle and
  letter→posture resolution, scoring, and debrief.
- **API (Part 3)** — `app/api/*`: authoring, participant runtime, and group routers. Every
  request is tenant-scoped via `X-Tenant-Id`; creation is idempotent via `Idempotency-Key`.
- **Frontend (Part 4)** — `frontend/`: a React + Vite + TypeScript + Tailwind app with three
  workspaces (Author, Run, Group) built around the 100-unit allocation instrument.

---

## Tech stack

Python 3.11+ · FastAPI · Pydantic v2 · SQLAlchemy 2 (async) + Alembic · PostgreSQL 15
(JSONB) in production, SQLite for offline/dev · OpenAI Responses API (optional) · pytest.
Frontend: React 18 · Vite 5 · TypeScript 5 · Tailwind 3 · Recharts · Vitest.

---

## Project structure

```
allocation-room/
├── app/
│   ├── api/            # FastAPI routers: authoring, runtime, groups (+ deps, schemas)
│   ├── jobs/           # async job runner, DB checkpointer, checkpoint codec
│   ├── services/       # generation, session (render shuffle), scoring, debrief
│   ├── pipeline/       # Foundation → Fan-out → Reduce generation graph (Part 2)
│   ├── scoring/        # deterministic fingerprint + group analytics (Part 2)
│   ├── debrief/        # debrief writer (Part 2)
│   ├── llm/            # provider interface, mock + openai providers, concurrency
│   ├── prompts/        # verbatim prompt templates
│   ├── safety/         # PII redaction + injection screening
│   ├── schemas/        # Pydantic contracts (input, content, runtime, scoring, …)
│   ├── models/         # SQLAlchemy ORM (18 tables) + portable JSONB/UUID types
│   ├── config.py       # pydantic-settings (env-driven; nothing hardcoded)
│   ├── db.py           # async engine/session factory
│   └── main.py         # app factory: routers, CORS, rate limit, error handlers, worker
├── frontend/
│   └── src/
│       ├── api/        # typed client + server schema mirrors
│       ├── components/ # AllocationMeter (signature), charts, UI atoms, control bar
│       ├── lib/        # 100-unit allocation helpers (+ tests)
│       └── pages/      # AuthoringConsole, ParticipantRuntime, GroupRoom
├── alembic/            # migration (create_all-based; works on Postgres and SQLite)
├── scripts/            # init_db, create_tenant helpers
├── tests/              # pytest suite (schemas, pipeline, scoring, gates, API)
├── pyproject.toml
└── .env.example
```

---

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm (for the frontend)
- PostgreSQL 15 for production (optional for local: SQLite works offline)

---

## Backend — setup & run (offline, mock provider)

```bash
# 1. install
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. configure (offline SQLite + mock provider)
cp .env.example .env
# then edit .env:
#   DATABASE_URL=sqlite+aiosqlite:///./allocation_room.sqlite
#   LLM_PROVIDER=mock

# 3. create the schema
alembic upgrade head            # Postgres or SQLite (migration uses create_all)
# (quick alternative for a throwaway SQLite db: `python -m scripts.init_db`)

# 4. provision a tenant — copy the printed UUID
python -m scripts.create_tenant "Acme Corp"

# 5. run the API
uvicorn app.main:app --reload   # http://localhost:8000  (docs at /docs)
```

**Generating a simulation over HTTP.** Generation runs in a background worker in normal
operation. For local/dev you can also drain the queue synchronously with
`POST /simulations/{id}/run` (used by the frontend's "Create and generate").

For **production with PostgreSQL**, set
`DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/allocation_room`, run
`alembic upgrade head`, and the background worker drains jobs automatically.

### Switch to OpenAI

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
LLM_MODEL_STRONG=<your strongest Responses-API model>
LLM_MODEL_MID=<a faster Responses-API model>
```

No code changes — the provider is selected entirely from config.

---

## Frontend — setup & run

```bash
cd frontend
npm install

cp .env.example .env.local
# set the tenant from step 4 above:
#   VITE_TENANT_ID=<the printed tenant UUID>
#   VITE_API_BASE_URL=/api           # dev proxy → http://localhost:8000
#   VITE_API_BACKEND=http://localhost:8000

npm run dev        # http://localhost:5173  (proxies /api to the backend)
npm run build      # typechecks then builds to dist/
npm run test       # vitest unit tests
```

The dev server proxies `/api` to the backend, so the browser makes same-origin requests in
development. In production, serve `dist/` and set `VITE_API_BASE_URL` to the API's origin
(the backend already sends CORS headers for the configured origins).

**Walkthrough:** Author → fill the pre-populated form → *Create and generate* → switch to
Run → *Open session* (participant `p1`) → distribute 100 units per decision → *Submit* →
*Generate debrief*. The Group workspace reconciles a team allocation (the team UUID comes
from a group round) and shows group analytics.

---

## API reference

All endpoints require the `X-Tenant-Id: <uuid>` header. `POST /simulations` also honors an
optional `Idempotency-Key`.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/simulations` | Create a simulation + queue generation (idempotent) → `202` |
| `GET` | `/simulations/{id}` | Simulation summary (tenant-scoped) |
| `GET` | `/simulations/{id}/status` | Status, job state, flagged count |
| `GET` | `/simulations/{id}/review` | List `[REVIEW]`-flagged decisions |
| `POST` | `/simulations/{id}/review` | Approve / reject flagged content |
| `POST` | `/simulations/{id}/run` | Dev/admin: drain queued jobs synchronously |
| `POST` | `/sessions` | Open a participant session |
| `GET` | `/sessions/{id}` | Posture-stripped decisions (options A–D only) |
| `POST` | `/sessions/{id}/allocations` | Submit 100-unit allocations (letters → postures) |
| `POST` | `/sessions/{id}/reflections` | Capture a reflection |
| `POST` | `/sessions/{id}/commitments` | Capture a commitment |
| `GET` | `/sessions/{id}/debrief` | Posture fingerprint + written debrief |
| `POST` | `/teams/{id}/reconcile` | Reconcile a team allocation → group analytics |
| `GET` | `/teams/{id}/analytics` | Stored group analytics |
| `GET` | `/health` | Liveness + active provider |

---

## Validation checks (invariants the system enforces)

- **Exactly 100 units.** Every allocation must sum to 100 across the four postures, each in
  0..100; the participant UI disables submit until each decision balances, and the server
  re-validates (`422` otherwise).
- **Posture concealment.** `GET /sessions/{id}` returns options as letters with neutral
  `Option A` labels — no `posture` field and no posture-revealing labels ever reach the
  participant. The letter→posture map is recomputed server-side from the session seed.
- **Tenant isolation.** Reading another tenant's simulation/session returns `404` (existence
  is not leaked).
- **Idempotent creation.** A repeated `POST /simulations` with the same `Idempotency-Key`
  returns the original simulation rather than creating a duplicate.
- **Input caps.** Participants ≤ 20, teams ≤ 5, team size 2–4, decisions per round 1–6, and
  rounds ≤ `MAX_ROUNDS` (default 6).
- **CORS + rate limiting.** Browser origins are restricted to `CORS_ALLOW_ORIGINS`; a
  per-client fixed-window limit (`RATE_LIMIT_PER_MINUTE`) returns `429` when exceeded
  (disabled under `APP_ENV=test`).
- **Errors never leak internals.** Service errors map to `404`/`409`/`422`; anything
  unexpected returns a generic `500`.

---

## Testing

```bash
# backend — 33 tests (schemas, pipeline, scoring, gates, full offline API flow)
python -m pytest -q

# frontend — allocation unit tests
cd frontend && npm run test
```

The backend suite runs fully offline against SQLite with the mock provider. `tests/test_api.py`
drives the complete flow end-to-end: create → idempotent re-create → run job → open session →
assert posture-stripping → submit letter allocations → verify letter→posture resolution in
storage → fingerprint + debrief → tenant isolation.

### Basic test cases covered

- Allocation that doesn't sum to 100 is rejected (`422`).
- Rendered options expose no posture and use neutral labels.
- Submitted letters resolve to the correct postures (deterministic per session seed).
- Posture fingerprint is computed and persisted (`n_decisions`, indices, reliability).
- Debrief cites only decisions the participant actually saw.
- Cross-tenant reads return `404`; duplicate creates are idempotent.
- Frontend: empty/over/balanced budget states and 0..100 clamping (Vitest).

---

## Configuration

Key environment variables (see `.env.example` for the full list):

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | Postgres DSN | Use `sqlite+aiosqlite:///./db.sqlite` for offline/dev |
| `APP_ENV` | `local` | `test` disables the worker + rate limiter |
| `LLM_PROVIDER` | `mock` | `mock` or `openai` |
| `MAX_CONCURRENCY` | `12` | LLM call fan-out limit |
| `MAX_REVISIONS` | `2` | Critic/revise cap before `[REVIEW]` |
| `MAX_ROUNDS` | `6` | Round-count input cap |
| `CORS_ALLOW_ORIGINS` | `localhost:5173,4173` | Comma-separated browser origins |
| `RATE_LIMIT_PER_MINUTE` | `120` | Per-client request cap |

Frontend: `VITE_API_BASE_URL`, `VITE_API_BACKEND`, `VITE_TENANT_ID`.

---

## Limitations & assumptions

- **Offline DB is SQLite; production is PostgreSQL.** ORM columns use portable types that map
  to real `JSONB`/`UUID` on PostgreSQL and to `JSON`/`CHAR(36)` on SQLite. `SELECT … FOR
  UPDATE SKIP LOCKED` is PostgreSQL-only; on SQLite the job claim degrades to a guarded update
  (single-worker dev).
- **Checkpoint resume is job-level.** Completed nodes from a prior run are skipped on restart;
  finer-grained mid-run persistence is a future enhancement (the checkpointer Protocol is
  synchronous by design).
- **No team-listing endpoint.** The Group workspace takes a team UUID directly; team IDs are
  created during a group round. A `GET /teams` listing is a natural follow-up.
- **Single-worker rate limiter.** The in-process limiter bounds one worker; multi-worker
  deployments should front it with a shared limiter.
- **Mock provider is deterministic** and seeded for reproducible offline runs; it is for
  development and tests, not production content.
- **Tenancy is provisioned out of band** via `scripts/create_tenant.py` (no public
  tenant-creation endpoint).

---

## Build status

- Backend: **33 passing tests** (offline, SQLite + mock provider).
- Frontend: typechecks, production build succeeds, **5 passing unit tests**.
- Live integration smoke (CORS preflight, full mock flow, posture-leak check, tenant
  isolation, rate limiting) passes.
