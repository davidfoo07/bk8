# CourtEdge — NBA Polymarket edge finder

Personal tool. Rates every NBA game with lineup/injury-adjusted team ratings, turns that into
win / spread-cover / over probabilities, and compares them with Polymarket prices to flag edges
(STRONG BUY / BUY / LEAN / NO EDGE). The owner bets small amounts ($1) on Polymarket off these
signals, so a wrong STRONG BUY costs real money — be conservative and say plainly when a signal
is untrustworthy.

The owner is in Singapore (SGT, UTC+8); NBA games tip off ~7–11am SGT. Reply casually and briefly.

## Layout

```
bk8/                      ← git repo (github.com/davidfoo07/bk8, branch main)
  backend/                FastAPI, Python 3.12, SQLAlchemy async + Alembic, APScheduler
    app/main.py           app + scheduler start (pipeline every 5 min)
    app/config.py         settings (.env) + current_season(), sync_database_url()
    app/services/
      pipeline.py         THE core: schedule → ratings/injuries/Polymarket → model → edges
      prediction_store.py History: save/load/lock per day (daily_predictions table)
      market_store.py     market_snapshots table
      evaluation.py       model-vs-Polymarket Brier/log-loss (/results/evaluation)
      scheduler.py        background refresh jobs
    app/analytics/        prediction_model, edge_calculator, season_blend, roster_prior,
                          lineup_adjustment, schedule_engine
    app/connectors/       espn.py, nba_api.py (+ disk_cache.py), injuries.py (ESPN),
                          polymarket.py (Gamma API), pbpstats.py
    app/api/v1/           games.py, results.py, bets.py, simulation.py
    alembic/versions/     migrations (latest: d41a7c9e2b10 daily_predictions)
    tests/                pytest; fixtures/espn/ = recorded ESPN JSON
    data/cache/           NBA season-stats disk cache (gitignored)
  frontend/               Next.js 16 (non-standard — read frontend/AGENTS.md and
                          node_modules/next/dist/docs/ before frontend changes), React 19, Tailwind
    src/app/page.tsx      Dashboard (slate picker: today + 7 days ahead)
    src/app/history/      Prediction results vs actual
    src/app/bets/ simulation/ accuracy/
    src/components/GameCard.tsx, TopEdges.tsx
```

`courtedge/.claude/launch.json` (one level up) defines `backend` (:8000) and `frontend` (:3001)
for the preview tools.

## Run / test

```bash
# backend (venv already exists; created with: uv venv --python 3.12 venv)
cd backend && ./venv/bin/uvicorn app.main:app --reload --port 8000
# frontend — runs on 3001, not 3000
cd frontend && npm run dev
# tests (always a local throwaway DB, never Supabase)
cd backend && ./venv/bin/python -m pytest tests/ -q
cd frontend && npx tsc --noEmit && npx eslint src/
# migrations — URL comes from DATABASE_URL
cd backend && ./venv/bin/alembic upgrade head
```

- The backend reads `.env` only at startup: restart it after editing `.env`.
- Lint: ruff/eslint have many pre-existing warnings. Keep **changed lines** clean; don't
  mass-fix unrelated files.

## Data sources

| What | Source | Notes |
|---|---|---|
| Schedule, live score/clock, box score, final scores | **ESPN** site API | primary; NBA scoreboard is fallback only |
| Injuries | ESPN | lags trades — injuries are re-mapped to current rosters |
| Team ratings, player impact (E_NET etc.), rosters, standings | stats.nba.com | **blocks this IP (403) under load.** Disk-cached 3–12h; on failure serves the last cached copy (STALE). After a 403 all NBA calls pause 15 min. |
| Prices | Polymarket Gamma API | moneyline = `sportsMarketType == "moneyline"`; spread = **main line** (earliest-created), not the smallest |

**Never hammer stats.nba.com** (no loops over seasons/teams/dates in ad-hoc scripts, no tight
polling). Prefer the disk cache and ESPN.

## Database

