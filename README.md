# VoxPath

A chat assistant for India that answers from live data instead of model memory:
Indian news (including Bihar and Uttar Pradesh regional sources), NSE/BSE stock
and index prices, and Indian Railways lookups (PNR, live status, schedules,
availability, fares). It also remembers facts each user asks it to keep.

- **Backend** (`backend/`): FastAPI + a LangGraph ReAct agent on OpenAI. Tools
  live in one FastMCP registry (`mcp_server.py`) that the agent calls in-process.
  Conversations and long-term memory persist in Postgres (pgvector).
- **Frontend** (`frontend/`): Next.js chat UI with email/password sign-in.

> `docs/TECHNICAL_DOCUMENTATION.md` and `docs/VISUAL_OVERVIEW.md` describe an
> earlier Vertex AI / Gemini version and are out of date. This README is current.

## Prerequisites

- Python 3.11
- Node.js 20.9+ (Next.js 16)
- Postgres 14+ with the [pgvector](https://github.com/pgvector/pgvector) extension installed
- API keys: OpenAI and [IRCTC on RapidAPI](https://rapidapi.com/) (host `irctc-api2.p.rapidapi.com`)

## Setup

### 1. Database

Create a database and a role for the app:

```sql
CREATE ROLE voxpath LOGIN PASSWORD 'change-me';
CREATE DATABASE voxpath OWNER voxpath;
\c voxpath
CREATE EXTENSION IF NOT EXISTS vector;   -- as a superuser, if the app role can't
```

The app creates its own tables on first start (LangGraph checkpoint and store
tables, `users`, `threads`). There are no migrations to run.

### 2. Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env      # then fill in the values
```

See [`backend/.env.example`](backend/.env.example) for every setting. Four are required:
`OPENAI_API_KEY`, `JWT_SECRET`, `RAPIDAPI_KEY` and `DATABASE_URL`.

On macOS/Linux use `.venv/bin/python` and `cp` instead.

### 3. Frontend

```powershell
cd frontend
npm install
```

The frontend calls the backend at `http://127.0.0.1:8000`. To change that, set
`NEXT_PUBLIC_API_BASE` in `frontend/.env.local`.

## Running

From the repo root, start both together:

```powershell
npm install        # once, for `concurrently`
npm run dev
```

Or run them separately:

```powershell
cd backend;  .venv\Scripts\python.exe main.py     # http://127.0.0.1:8000
cd frontend; npm run dev                           # http://localhost:3000
```

Start the backend with `python main.py`, **not** `uvicorn main:app`. On Windows,
uvicorn picks an event loop the async Postgres driver cannot use, and startup
fails with a `ProactorEventLoop` error. `main.py` picks a compatible loop.

Open http://localhost:3000, create an account, and start chatting.

## API

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /auth/register`, `POST /auth/login` | none | Returns a bearer token |
| `GET /auth/me` | bearer | The signed-in user |
| `POST /chat` | bearer | `{"message", "thread_id"}` → `{"text"}` |
| `/mcp` | bearer | The tool registry over MCP HTTP, for external MCP clients |
| `GET /health`, `GET /news/status` | none | Liveness and news-refresher status |

## Tests

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q test_backend.py test_units_fast.py
```

The tests mock OpenAI, RapidAPI and Postgres, so they need no keys or database.
CI (`.github/workflows/ci.yml`) runs them, plus frontend lint and type checks,
on every pull request.
