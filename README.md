# CourtEdge

**Lineup-adjusted NBA analytics platform for Polymarket edge detection.**

CourtEdge replaces stale team-level NBA stats with real-time lineup-adjusted ratings. It calculates the true impact of missing players using on/off splits, then compares model probabilities against Polymarket prices to surface mispriced bets with expected value.

---

## Quick Start

```bash
git clone https://github.com/davidfoo07/bk8.git
cd bk8

# Backend setup
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cd ..

# Frontend setup
cd frontend && npm install && cd ..

# Install root dev tools
npm install

# Run both (backend + frontend in one terminal)
npm run dev
```

Open **http://localhost:3000** — live dashboard with today's games, Polymarket edges, and model predictions.

---

## Commands

Run from the project root:

| Command | What it does |
|---|---|
| `npm run dev` | Start backend (port 8000) + frontend (port 3000) together |
| `npm run dev:backend` | Backend only with hot reload |
| `npm run dev:frontend` | Frontend only |
| `npm run test` | Run all 68+ backend tests |
| `npm run test:quick` | Run tests, stop on first failure |
| `npm run build` | Build frontend for production |

---

## Why CourtEdge

Polymarket NBA lines move slowly compared to sportsbooks. When a star player is ruled out 90 minutes before tipoff, the market often lags 10-20 minutes. CourtEdge pre-calculates the adjusted ratings for every plausible injury scenario, so you can see the true edge the moment news breaks.

**Core workflow:**
1. Pull team ratings from NBA API (estimated metrics + standings fallback)
2. Pull tonight's injury report
3. Adjust each team's ORtg / DRtg / NRtg based on who's actually playing
4. Convert adjusted ratings to win probability, spread, and total
5. Compare model probability vs Polymarket price → edge + Kelly sizing
6. Display verdicts: **STRONG BUY** / **BUY** / **LEAN** / **NO EDGE**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js 15)                    │
│  Dashboard ─ Game Cards ─ Bet Tracker ─ Model Accuracy          │
│  Port 3000 │ React 19 │ Tailwind v4 │ TypeScript strict         │
└─────────────────────────┬───────────────────────────────────────┘
                          │ REST (JSON)
┌─────────────────────────▼───────────────────────────────────────┐
│                       Backend (FastAPI)                          │
│  /api/v1/games/today ─ /bets ─ /teams ─ /injuries               │
│  Port 8000 │ Python 3.12 │ async/await │ Pydantic v2             │
├─────────────────────────────────────────────────────────────────┤
│  Live Data Pipeline (app/services/pipeline.py)                   │
│  scoreboardv3 → ratings + injuries + Polymarket (parallel)       │
│  → lineup adjustment → prediction model → edge calculator        │
│  → GameAnalysis assembly → 5min TTL cache                        │
├─────────────────────────────────────────────────────────────────┤
│  Analytics Engine                                                │
│  ├── Lineup Adjustment (OnOffSplitModel, diminishing returns)    │
│  ├── Prediction Model (NRtg → logistic win prob, scipy norm)     │
│  ├── Edge Calculator (EV, Kelly criterion, verdicts)             │
│  └── Schedule Engine (B2B, rest, travel, motivation)             │
├─────────────────────────────────────────────────────────────────┤
│  Data Connectors                    │  Validation Layer (4 tiers)│
│  ├── NBA API (stats.nba.com)        │  ├── Range/sanity checks   │
│  ├── PBP Stats (pbpstats.com)       │  ├── Cross-source verify   │
│  ├── Polymarket Gamma API           │  ├── Staleness detection    │
│  └── Injury Feed (NBA CDN)          │  └── Anomaly detection      │
├─────────────────────────────────────────────────────────────────┤
│  PostgreSQL (SQLAlchemy + Alembic) │ In-memory TTL cache          │
└─────────────────────────────────────────────────────────────────┘
```

### Live Pipeline Data Flow

```
NBA scoreboardv3 ──→ today's games (7 games)
        │
        ├── standings (30 teams, W/L/seed)  ←── fetched first
        │
        ├── team ratings ←── fallback chain:
        │     1. leaguedashteamstats Advanced (often 500)
        │     2. leaguedashteamstats Base (often 500)
        │     3. teamestimatedmetrics ← THIS WORKS
        │     4. standings estimation: NRtg = (WinPCT - 0.5) × 28
        │
        ├── injuries (NBA official API)
        │
        └── Polymarket markets (51K+ scanned, matched by slug)
                │
                ▼
        Per-game processing:
        lineup adjustment → prediction model → edge calculator
                │
                ▼
        DailyAnalysis (cached 5min TTL)
