# CourtEdge — NBA Polymarket Analytics Platform

## Project Overview
Lineup-adjusted NBA ratings engine + Polymarket edge calculator.
Python/FastAPI backend, Next.js frontend, PostgreSQL database.

## Architecture
- `/backend` — Python 3.11+, FastAPI, SQLAlchemy, APScheduler
- `/frontend` — Next.js 14+, React, Tailwind CSS, Recharts
- `/shared` — TypeScript types shared between frontend and API docs
- Database: PostgreSQL (Railway or local Docker)

## Commands
- Backend: `cd backend && uvicorn app.main:app --reload`
- Frontend: `cd frontend && npm run dev`
- Tests (backend): `cd backend && pytest -v`
- Tests (frontend): `cd frontend && npm test`
- Lint: `cd backend && ruff check .` / `cd frontend && npm run lint`
- Type check: `cd backend && mypy app/` / `cd frontend && npx tsc --noEmit`

## Code Standards
- Python: Use type hints everywhere. Use Pydantic models for all data structures. Follow PEP 8 via ruff.
- TypeScript: Strict mode. No `any` types. Use Zod for runtime validation.
- All functions that fetch external data must have error handling, retry logic, and timeout.
- All data entering the system must pass through the validation layer.
- Every module must have unit tests. Data connectors must have integration tests with mock responses.

## Data Validation Rules
- ORtg/DRtg: 90-130 range. Flag and fall back if outside.
- NRtg: -25 to +25 range.
- Polymarket prices: 0.01-0.99 range.
- Player minutes: 0-48 range.
- Cross-source tolerance: ORtg/DRtg within 2.0, NRtg within 3.0.
- Always log validation failures to the validation_log table.

## When Compacting
Always preserve:
- The full list of modified files
- Any test commands and their results
- The current implementation plan and which milestone we're on
- Error messages that haven't been resolved
- Database schema changes