- Production data: **Supabase** Postgres (Mumbai, `aws-0-ap-south-1`) via the **Session
  pooler** URL in `backend/.env` as `postgresql+asyncpg://...:5432/postgres?ssl=require`.
  Direct connection is IPv6-only (unreachable here); transaction pooler breaks asyncpg.
- Never print, echo or commit the password; inspect `.env` only with the password masked.
- Free tier pauses after ~1 week idle → user must click Restore in the Supabase dashboard.
- Local Docker Postgres `courtedge-postgres` on **:5433** (volume `courtedge-pgdata`): old
  backup + home of `courtedge_test`. Port 5432 locally belongs to another project
  (`hl-postgres`) — don't touch it.
- Tables in use: `bets`, `market_snapshots`, `daily_predictions` (History). Others are unused.
- `tests/conftest.py` forces a local test DB and refuses non-local hosts.

## Model in one paragraph

Season is date-derived (`current_season()`; rolls over in October). Team ORtg/DRtg = current
season blended with a prior by games played (`w = gp/(gp+15)`). The prior is **roster-based**:
current roster rated on last season's player impact (2024-25 at half weight for players who
missed last season), regressed 0.6 toward league average. Injuries subtract player impact
(relative to the team the stats were earned on, shrunk for small samples). NRtg diff + home
court (3.0) + schedule → margin. One normal margin distribution (σ=13, backtested on 2025-26
as-of-date projections) gives win prob, spread cover and the live model — keep them on the same
σ. Total: league scoring baseline that adapts fast early season, σ=19.

## Rules the app enforces (don't break these)

- **Slate date** rolls over at **6am US Eastern** (6pm SGT), America/New_York tz — late games stay
  on the dashboard until finished.
- **History** saves only the *current* slate, merges re-runs, and **locks each game at tip-off**;
  games first seen after tip-off are never saved (no hindsight). Upcoming days viewed via the
  slate picker are not saved. Injury-toggle what-ifs are never saved.
- History only exists for days the backend was running before tip-off (scheduler saves every
  5 min). A day missed is gone — don't backfill it into History.
- **Verdict caps → LEAN**: game in progress (edges use the score+clock live model), stale roster
  prior, or |model − market| > 0.15 (`market_disagreement_threshold`; Kelly then uses a 50/50
  model/market blend). Polymarket prices ≤2¢/≥98¢ = SETTLED.
- `tipoff_sgt` must be the same instant in Asia/Singapore (not UTC + 8h).
- Validation (`services/validation.py`): ORtg/DRtg 90–130, NRtg ±25, prices 0.01–0.99, minutes
  0–48; out-of-range data falls back rather than flowing into the model. External fetches need
  timeout + retry + graceful fallback.

## Where things stand (Oct 2026, start of 2026-27 season)

- History: Oct 22 (good), Oct 23 (saved early with the *old* model — ignore for accuracy),
  Oct 24–26 missing (app was off). Real tracking starts Oct 27. The app now runs detached
  (`caffeinate -dis npm run dev`, log in `courtedge/courtedge.log`), not via the preview panel,
  which stops when the Claude app closes.
- Model vs Market evaluation needs 100+ graded games before it means anything.
- Known open issues: LAC@LAL and MIA@CHA style large disagreements not fully explained (guard
  catches them); several STRONG BUYs sit just under the 0.15 guard. Whether verdicts should use a
  market-blended probability can't be tested yet, and closing-line value can't be measured —
  both need stored Polymarket price history.
- Hosting: none. No VPS (deploy workflow removed), no CI by choice — don't add CI. Runs on
  the owner's Mac; it must stay awake overnight for History to record games.

## Working with the owner

- Commit/push only when asked; they usually say "commit and push". Commit on `main` is fine
  (solo repo); use clear conventional messages; never commit `.env`.
- Git identity for this repo is set locally (David Foo). GitHub CLI may be logged in as
  `davidfoo07-ola`, which lacks access to `davidfoo07/bk8` — pushes use the `davidfoo07` login.
- Verify changes against the running app (curl the API, check the dashboard), not just tests.
- Results from a handful of games are noise; don't tune the model on them.
