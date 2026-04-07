# CourtEdge

**Lineup-adjusted NBA analytics platform for Polymarket edge detection.**

CourtEdge replaces stale team-level NBA stats with real-time lineup-adjusted ratings. It calculates the true impact of missing players using on/off splits, then compares model probabilities against Polymarket prices to surface mispriced bets with expected value.

---

## Table of Contents

- [Why CourtEdge](#why-courtedge)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Running the Backend](#running-the-backend)
- [Running the Frontend](#running-the-frontend)
- [Running Tests](#running-tests)
- [API Reference](#api-reference)
- [Core Concepts](#core-concepts)
- [Configuration](#configuration)
- [Contributing](#contributing)
- [Roadmap](#roadmap)

---

## Why CourtEdge

Polymarket NBA lines move slowly compared to sportsbooks. When a star player is ruled out 90 minutes before tipoff, the market often lags 10-20 minutes. CourtEdge pre-calculates the adjusted ratings for every plausible injury scenario, so you can see the true edge the moment news breaks.

**Core workflow:**
1. Pull team ratings from NBA API + PBP Stats
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
│  Port 8000 │ Python 3.11+ │ async/await │ Pydantic v2            │
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
│  PostgreSQL (SQLAlchemy + Alembic) │ Redis (cache, optional)     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
bk8/
├── CLAUDE.md                  # AI pair-programming guide
├── CourtEdge_PRD.md           # Full product requirements document
├── backend/
│   ├── app/
│   │   ├── analytics/         # Core engines
│   │   │   ├── lineup_adjustment.py   # OnOffSplitModel (the key differentiator)
│   │   │   ├── prediction_model.py    # NRtg → spread, win prob, total
│   │   │   ├── edge_calculator.py     # Model vs market → edge + Kelly
│   │   │   └── schedule_engine.py     # B2B, fatigue, motivation
│   │   ├── api/v1/            # REST endpoints
│   │   │   ├── games.py       # /games/today, /games/today/ai-prompt
│   │   │   ├── bets.py        # POST /bets, GET /bets/history
│   │   │   ├── teams.py       # /teams, /teams/{id}/ratings
│   │   │   └── injuries.py    # POST /injuries/override
│   │   ├── connectors/        # External API clients
│   │   │   ├── nba_api.py     # stats.nba.com
│   │   │   ├── pbpstats.py    # pbpstats.com (on/off splits)
│   │   │   ├── polymarket.py  # gamma-api.polymarket.com
│   │   │   └── injuries.py    # NBA injury feed (CDN + API)
│   │   ├── models/            # SQLAlchemy ORM (10 tables)
│   │   ├── schemas/           # Pydantic request/response models
│   │   ├── services/          # Validation layer
│   │   ├── config.py          # Settings from env vars
│   │   └── main.py            # FastAPI app entry point
│   ├── tests/                 # 68 unit tests
│   ├── alembic/               # DB migrations
│   ├── requirements.txt
│   └── pyproject.toml
└── frontend/
    ├── src/
    │   ├── app/               # Next.js App Router pages
    │   │   ├── page.tsx       # Main dashboard
    │   │   ├── bets/page.tsx  # Bet tracker
    │   │   └── accuracy/page.tsx  # Model accuracy (placeholder)
    │   ├── components/        # React components
    │   │   ├── GameCard.tsx   # Expandable game analysis card
    │   │   ├── TopEdges.tsx   # Top edges banner
    │   │   └── Header.tsx     # Navigation + live clock
    │   ├── lib/               # API client + utilities
    │   └── types/             # TypeScript interfaces
    ├── package.json
    └── tsconfig.json
```

---

## Getting Started

### Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | Required for `X \| Y` union syntax |
| Node.js | 18+ | For Next.js 15 |
| PostgreSQL | 14+ | Can skip for dev (API works with sample data) |
| Redis | 7+ | Optional, for caching |

### 1. Clone the repo

```bash
git clone https://github.com/davidfoo07/bk8.git
cd bk8
```

### 2. Backend setup

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy env config
cp .env.example .env
# Edit .env if you have a PostgreSQL instance, otherwise defaults work for API-only mode
```

### 3. Frontend setup

```bash
cd frontend

# Install dependencies
npm install

# Copy env config
cp .env.example .env.local
```

---

## Running the Backend

```bash
cd backend
source venv/bin/activate

# Development server with hot reload
uvicorn app.main:app --reload --port 8000

# The API is now live at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

The backend ships with **sample data** (CLE vs MEM game with edges) so you can explore the API immediately without a database or live data connections.

### Database setup (optional for dev)

If you want persistence, create the PostgreSQL database and run migrations:

```bash
createdb courtedge
alembic upgrade head
```

---

## Running the Frontend

```bash
cd frontend

# Development server
npm run dev

# Open http://localhost:3000
```

The frontend falls back to built-in sample data if the backend is unreachable, so you can run it standalone to see the UI.

---

## Running Tests

```bash
cd backend
source venv/bin/activate

# Run all 68 tests
python -m pytest tests/ -v

# Run specific test module
python -m pytest tests/analytics/test_edge_calculator.py -v

# Run with coverage
python -m pytest tests/ --cov=app --cov-report=html
```

Test breakdown:
- `test_lineup_adjustment.py` — OnOffSplitModel, diminishing returns, confidence levels
- `test_prediction_model.py` — Win probability, totals, schedule modifiers, margin conversion
- `test_edge_calculator.py` — Edge calculation, Kelly criterion, verdicts
- `test_validation.py` — Range checks, cross-source, staleness, anomaly detection
- `test_endpoints.py` — All REST API endpoints (games, bets, teams, injuries)

---

## API Reference

All endpoints are prefixed with `/api/v1`. Interactive Swagger docs at `/docs`.

### Games

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/games/today` | Full analysis for all games today (the main endpoint) |
| `GET` | `/games/today/ai-prompt` | Pre-formatted text for Claude / ChatGPT consumption |
| `GET` | `/games/{game_id}` | Detailed analysis for a single game |

### Bets

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/bets` | Log a new bet |
| `GET` | `/bets/history` | Bet history with aggregate stats (win rate, ROI, P&L) |

### Teams

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/teams` | List all 30 NBA teams |
| `GET` | `/teams/{team_id}` | Team info by abbreviation (e.g. `CLE`) |
| `GET` | `/teams/{team_id}/ratings` | Current and adjusted ratings |

### Injuries

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/injuries/override` | Manually set a player's status (e.g. OUT before official report) |
| `GET` | `/injuries/overrides` | List all manual overrides |
| `DELETE` | `/injuries/override/{player_id}` | Remove an override |

### Example: Get today's analysis

```bash
curl http://localhost:8000/api/v1/games/today | python -m json.tool
```

### Example: Copy AI prompt

```bash
curl -s http://localhost:8000/api/v1/games/today/ai-prompt | jq -r '.prompt'
```

---

## Core Concepts

### Lineup Adjustment Engine

The core differentiator. Instead of using season-average team ratings, CourtEdge adjusts for who's actually playing tonight:

```
Adjusted_ORtg = Season_ORtg + Σ (player_impact × minutes_share × diminishing_factor)
```

- **Player impact** = `on_court_rating - off_court_rating` (from PBP Stats on/off splits)
- **Diminishing returns** = `0.85^i` for the `i`-th missing player (interaction effects)
- **Confidence** = based on on/off minutes sample size (HIGH: >200min, MEDIUM: 100-200, LOW: <100)

### Prediction Model

Converts adjusted ratings to game predictions:

1. **NRtg differential** → projected margin (home NRtg - away NRtg)
2. **Home court advantage** → +3.0 points
3. **Schedule modifiers** → B2B (-2.5), 3-in-4 (-3.5), rest advantage (+1.5/day)
4. **Win probability** → logistic function with sigma=6.0
5. **Spread cover / Over prob** → normal distribution with std_dev=12.0

### Edge Calculator

Compares model vs market:

```
edge = model_probability - market_price
EV = (probability × decimal_odds) - 1
Kelly% = (p × b - q) / b   (quarter Kelly for conservative sizing)
```

Verdicts:
- **STRONG BUY**: edge >= 12%
- **BUY**: edge >= 6%
- **LEAN**: edge >= 3%
- **NO EDGE**: edge < 3%

### Data Validation (4 Tiers)

1. **Range checks** — ORtg/DRtg within [90, 130], NRtg within [-25, 25], etc.
2. **Cross-source** — NBA API vs PBP Stats ratings within 2.0 tolerance
3. **Staleness** — Prices <10min, injuries <2hr, ratings <24hr
4. **Anomaly** — Flag NRtg swings >8pts or price moves >15¢/hr

---

## Configuration

### Backend (`.env`)

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/courtedge
REDIS_URL=redis://localhost:6379/0
ENVIRONMENT=development          # development | production
LOG_LEVEL=DEBUG                  # DEBUG | INFO | WARNING
CORS_ORIGINS=http://localhost:3000
```

### Frontend (`.env.local`)

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

### Data Refresh Intervals (backend `config.py`)

| Data | Interval | Setting |
|------|----------|---------|
| Injury reports | 30 min | `injury_refresh_interval` |
| Polymarket prices | 5 min | `polymarket_refresh_interval` |
| Team ratings | 24 hr | `ratings_refresh_interval` |

---

## Contributing

### Development workflow

1. Fork the repo and create a feature branch from `main`
2. Install dependencies for both backend and frontend (see [Getting Started](#getting-started))
3. Make your changes
4. Run tests: `cd backend && python -m pytest tests/ -v`
5. Lint: `cd backend && ruff check app/` and `cd frontend && npm run lint`
6. Open a pull request against `main`

### Code style

- **Backend**: Python 3.11+, type hints everywhere, ruff + mypy strict
- **Frontend**: TypeScript strict, functional components, Tailwind utility classes
- **Naming**: snake_case (Python), camelCase (TypeScript), PascalCase (React components)
- **Imports**: absolute imports from `app.` (backend) and `@/` (frontend)

### Key design principles

- **Pluggable models** — `LineupAdjustmentModel` is an abstract class. V1 is `OnOffSplitModel`. Add V2 by implementing the interface.
- **Connectors inherit from `BaseConnector`** — All external APIs use the same abstract interface with `fetch()`, `health_check()`, and retry logic.
- **Schemas as contracts** — Pydantic models define the API boundary. Frontend TypeScript types mirror them exactly.
- **Sample data fallback** — Both backend and frontend work with sample data, so you can develop without live API keys or a database.

---

## Roadmap

### Phase 2 — Live Data Pipeline
- [ ] Wire connectors to live NBA API / PBP Stats data
- [ ] APScheduler jobs for automatic refresh
- [ ] Redis caching for hot data
- [ ] Alembic migrations for production DB

### Phase 3 — Model Improvements
- [ ] V2 lineup model using multi-player interaction effects
- [ ] Bayesian regression for on/off split stabilization
- [ ] Historical backtesting engine
- [ ] Model accuracy tracking (calibration curves, ROI by edge threshold)

### Phase 4 — Production Deployment
- [ ] Railway (backend + PostgreSQL) + Vercel (frontend)
- [ ] WebSocket for live price updates
- [ ] Telegram/WEA notifications for STRONG BUY alerts
- [ ] Multi-sport expansion (NFL, MLB)

---

## License

Private project. All rights reserved.