```

---

## Project Structure

```
bk8/
├── package.json               # Root: concurrently scripts (npm run dev)
├── CourtEdge_PRD.md           # Full product requirements document
├── backend/
│   ├── app/
│   │   ├── services/
│   │   │   └── pipeline.py    # ★ Core orchestrator (the brain)
│   │   ├── analytics/         # Core engines
│   │   │   ├── lineup_adjustment.py   # OnOffSplitModel
│   │   │   ├── prediction_model.py    # NRtg → spread, win prob, total
│   │   │   ├── edge_calculator.py     # Model vs market → edge + Kelly
│   │   │   └── schedule_engine.py     # B2B, fatigue, motivation
│   │   ├── api/v1/            # REST endpoints
│   │   │   ├── games.py       # /games/today, /games/today/ai-prompt
│   │   │   ├── bets.py        # POST /bets, GET /bets/history
│   │   │   ├── teams.py       # /teams, /teams/{id}/ratings
│   │   │   └── injuries.py    # POST /injuries/override
│   │   ├── connectors/        # External API clients
│   │   │   ├── nba_api.py     # stats.nba.com (scoreboard, ratings, standings)
│   │   │   ├── pbpstats.py    # pbpstats.com (on/off splits)
│   │   │   ├── polymarket.py  # gamma-api.polymarket.com (51K+ markets)
│   │   │   └── injuries.py    # NBA injury feed
│   │   ├── models/            # SQLAlchemy ORM (10 tables)
│   │   ├── schemas/           # Pydantic request/response models
│   │   └── main.py            # FastAPI app entry point
│   ├── tests/                 # 68+ unit tests
│   ├── alembic/               # DB migrations
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── app/
    │   │   ├── page.tsx       # Dashboard (live data, auto-refresh 5min)
    │   │   ├── bets/page.tsx  # Bet tracker
    │   │   └── accuracy/      # Model accuracy (placeholder)
    │   ├── components/
    │   │   ├── GameCard.tsx   # Expandable game analysis card
    │   │   ├── TopEdges.tsx   # Top edges banner
    │   │   └── Header.tsx     # Navigation + SGT clock
    │   ├── lib/
    │   │   ├── api.ts         # Backend API client
    │   │   └── utils.ts       # Formatting, verdict colors
    │   └── types/api.ts       # TypeScript interfaces (mirrors Pydantic)
    └── package.json
```

---

## API Reference

All endpoints prefixed with `/api/v1`. Interactive Swagger docs at `http://localhost:8000/docs`.

### Games

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/games/today` | Full analysis for all games today (the main endpoint) |
| `GET` | `/games/today/ai-prompt` | Pre-formatted text for Claude / ChatGPT |
| `GET` | `/games/{game_id}` | Detail for a single game |
| `POST` | `/games/refresh` | Force clear cache and re-fetch all data |

### Bets

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/bets` | Log a new bet |
| `GET` | `/bets/history` | Bet history with aggregate stats |

### Teams

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/teams` | List all 30 NBA teams |
| `GET` | `/teams/{team_id}` | Team info by abbreviation |
| `GET` | `/teams/{team_id}/ratings` | Live team ratings |

### Example: Get today's edges

```bash
curl -s http://localhost:8000/api/v1/games/today | python3 -c "
import json,sys; d=json.load(sys.stdin)
for e in d['top_edges'][:5]:
    print(f\"{e['verdict']}: {e['selection']} @ \${e['price']:.2f} (edge: {e['edge']:+.1%})\")
"
```

### Example: AI prompt for Claude/ChatGPT

```bash
curl -s http://localhost:8000/api/v1/games/today/ai-prompt | jq -r '.prompt'
```

---

## Core Concepts

### Lineup Adjustment Engine

The core differentiator. Instead of season-average team ratings, CourtEdge adjusts for who's actually playing:

```
Adjusted_ORtg = Season_ORtg + Σ (player_impact × minutes_share × 0.85^i)
```

- **Player impact** = `on_court_rating - off_court_rating` (PBP Stats on/off splits)
- **Diminishing returns** = `0.85^i` for the `i`-th missing player
- **Confidence** = based on sample size (HIGH: >200min, MEDIUM: 100-200, LOW: <100)

### Prediction Model

```
NRtg differential → projected margin (+3.0 home court)
→ logistic win probability (sigma=6.0)
→ spread cover / over probability (normal dist, std_dev=12.0)
```

### Edge Calculator

```
edge = model_probability - market_price
verdict: ≥12% STRONG BUY │ ≥6% BUY │ ≥3% LEAN │ <3% NO EDGE
kelly% = quarter Kelly for conservative sizing
```

### Team Ratings Fallback Chain

NBA's advanced stats endpoint (`leaguedashteamstats`) returns HTTP 500 intermittently. The pipeline handles this with a 4-level fallback:

1. `leaguedashteamstats` MeasureType=Advanced
2. `leaguedashteamstats` MeasureType=Base
3. `teamestimatedmetrics` (E_OFF_RATING, E_DEF_RATING) ← **usually works**
4. Standings estimation: `NRtg = (WinPCT - 0.5) × 28`

---

## Configuration

### Backend (`.env`)

```env
DATABASE_URL=postgresql+asyncpg://user:@localhost:5432/courtedge
ENVIRONMENT=development
LOG_LEVEL=DEBUG
CORS_ORIGINS=http://localhost:3000
```

### Frontend (`.env.local`)

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

---

## Database Setup (Optional)

The app works without a database (live pipeline + in-memory cache). For bet tracking persistence:

```bash
createdb courtedge
cd backend && source venv/bin/activate
alembic upgrade head   # Creates 10 tables
```

---

## Roadmap

- [x] **Phase 1**: Full stack MVP — connectors, analytics, API, frontend
- [x] **Phase 2**: Live data pipeline — real NBA/Polymarket data, wired frontend
- [ ] **Phase 3**: Model improvements — RAPM player model, backtesting, calibration
- [ ] **Phase 4**: Deployment — Railway + Vercel, WebSocket prices, alert notifications

---

## License

Private project. All rights reserved.
