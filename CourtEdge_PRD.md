# Product Requirements Document (PRD)
# CourtEdge — Polymarket NBA Betting Analysis Platform

**Version:** 1.0
**Date:** April 7, 2026
**Author:** Product Team
**Status:** Ready for Development

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Product Vision & Success Metrics](#3-product-vision--success-metrics)
4. [User Personas](#4-user-personas)
5. [System Architecture](#5-system-architecture)
6. [Feature Specifications](#6-feature-specifications)
7. [Data Architecture](#7-data-architecture)
8. [API Specification](#8-api-specification)
9. [Frontend Specification](#9-frontend-specification)
10. [Prediction Model](#10-prediction-model)
11. [Development Phases & Roadmap](#11-development-phases--roadmap)
12. [Claude Code Implementation Guide](#12-claude-code-implementation-guide)
13. [Testing Strategy](#13-testing-strategy)
14. [Deployment & Infrastructure](#14-deployment--infrastructure)
15. [Future Considerations](#15-future-considerations)

---

## 1. Executive Summary

CourtEdge is a lineup-adjusted NBA analytics platform built for Polymarket prediction market betting. It solves the core problem of using stale team-level statistics by recalculating team ratings based on who is actually playing tonight, then comparing the model's probability estimates against Polymarket prices to surface mispriced opportunities (positive expected value bets).

**The core value proposition:** Reduce nightly research from ~2 hours to ~15 minutes while dramatically improving analysis quality by replacing team-level averages with lineup-adjusted ratings.

**Two interfaces:**
- A professional dark-mode web dashboard for the human operator
- A structured JSON API for AI systems (Claude and Gemini) to consume

---

## 2. Problem Statement

### Current Pain Points (Ordered by Impact)

**#1 — Stale team-level stats lead to bad bets**
Season-long Offensive Rating (ORtg), Defensive Rating (DRtg), and Net Rating (NRtg) don't reflect who's actually playing. When key players are OUT, these numbers are misleading. Example: Betting Detroit -2.5 based on strong season NRtg when Cade Cunningham was OUT — Detroit's NRtg without Cade is significantly worse. Result: loss.

**#2 — Totals model is broken (0-4 record)**
Team-level pace and efficiency inputs are unreliable during late-season rotation changes. The tool needs lineup-aware projections for totals as well as spreads.

**#3 — No systematic edge detection**
No process for comparing model probability against Polymarket price to calculate expected value. Bets are made on "who will win" rather than "where is the price wrong."

**#4 — Manual workflow is slow and error-prone**
Currently visiting Polymarket, StatMuse, and other sites, copy-pasting links to AI systems. ~2 hours per night of manual research across 6+ websites.

### Track Record
- 19 bets across 2 sessions: 8-11 (42% win rate), net negative P&L
- Losses are primarily attributable to using unadjusted team-level stats

---

## 3. Product Vision & Success Metrics

### Vision
Build the most accurate lineup-adjusted NBA ratings engine available, paired with a Polymarket edge calculator, that a solo bettor (and eventually subscribers) can use to find and exploit mispriced prediction markets.

### Success Metrics (MVP)

| Metric | Target | How Measured |
|--------|--------|-------------|
| Nightly research time | < 15 minutes | Self-reported |
| Model calibration | Within 5% of actual outcomes over 50+ bets | `(predicted probability - actual win rate)` per bucket |
| Edge detection accuracy | > 55% win rate on bets where model shows > 8% edge | Historical tracking |
| Data freshness | Injury data < 30 min old, Polymarket prices < 5 min old | Monitoring |
| API response time | < 2 seconds for full game analysis | Logging |

---

## 4. User Personas

### Primary: The Operator (Human)
- Solo bettor based in Singapore (UTC+8)
- NBA games occur in US Eastern time (games tip off at 7pm-10:30pm ET = 7am-10:30am SGT next day)
- Analyzes every game on the slate each night
- Bets a few hours before tipoff, primarily on Polymarket
- Bets on spreads, moneylines, and totals (not player props)
- Can buy YES or NO shares depending on which side has the edge
- Uses fractional Kelly criterion for position sizing
- Wants to scan quickly, spot edges, and act

### Secondary: AI Analysts (Claude & Gemini)
- Receive structured game data via API or formatted prompt
- Analyze matchups, provide qualitative context
- Output recommendations that the Operator cross-references against the model
- Need clean, structured, comprehensive data in a single API call

### Future: Subscribers
- Other bettors who pay for access to lineup-adjusted ratings and edge calculations
- Not building auth/billing now, but architecture must support it later

---

## 5. System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      DATA INGESTION LAYER                   │
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │ NBA API   │ │ PBP Stats│ │ Injury   │ │ Polymarket   │  │
│  │ Connector │ │ Connector│ │ Feed     │ │ Gamma API    │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘  │
│       │             │            │               │          │
│  ┌────▼─────────────▼────────────▼───────────────▼───────┐  │
│  │              DATA VALIDATION LAYER                     │  │
│  │   • Range checks  • Cross-source verification         │  │
│  │   • Staleness detection  • Anomaly flagging           │  │
│  └──────────────────────┬────────────────────────────────┘  │
└─────────────────────────┼───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                     ANALYTICS ENGINE                        │
│                                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐  │
│  │ Lineup       │ │ Schedule     │ │ Motivation /       │  │
│  │ Adjustment   │ │ Context      │ │ Standings          │  │
│  │ Engine       │ │ Engine       │ │ Engine             │  │
│  └──────┬───────┘ └──────┬───────┘ └─────────┬──────────┘  │
│         │                │                    │             │
│  ┌──────▼────────────────▼────────────────────▼──────────┐  │
│  │              PREDICTION MODEL                          │  │
│  │   NRtg-based → Win Prob → Spread → Total projection   │  │
│  └──────────────────────┬────────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼────────────────────────────────┐  │
│  │              EDGE CALCULATOR                           │  │
│  │   Model Prob vs Polymarket Price → EV → Verdict       │  │
│  └──────────────────────┬────────────────────────────────┘  │
└─────────────────────────┼───────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
┌─────────▼────┐ ┌───────▼──────┐ ┌──────▼───────┐
│  REST API    │ │  Web         │ │  Historical  │
│  (AI-facing) │ │  Dashboard   │ │  Database    │
│              │ │  (Human)     │ │  (Tracking)  │
└──────────────┘ └──────────────┘ └──────────────┘
```

### Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Backend Runtime | **Python 3.11+ / FastAPI** | Superior sports data libraries (`nba_api`, `pandas`, `numpy`), async support, fast development |
| Database | **PostgreSQL** via Supabase or Railway | Relational for structured game/bet data, JSON columns for flexible stats, free tier available |
| Cache | **Redis** (or in-memory with TTL) | Cache API responses, reduce external calls |
| Task Scheduler | **APScheduler** (in-process) or **cron jobs** | Scheduled data refresh without separate infra |
| Frontend | **Next.js 14+ (App Router)** with React | SSR for fast loads, excellent DX, Vercel deployment |
| Charting | **Recharts** or **Lightweight Charts (TradingView)** | Interactive, professional-grade charts |
| Styling | **Tailwind CSS** | Utility-first, dark mode built-in, rapid iteration |
| Hosting | **Railway** (backend + DB + Redis) + **Vercel** (frontend) | Simple deployment, affordable, good DX |
| Monorepo | **Turborepo** or flat structure with `/backend` and `/frontend` dirs | Clean separation |

### Why a Backend Is Required

1. **Scheduled jobs** — Injury feeds refresh every 30 minutes, Polymarket prices every 5 minutes, ratings recalculate daily. A pure frontend cannot schedule.
2. **Data caching** — External APIs (NBA, PBP Stats) rate-limit aggressively. The backend caches responses and serves them to the frontend/API.
3. **Historical storage** — Tracking bets, results, and model accuracy over time requires a database.
4. **AI-readable API** — Claude and Gemini need a structured endpoint to call.
5. **Computation** — Lineup adjustment calculations are CPU-intensive and shouldn't run client-side.

---

## 6. Feature Specifications

### 6.1 Lineup-Adjusted Ratings Engine (P0 — THE CORE FEATURE)

**What it does:**
Takes a team's season-level ORtg, DRtg, and NRtg, then adjusts based on which players are confirmed OUT, GTD, or minutes-limited for tonight's game.

**Methodology (Start Simple, Design for Swap):**

The system uses a **pluggable model interface**. V1 implements additive on/off splits. The interface allows future upgrades (RAPM, lineup-combination-based) without rewriting consumers.

```python
# Abstract interface — all model implementations conform to this
class LineupAdjustmentModel(ABC):
    @abstractmethod
    def calculate_adjusted_ratings(
        self,
        team_id: str,
        season_ortg: float,
        season_drtg: float,
        missing_players: list[PlayerAbsence],
        minutes_context: dict  # player minutes distributions
    ) -> AdjustedRatings:
        pass

# V1 Implementation: Additive On/Off Splits
class OnOffSplitModel(LineupAdjustmentModel):
    """
    For each missing player:
    1. Pull team ORtg WITH player on court vs OFF court
    2. Calculate delta: on_court_ortg - off_court_ortg = player_impact
    3. Weight by minutes share (a player who plays 35 mpg matters more than 15 mpg)
    4. Sum deltas for all missing players
    5. Apply to team baseline

    Example:
        Team season ORtg: 115.0
        Player A (OUT): on-court ORtg 118.0, off-court 110.5 → impact = +7.5
        Player A minutes share: 0.40 (plays 40% of team minutes)
        Weighted impact: 7.5 * 0.40 = 3.0
        Adjusted ORtg: 115.0 - 3.0 = 112.0
    """
```

**Multi-player absence handling:**
- For 1 missing player: straightforward on/off delta
- For 2+ missing players: check if PBP Stats has data for the specific N-man lineup combination that remains. If yes, use that directly (more accurate). If no, fall back to additive on/off (sum individual deltas, apply diminishing returns factor of 0.85 per additional player to avoid over-correction)

**Output per team per game:**

```json
{
  "team": "DET",
  "season_ortg": 112.5,
  "season_drtg": 114.2,
  "season_nrtg": -1.7,
  "adjusted_ortg": 108.3,
  "adjusted_drtg": 116.1,
  "adjusted_nrtg": -7.8,
  "ortg_delta": -4.2,
  "drtg_delta": +1.9,
  "nrtg_delta": -6.1,
  "missing_players": [
    {
      "name": "Cade Cunningham",
      "status": "OUT",
      "ortg_impact": -3.5,
      "drtg_impact": +1.2,
      "nrtg_impact": -4.7,
      "minutes_share": 0.38
    }
  ],
  "confidence": "HIGH",  // HIGH if >200 on/off minutes sample, MEDIUM if 100-200, LOW if <100
  "data_source": "pbpstats",
  "last_updated": "2026-04-07T14:30:00Z"
}
```

### 6.2 Data Validation Layer (P0)

Every piece of data flowing through the system must be validated. This is a first-class concern, not an afterthought.

**Tier 1 — Range/Sanity Checks (automated, every data fetch):**

```python
VALIDATION_RULES = {
    "ortg": {"min": 90, "max": 130, "description": "Offensive Rating"},
    "drtg": {"min": 90, "max": 130, "description": "Defensive Rating"},
    "nrtg": {"min": -25, "max": 25, "description": "Net Rating"},
    "pace": {"min": 90, "max": 110, "description": "Pace Factor"},
    "player_minutes": {"min": 0, "max": 48, "description": "Minutes Per Game"},
    "team_roster_size": {"min": 12, "max": 17, "description": "Active Roster Size"},
    "game_count": {"min": 1, "max": 82, "description": "Games Played"},
    "win_probability": {"min": 0, "max": 1, "description": "Win Probability"},
    "polymarket_price": {"min": 0.01, "max": 0.99, "description": "Market Price"},
}
```

If any value falls outside its range → log a WARNING, flag the data point, and fall back to the last known good value.

**Tier 2 — Cross-Source Verification (daily, during ratings refresh):**

```python
# Compare ORtg/DRtg/NRtg across NBA API and PBP Stats
# They should agree within a tolerance (different methodologies have slight differences)
CROSS_SOURCE_TOLERANCE = {
    "ortg": 2.0,   # Within 2.0 points
    "drtg": 2.0,
    "nrtg": 3.0,   # NRtg can diverge more due to possession counting differences
}

# If sources disagree beyond tolerance → flag for manual review
# Use the average of agreeing sources as the canonical value
# Log the discrepancy for debugging
```

**Tier 3 — Staleness Detection:**
- Team ratings: flag if > 24 hours old
- Injury reports: flag if > 2 hours old during game day
- Polymarket prices: flag if > 10 minutes old
- If stale → show a visible warning badge in the UI

**Tier 4 — Anomaly Detection:**
- If a team's adjusted NRtg changes by more than 8 points from baseline → flag as "unusual, verify injuries"
- If Polymarket price moves more than 15 cents in an hour → flag as "major line movement"

### 6.3 Polymarket Integration & Edge Calculator (P0)

**Polymarket Gamma API Integration:**

```
Base URL: https://gamma-api.polymarket.com
NBA series_id: 10345

Endpoints:
  GET /markets?series_id=10345&active=true
  → Returns all active NBA markets

Market types to pull:
  - Moneyline (e.g., "Will CLE beat MEM?")
  - Spread (e.g., "Will CLE cover -13.5?")
  - Total (e.g., "Will CLE vs MEM go Over 224.5?")

Slug format: nba-{away}-{home}-{YYYY-MM-DD}
Example: nba-det-orl-2026-04-06

Key fields:
  - outcome_prices: [YES_price, NO_price]
  - volume: total trading volume
  - liquidity: available liquidity
```

**Edge Calculation:**

```python
def calculate_edge(model_probability: float, market_price: float) -> EdgeResult:
    """
    model_probability: our model's estimated true probability (0-1)
    market_price: Polymarket YES price (0-1), which IS the implied probability

    Returns edge, EV per dollar, Kelly fraction, and verdict.
    """
    edge = model_probability - market_price
    
    # EV per $1 bet on YES
    # If you buy YES at $0.45, you pay $0.45 and win $1.00 if correct
    # EV = (prob * payout) - cost = (prob * 1.0) - price
    ev_per_dollar = (model_probability * (1.0 / market_price)) - 1.0

    # Also calculate edge on the NO side
    no_model_prob = 1.0 - model_probability
    no_price = 1.0 - market_price
    no_edge = no_model_prob - no_price
    no_ev = (no_model_prob * (1.0 / no_price)) - 1.0

    # Kelly Criterion (full Kelly, display as fraction)
    # Kelly% = edge / (odds - 1) ... but for Polymarket:
    # Kelly% = (model_prob * decimal_odds - 1) / (decimal_odds - 1)
    decimal_odds_yes = 1.0 / market_price
    kelly_yes = max(0, (model_probability * decimal_odds_yes - 1) / (decimal_odds_yes - 1))
    quarter_kelly_yes = kelly_yes * 0.25  # Conservative: quarter Kelly

    # Determine best side and verdict
    best_side = "YES" if edge > no_edge else "NO"
    best_edge = max(edge, no_edge)
    
    if best_edge >= 0.12:
        verdict = "STRONG BUY"
    elif best_edge >= 0.06:
        verdict = "BUY"
    elif best_edge >= 0.03:
        verdict = "LEAN"
    else:
        verdict = "NO EDGE"

    return EdgeResult(
        yes_edge=edge,
        no_edge=no_edge,
        yes_ev=ev_per_dollar,
        no_ev=no_ev,
        best_side=best_side,
        best_edge=best_edge,
        verdict=verdict,
        kelly_fraction=quarter_kelly_yes if best_side == "YES" else ...,
        suggested_bet_pct=quarter_kelly_yes * 100  # as percentage of bankroll
    )
```

**Display per game (dashboard card):**

```
CLE vs MEM  |  Spread: CLE -13.5  |  Total: 224.5
─────────────────────────────────────────────────────
SPREAD                Polymarket    Our Model    Edge
CLE covers -13.5:       45¢          58%        +13%     ← STRONG BUY
MEM covers +13.5:       55¢          42%        -13%

MONEYLINE             Polymarket    Our Model    Edge
CLE wins:               82¢          88%         +6%     ← BUY
MEM wins:               18¢          12%         -6%

TOTAL                 Polymarket    Our Model    Edge
Over 224.5:             52¢          48%         -4%
Under 224.5:            48¢          52%         +4%     ← LEAN

Suggested: BUY CLE -13.5 YES @ 45¢ | Kelly: 6.2% of bankroll
─────────────────────────────────────────────────────
```

### 6.4 Injury Feed (P0)

**Data Sources (in priority order):**
1. NBA Official Injury Report (`stats.nba.com` or `data.nba.com`)
2. Backup: Rotowire injury feed (scraping or RSS)

**Refresh Schedule:**
- Every 30 minutes on game days (starting 12 hours before first tipoff)
- Every 2 hours on non-game days

**Data Model:**

```json
{
  "player_name": "Cade Cunningham",
  "player_id": "1630595",
  "team": "DET",
  "status": "OUT",           // OUT | DOUBTFUL | QUESTIONABLE | PROBABLE | GTD | AVAILABLE
  "reason": "Knee - Injury Management",
  "source": "NBA Official",
  "last_updated": "2026-04-07T10:00:00-04:00",
  "confirmed_at": "2026-04-07T15:30:00-04:00",  // null if not yet confirmed for tonight
  "impact_rating": "HIGH"    // Based on minutes share and on/off differential
}
```

**Critical behavior:** When a player's status changes to OUT, the Lineup Adjustment Engine AUTOMATICALLY recalculates that team's adjusted ratings. The dashboard updates in near real-time. No manual intervention required.

**Manual override:** The Operator can manually set a player as OUT/IN (for cases where the injury report hasn't updated yet but the Operator has information). Manual overrides are flagged visually and persist until the next official update.

### 6.5 Schedule Context Engine (P1)

**Factors calculated per team per game:**

| Factor | Definition | Point Adjustment |
|--------|-----------|-----------------|
| Back-to-back | 2nd game in 2 nights | -2.5 points |
| 3-in-4 | 3rd game in 4 nights | -3.5 points |
| 4-in-6 | 4th game in 6 nights | -4.0 points |
| Road trip length | 4+ consecutive road games | -1.0 per game beyond 3rd |
| Rest advantage | Opponent has 2+ more rest days | +1.5 per extra rest day (max +3.0) |
| Home court | Playing at home | +3.0 points |
| Travel distance | Coast-to-coast travel | -0.5 to -1.5 based on miles |

These are additive modifiers applied to the projected spread.

### 6.6 Standings & Motivation Context (P1)

**Data points per team:**

```json
{
  "team": "CLE",
  "record": "62-18",
  "conference_seed": 1,
  "games_back": 0,
  "clinch_status": "CLINCHED_1_SEED",
  "magic_number": 0,
  "motivation_flag": "REST_EXPECTED",  // REST_EXPECTED | NEUTRAL | DESPERATE | FIGHTING
  "motivation_note": "Clinched #1 seed. Expect star rest in remaining games.",
  "remaining_schedule_strength": 0.480,
  "playoff_opponent_preview": "Faces MIA/ATL in R1"
}

// Motivation flags:
// REST_EXPECTED — clinched seeding, nothing to play for
// DESPERATE — 1-2 games from elimination or play-in bubble
// FIGHTING — seeding still in flux, every game matters
// NEUTRAL — default
```

### 6.7 Bet Tracking & Model Accuracy (P1)

**Log every bet placed:**

```json
{
  "id": "bet_001",
  "date": "2026-04-07",
  "game": "CLE vs MEM",
  "market_type": "spread",           // spread | moneyline | total
  "selection": "CLE -13.5 YES",
  "entry_price": 0.45,
  "model_probability": 0.58,
  "edge_at_entry": 0.13,
  "amount_usd": 50.00,
  "kelly_fraction_used": 0.062,
  "result": null,                    // WIN | LOSS | PUSH | null (pending)
  "pnl": null,                      // calculated after resolution
  "actual_margin": null,             // e.g., CLE won by 17 → CLE covered
  "notes": "Mobley resting for CLE, but MEM also missing Bane"
}
```

**Model accuracy dashboard (after 50+ bets):**
- Calibration curve: predicted probability buckets vs actual win rate
- ROI by edge threshold (e.g., "bets with >10% edge: +14% ROI")
- ROI by market type (spread vs moneyline vs total)
- Running P&L chart over time

---

## 7. Data Architecture

### Database Schema (PostgreSQL)

```sql
-- Teams
CREATE TABLE teams (
    id VARCHAR(3) PRIMARY KEY,       -- e.g., "CLE"
    full_name VARCHAR(50),
    conference VARCHAR(4),           -- "EAST" | "WEST"
    division VARCHAR(20)
);

-- Players
CREATE TABLE players (
    id VARCHAR(20) PRIMARY KEY,      -- NBA player ID
    name VARCHAR(100),
    team_id VARCHAR(3) REFERENCES teams(id),
    position VARCHAR(5),
    is_active BOOLEAN DEFAULT true
);

-- Team ratings (daily snapshot)
CREATE TABLE team_ratings (
    id SERIAL PRIMARY KEY,
    team_id VARCHAR(3) REFERENCES teams(id),
    date DATE NOT NULL,
    ortg DECIMAL(5,1),
    drtg DECIMAL(5,1),
    nrtg DECIMAL(5,1),
    pace DECIMAL(5,1),
    source VARCHAR(20),              -- "nba_api" | "pbpstats" | "avg"
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(team_id, date, source)
);

-- Player on/off splits (daily snapshot)
CREATE TABLE player_on_off (
    id SERIAL PRIMARY KEY,
    player_id VARCHAR(20) REFERENCES players(id),
    team_id VARCHAR(3) REFERENCES teams(id),
    date DATE NOT NULL,
    on_ortg DECIMAL(5,1),
    off_ortg DECIMAL(5,1),
    on_drtg DECIMAL(5,1),
    off_drtg DECIMAL(5,1),
    on_nrtg DECIMAL(5,1),
    off_nrtg DECIMAL(5,1),
    on_minutes INTEGER,              -- total on-court minutes (sample size)
    off_minutes INTEGER,
    minutes_per_game DECIMAL(4,1),
    minutes_share DECIMAL(4,3),      -- fraction of team minutes
    source VARCHAR(20),
    UNIQUE(player_id, date, source)
);

-- Injuries
CREATE TABLE injuries (
    id SERIAL PRIMARY KEY,
    player_id VARCHAR(20) REFERENCES players(id),
    team_id VARCHAR(3) REFERENCES teams(id),
    game_date DATE,
    status VARCHAR(15),              -- OUT, DOUBTFUL, QUESTIONABLE, PROBABLE, GTD, AVAILABLE
    reason TEXT,
    source VARCHAR(20),
    is_manual_override BOOLEAN DEFAULT false,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Games
CREATE TABLE games (
    id VARCHAR(50) PRIMARY KEY,      -- e.g., "2026-04-07_CLE_MEM"
    date DATE NOT NULL,
    home_team VARCHAR(3) REFERENCES teams(id),
    away_team VARCHAR(3) REFERENCES teams(id),
    tipoff_time TIMESTAMPTZ,
    status VARCHAR(15) DEFAULT 'SCHEDULED',  -- SCHEDULED | LIVE | FINAL
    home_score INTEGER,
    away_score INTEGER,
    home_spread DECIMAL(4,1),        -- from sportsbooks
    total_line DECIMAL(5,1)
);

-- Polymarket markets
CREATE TABLE polymarket_markets (
    id SERIAL PRIMARY KEY,
    game_id VARCHAR(50) REFERENCES games(id),
    market_type VARCHAR(15),         -- moneyline | spread | total
    polymarket_slug VARCHAR(100),
    polymarket_condition_id VARCHAR(100),
    yes_price DECIMAL(4,3),
    no_price DECIMAL(4,3),
    volume DECIMAL(12,2),
    liquidity DECIMAL(12,2),
    fetched_at TIMESTAMPTZ DEFAULT NOW()
);

-- Model predictions
CREATE TABLE predictions (
    id SERIAL PRIMARY KEY,
    game_id VARCHAR(50) REFERENCES games(id),
    market_type VARCHAR(15),
    home_adjusted_ortg DECIMAL(5,1),
    home_adjusted_drtg DECIMAL(5,1),
    home_adjusted_nrtg DECIMAL(5,1),
    away_adjusted_ortg DECIMAL(5,1),
    away_adjusted_drtg DECIMAL(5,1),
    away_adjusted_nrtg DECIMAL(5,1),
    projected_spread DECIMAL(5,1),   -- positive = home favored
    projected_total DECIMAL(5,1),
    home_win_probability DECIMAL(4,3),
    spread_cover_probability DECIMAL(4,3),
    over_probability DECIMAL(4,3),
    schedule_adjustment DECIMAL(4,1),
    confidence VARCHAR(10),          -- HIGH | MEDIUM | LOW
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Bets
CREATE TABLE bets (
    id SERIAL PRIMARY KEY,
    game_id VARCHAR(50) REFERENCES games(id),
    prediction_id INTEGER REFERENCES predictions(id),
    market_type VARCHAR(15),
    selection VARCHAR(100),          -- e.g., "CLE -13.5 YES"
    side VARCHAR(3),                 -- "YES" | "NO"
    entry_price DECIMAL(4,3),
    model_probability DECIMAL(4,3),
    edge_at_entry DECIMAL(4,3),
    amount_usd DECIMAL(10,2),
    kelly_fraction DECIMAL(5,4),
    result VARCHAR(5),               -- WIN | LOSS | PUSH | null
    pnl DECIMAL(10,2),
    placed_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

-- Data validation log
CREATE TABLE validation_log (
    id SERIAL PRIMARY KEY,
    check_type VARCHAR(30),          -- RANGE | CROSS_SOURCE | STALENESS | ANOMALY
    severity VARCHAR(10),            -- INFO | WARNING | ERROR
    field VARCHAR(50),
    expected_range VARCHAR(50),
    actual_value VARCHAR(50),
    source VARCHAR(20),
    message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Data Refresh Schedule

| Data | Frequency | Source | Cache TTL |
|------|-----------|--------|-----------|
| Team ratings (ORtg/DRtg/NRtg) | Daily at 6am ET | NBA API + PBP Stats | 24 hours |
| Player on/off splits | Daily at 6am ET | PBP Stats | 24 hours |
| Injury reports | Every 30 min on game days | NBA official + Rotowire | 30 minutes |
| Polymarket prices | Every 5 minutes | Gamma API | 5 minutes |
| Game schedule | Daily at 6am ET | NBA API | 24 hours |
| Standings | Daily at 6am ET | NBA API | 24 hours |
| Sportsbook consensus odds | Every 2 hours on game days | (Future: The Odds API) | 2 hours |

---

## 8. API Specification

### Base URL
```
Production: https://courtedge-api.railway.app/api/v1
Local dev:  http://localhost:8000/api/v1
```

### Key Endpoints

#### `GET /games/today`
Returns all games for today with full analysis.

**Response (this is THE endpoint for AI consumption):**

```json
{
  "date": "2026-04-07",
  "timezone_note": "All times in US Eastern. Operator is UTC+8.",
  "games_count": 8,
  "games": [
    {
      "game_id": "2026-04-07_CLE_MEM",
      "tipoff": "2026-04-07T19:30:00-04:00",
      "tipoff_sgt": "2026-04-08T07:30:00+08:00",
      "venue": "Rocket Mortgage FieldHouse",
      
      "home": {
        "team": "CLE",
        "full_name": "Cleveland Cavaliers",
        "record": "62-18",
        "seed": 1,
        "motivation": "REST_EXPECTED",
        "season_ortg": 118.5,
        "season_drtg": 108.2,
        "season_nrtg": 10.3,
        "adjusted_ortg": 116.1,
        "adjusted_drtg": 110.0,
        "adjusted_nrtg": 6.1,
        "nrtg_delta": -4.2,
        "injuries": [
          {
            "player": "Evan Mobley",
            "status": "OUT",
            "reason": "Rest",
            "nrtg_impact": -3.1
          }
        ],
        "schedule": {
          "is_b2b": false,
          "is_3_in_4": false,
          "rest_days": 2,
          "road_trip_game": 0
        }
      },
      
      "away": {
        "team": "MEM",
        "full_name": "Memphis Grizzlies",
        "record": "48-32",
        "seed": 4,
        "motivation": "FIGHTING",
        "season_ortg": 113.8,
        "season_drtg": 111.5,
        "season_nrtg": 2.3,
        "adjusted_ortg": 113.8,
        "adjusted_drtg": 111.5,
        "adjusted_nrtg": 2.3,
        "nrtg_delta": 0.0,
        "injuries": [],
        "schedule": {
          "is_b2b": true,
          "is_3_in_4": false,
          "rest_days": 0,
          "road_trip_game": 3
        }
      },
      
      "model": {
        "nrtg_differential": 3.8,
        "schedule_adjustment": -2.5,
        "home_court": 3.0,
        "projected_spread": -4.3,
        "projected_total": 221.5,
        "home_win_prob": 0.635,
        "confidence": "MEDIUM"
      },
      
      "markets": {
        "moneyline": {
          "polymarket_home_yes": 0.72,
          "polymarket_home_no": 0.28,
          "model_home_win": 0.635,
          "home_yes_edge": -0.085,
          "home_no_edge": 0.085,
          "best_side": "NO",
          "best_edge": 0.085,
          "verdict": "BUY",
          "kelly_quarter": 0.041,
          "ev_per_dollar": 0.304
        },
        "spread": {
          "line": -8.5,
          "polymarket_home_covers": 0.52,
          "model_home_covers": 0.44,
          "home_yes_edge": -0.08,
          "home_no_edge": 0.08,
          "best_side": "NO",
          "best_edge": 0.08,
          "verdict": "BUY"
        },
        "total": {
          "line": 224.5,
          "polymarket_over": 0.55,
          "model_over": 0.48,
          "over_edge": -0.07,
          "under_edge": 0.07,
          "best_side": "UNDER",
          "best_edge": 0.07,
          "verdict": "BUY"
        }
      },
      
      "data_quality": {
        "ratings_freshness": "FRESH",
        "injury_freshness": "FRESH",
        "price_freshness": "FRESH",
        "cross_source_validated": true,
        "warnings": []
      }
    }
  ],
  
  "top_edges": [
    {
      "game": "CLE vs MEM",
      "market": "moneyline",
      "selection": "MEM wins (NO on CLE)",
      "price": 0.28,
      "model_prob": 0.365,
      "edge": 0.085,
      "verdict": "BUY"
    }
  ]
}
```

#### `GET /games/today/ai-prompt`
Returns a pre-formatted text prompt optimized for pasting into Claude or Gemini.

```
COURTEDGE ANALYSIS — April 7, 2026
====================================

GAME 1: CLE vs MEM | 7:30 PM ET (7:30 AM SGT)
Venue: Rocket Mortgage FieldHouse (CLE home)

LINEUP-ADJUSTED RATINGS:
                  Season NRtg    Adjusted NRtg    Delta
CLE (62-18, #1):    +10.3          +6.1          -4.2  (Mobley OUT - Rest)
MEM (48-32, #4):     +2.3          +2.3           0.0  (Full strength)

SCHEDULE CONTEXT:
CLE: 2 rest days, at home (+3.0)
MEM: Back-to-back (-2.5), road game 3 of trip (-1.0)

MODEL PROJECTION:
NRtg diff: +3.8 → Spread: CLE -4.3 → Win prob: CLE 63.5%
Projected total: 221.5

POLYMARKET EDGES:
Market          Side      Price    Model    Edge     Verdict
Moneyline       MEM       $0.28    36.5%    +8.5%    BUY
Spread -8.5     MEM+8.5   $0.48    56.0%    +8.0%    BUY
Total 224.5     Under     $0.45    52.0%    +7.0%    BUY

TOP RECOMMENDATION: MEM moneyline @ $0.28 (edge: +8.5%, EV: +$0.30/dollar)

[... repeat for each game ...]

====================================
DATA QUALITY: All ratings FRESH (updated 6am ET), injuries updated 30m ago, prices <5m old.
```

#### `POST /bets`
Log a new bet.

#### `GET /bets/history`
Get bet history with P&L and model accuracy stats.

#### `GET /games/{game_id}`
Get detailed analysis for a single game.

#### `GET /teams/{team_id}/ratings`
Get current and historical ratings for a team.

#### `POST /injuries/override`
Manually set a player's status (for when official reports are lagging).

---

## 9. Frontend Specification

### Design Philosophy

**Aesthetic:** Professional analytics terminal. Dark mode. Dense but readable. Inspired by Bloomberg Terminal meets modern sports analytics. NOT a generic Bootstrap dashboard.

**Key design principles:**
- **Data density** — Show the maximum useful information without clutter
- **Color-coded edges** — Green (#00C853) for BUY, Red (#FF1744) for no edge, Amber (#FFD600) for LEAN, white for neutral
- **Interactive** — Hover for details, click to expand game cards
- **Progressive disclosure** — Summary view first, drill into details on click

### Color System (CSS Variables)

```css
:root {
  /* Background layers */
  --bg-primary: #0a0e17;        /* Darkest — page background */
  --bg-secondary: #111827;      /* Card backgrounds */
  --bg-tertiary: #1a2235;       /* Elevated elements, hover states */
  --bg-hover: #1f2937;          /* Interactive hover */

  /* Text */
  --text-primary: #e2e8f0;      /* Primary text */
  --text-secondary: #94a3b8;    /* Secondary/muted text */
  --text-muted: #64748b;        /* Tertiary/disabled */

  /* Edges / Verdicts */
  --edge-strong-buy: #00C853;   /* +12% edge or more */
  --edge-buy: #4CAF50;          /* +6% to +12% */
  --edge-lean: #FFD600;         /* +3% to +6% */
  --edge-no-edge: #78909C;      /* < 3% */
  --edge-avoid: #FF1744;        /* Negative EV */

  /* Accents */
  --accent-blue: #2979FF;       /* Links, interactive elements */
  --accent-purple: #7C4DFF;     /* Model confidence indicators */

  /* Borders */
  --border-subtle: #1e293b;
  --border-active: #334155;

  /* Charts */
  --chart-line: #2979FF;
  --chart-area: rgba(41, 121, 255, 0.1);
}
```

### Typography

```css
/* Use a monospace/technical font for numbers and data */
--font-data: 'JetBrains Mono', 'Fira Code', monospace;
/* Use a clean sans-serif for labels and text */
--font-ui: 'DM Sans', 'Satoshi', sans-serif;
/* Use a condensed font for dense tables */
--font-condensed: 'DM Sans', sans-serif;
```

### Page Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  COURTEDGE                            Apr 7, 2026 | 8:30am SGT │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │
│  [Dashboard]  [Bet Tracker]  [Model Accuracy]  [Settings]       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─ TOP EDGES ─────────────────────────────────────────────┐   │
│  │  🟢 MEM ML @ $0.28 (edge: +8.5%)                       │   │
│  │  🟢 CLE/MEM Under 224.5 @ $0.45 (edge: +7.0%)         │   │
│  │  🟡 BOS -4.5 @ $0.48 (edge: +4.2%)                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ GAME CARDS ────────────────────────────────────────────┐   │
│  │                                                         │   │
│  │  ┌─────────────────────────────────────────────┐       │   │
│  │  │  CLE (62-18) vs MEM (48-32)  |  7:30 PM ET │       │   │
│  │  │                                              │       │   │
│  │  │  ADJUSTED RATINGS                            │       │   │
│  │  │  CLE  NRtg: +10.3 → +6.1  (▼ 4.2)         │       │   │
│  │  │  MEM  NRtg:  +2.3 → +2.3  (─ 0.0)         │       │   │
│  │  │                                              │       │   │
│  │  │  ┌─ INJURIES ─────────────────────────┐     │       │   │
│  │  │  │  CLE: E. Mobley (OUT - Rest)       │     │       │   │
│  │  │  │  MEM: Full strength                 │     │       │   │
│  │  │  └─────────────────────────────────────┘     │       │   │
│  │  │                                              │       │   │
│  │  │  EDGES                                       │       │   │
│  │  │  ML    MEM     $0.28   36.5%   +8.5%  BUY  │       │   │
│  │  │  SPR   MEM+8.5 $0.48   56.0%   +8.0%  BUY  │       │   │
│  │  │  TOT   Under   $0.45   52.0%   +7.0%  BUY  │       │   │
│  │  │                                              │       │   │
│  │  │  [Copy AI Prompt]  [View Details]  [Log Bet] │       │   │
│  │  └─────────────────────────────────────────────┘       │   │
│  │                                                         │   │
│  │  [... more game cards ...]                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ COPY AI PROMPT ────────────────────────────────────────┐   │
│  │  [Copy Full Slate Analysis]  [Copy Single Game]          │   │
│  │  Format: [Claude] [Gemini] [Raw JSON]                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Interactive Elements

**Game Card (collapsed — default view):**
- Team names, records, seeds
- Adjusted NRtg with delta indicator (▲ ▼ ─)
- Key injuries (top 2 by impact)
- Best edge with color-coded verdict badge
- Tipoff time in ET and SGT

**Game Card (expanded — on click):**
- Full injury list with impact ratings
- All three market types (ML, spread, total) with edges
- Schedule context (B2B, rest days, road trip)
- Motivation flags
- Interactive price chart (Polymarket price movement over last 24 hours — Polymarket-style hover tooltip)
- Confidence indicator
- Data quality badges

**"Copy AI Prompt" button:**
- Formats the current game (or full slate) as an optimized text prompt
- Copies to clipboard with one click
- Formats differently for Claude vs Gemini (Claude gets XML-tagged data, Gemini gets plain text)

**Bet Logging Modal:**
- Pre-fills game, market, side, current price, model probability, edge
- User enters: amount, notes
- Auto-calculates Kelly fraction
- Saves to database

**Price Chart (Polymarket-style):**
- Line chart showing YES price over time
- Hover shows exact price and timestamp (tooltip follows cursor — Polymarket style)
- Overlay: model's probability as a dashed horizontal line
- Green fill when market price < model (edge exists), red fill when not

### Responsive Behavior
- **Desktop (primary):** Full dashboard, multi-column game cards
- **Tablet:** Single-column game cards, collapsible sections
- **Mobile:** Simplified cards, swipeable, key info only (edges + verdict)

---

## 10. Prediction Model

### V1: NRtg-Based Simple Model

```python
def predict_game(
    home_adj_nrtg: float,
    away_adj_nrtg: float,
    home_schedule_mod: float,    # e.g., -2.5 for B2B
    away_schedule_mod: float,
    home_court_advantage: float = 3.0
) -> Prediction:
    """
    Core model:
    1. NRtg differential → projected margin (roughly 1:1 mapping)
    2. Add home court advantage (+3.0 points)
    3. Add schedule modifiers
    4. Convert margin → win probability using logistic function

    Calibration constants (from NBA historical data):
    - 1 point of NRtg differential ≈ 1 point of spread
    - 1 point of spread ≈ ~2.5% win probability shift (around 50%)
    - Home court ≈ +3.0 points (has been declining; historically ~3.5)
    """
    
    # Step 1: Raw NRtg differential (positive = home advantage)
    nrtg_diff = home_adj_nrtg - away_adj_nrtg
    
    # Step 2: Add modifiers
    projected_margin = nrtg_diff + home_court_advantage + home_schedule_mod - away_schedule_mod
    
    # Step 3: Margin → Win Probability (logistic function)
    # Calibrated: at margin=0, prob=50%. Each point ≈ 2.5% shift.
    # Using sigma=6.0 (calibrated against historical NBA results)
    import math
    home_win_prob = 1.0 / (1.0 + math.exp(-projected_margin / 6.0))
    
    # Step 4: Projected total (simpler — average of adjusted team paces and efficiencies)
    # This is a rougher estimate; will be improved in V2
    projected_total = estimate_total(home_adj_ortg, home_adj_drtg, away_adj_ortg, away_adj_drtg)
    
    # Step 5: Spread cover probability
    # If spread is CLE -8.5 and we project CLE -4.3, 
    # prob of covering = prob(actual margin > 8.5 given projected margin = 4.3)
    # Using normal distribution with std_dev ≈ 12 points (NBA game-to-game variance)
    from scipy.stats import norm
    spread_cover_prob = 1.0 - norm.cdf(spread_line, loc=projected_margin, scale=12.0)
    
    return Prediction(
        projected_spread=round(projected_margin, 1),
        home_win_prob=round(home_win_prob, 3),
        projected_total=round(projected_total, 1),
        spread_cover_prob=round(spread_cover_prob, 3),
        confidence=calculate_confidence(...)
    )
```

### Model Confidence

Confidence is based on data quality, not model certainty:

| Confidence | Criteria |
|------------|----------|
| HIGH | On/off sample > 200 min for all missing players, cross-source validated, no data warnings |
| MEDIUM | On/off sample 100-200 min, or 1 data warning |
| LOW | On/off sample < 100 min, or multiple data warnings, or key data stale |

### Future Model Improvements (V2+)
- RAPM (Regularized Adjusted Plus-Minus) for player impact values
- Multi-player lineup combination data from PBP Stats
- Machine learning regression on historical game outcomes
- Incorporate betting market movement as a signal
- Player tracking data (shot quality, defensive metrics)

---

## 11. Development Phases & Roadmap

### Phase 1: MVP (Target: 2-3 weeks)
**Goal:** End-to-end pipeline from data ingestion to edge display

| Milestone | Description |
|-----------|-------------|
| M1: Project Setup | Repo structure, DB schema, FastAPI scaffold, Next.js scaffold, CLAUDE.md |
| M2: Data Connectors | NBA API connector, PBP Stats connector (on/off splits), data validation layer |
| M3: Lineup Adjustment Engine | On/off split model, multi-player adjustment, confidence scoring |
| M4: Polymarket Integration | Gamma API connector, market parsing, price caching |
| M5: Prediction Model | NRtg-based model, spread/ML/total projections, edge calculator |
| M6: REST API | `/games/today` endpoint, `/games/today/ai-prompt` endpoint |
| M7: Frontend — Game Cards | Dashboard layout, game cards with adjusted ratings and edges |
| M8: Frontend — AI Prompt | "Copy AI Prompt" button, format selector |
| M9: Integration & Polish | End-to-end test, data validation verification, UI polish |

### Phase 2: Enhanced Analytics (2 weeks after MVP)
- Injury feed auto-refresh with push to lineup engine
- Schedule context engine
- Standings & motivation flags
- Bet tracking UI + model accuracy dashboard
- Polymarket price history chart (interactive, Polymarket-style)

### Phase 3: Model Improvement (Ongoing)
- Add sportsbook consensus odds comparison (The Odds API)
- Implement RAPM-based player impact model
- Multi-player lineup combination data
- Historical model accuracy analysis → calibration improvements

### Phase 4: Pre-Monetization (Future)
- User authentication (email + OAuth)
- Subscription tiers
- Rate limiting for API
- Usage analytics
- Landing page

---

## 12. Claude Code Implementation Guide

This section is specifically for Claude Code — the AI agent that will build this project. Follow these practices for maximum quality and efficiency.

### 12.1 CLAUDE.md Configuration

Create a `CLAUDE.md` at the project root with:

```markdown
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
```

### 12.2 Subagent Architecture

Use Claude Code's subagent pattern to maintain clean context. The orchestrator (main agent) delegates to specialized subagents for each milestone.

**Pattern: Builder → Verifier Feedback Loop**

For each milestone, use TWO subagents:

```
Main Agent (Orchestrator)
│
├── Milestone M2: Data Connectors
│   ├── Builder Subagent
│   │   • Prompt: "Implement NBA API connector and PBP Stats connector 
│   │     in /backend/app/connectors/. Follow the interface defined in 
│   │     /backend/app/connectors/base.py. Include retry logic, timeout 
│   │     handling, and rate limiting. Write to these files: 
│   │     nba_api.py, pbpstats.py. Run tests after implementation."
│   │   • Model: sonnet
│   │   • Tools: Read, Write, Edit, Bash, Grep, Glob
│   │
│   └── Verifier Subagent
│       • Prompt: "Review the data connectors in /backend/app/connectors/.
│       Verify: (1) All external calls have try/except with specific 
│       exceptions, (2) Retry logic uses exponential backoff, (3) Response
│       data passes through validation layer, (4) Unit tests exist and 
│       pass, (5) Mock responses match real API response shapes. 
│       Run: pytest -v tests/connectors/. Report issues with severity."
│       • Model: sonnet
│       • Tools: Read, Bash, Grep, Glob (no Write — verifier is read-only)
│
├── Milestone M3: Lineup Adjustment Engine
│   ├── Builder Subagent
│   └── Verifier Subagent (verify math is correct, edge cases handled)
│
├── ... (repeat for each milestone)
```

**Why this works:**
- Each subagent has its own context window → no pollution of the orchestrator's context
- Builder focuses purely on implementation
- Verifier catches issues the builder missed (test-time compute: same model finds bugs another instance created)
- Orchestrator only sees summaries, keeping its context clean for planning

### 12.3 Subagent Definitions

Create these files in `.claude/agents/`:

**`.claude/agents/builder.md`**
```yaml
---
name: builder
description: Implements features based on specs. Use for coding new modules, connectors, API endpoints, and UI components.
tools: Read, Write, Edit, Bash, Grep, Glob
model: sonnet
---

You are an implementation specialist for the CourtEdge project. You receive a specific implementation task with clear file targets and acceptance criteria.

Your workflow:
1. Read relevant existing code to understand patterns and interfaces
2. Implement the feature following project code standards (see CLAUDE.md)
3. Write unit tests alongside the implementation
4. Run tests and fix any failures
5. Report what you built, files modified, and test results

Rules:
- Follow existing code patterns. Check how similar modules are structured before writing.
- Type hints on every function (Python) and strict TypeScript types.
- Every external API call: try/except, retry with backoff, timeout, validate response.
- Log important events and errors.
- Write tests first if implementing calculation logic (TDD for the prediction model and edge calculator).
```

**`.claude/agents/verifier.md`**
```yaml
---
name: verifier
description: Reviews code for correctness, edge cases, and adherence to standards. Use after builder completes a milestone.
tools: Read, Bash, Grep, Glob
model: sonnet
---

You are a QA specialist for the CourtEdge project. You receive completed code and must verify it meets the requirements.

Your verification checklist:
1. **Correctness**: Does the logic match the PRD specification? Are edge cases handled?
2. **Data Validation**: Does all incoming data pass through validation? Are range checks in place?
3. **Error Handling**: Do all external calls have proper error handling? What happens when an API is down?
4. **Tests**: Do tests exist? Do they pass? Do they cover edge cases? Run: pytest -v or npm test
5. **Type Safety**: Run mypy (Python) or tsc --noEmit (TypeScript). Zero errors.
6. **Code Quality**: Run ruff check (Python) or eslint (TypeScript). Zero warnings.
7. **Math Verification**: For calculation modules (lineup adjustment, edge calculator, prediction model), verify the math with manual examples.

Output format:
- PASS: [what passed]
- FAIL: [what failed, with specific file:line references and expected vs actual]
- WARN: [non-blocking concerns]

You do NOT modify code. You only read and report.
```

**`.claude/agents/researcher.md`**
```yaml
---
name: researcher
description: Investigates APIs, libraries, and external data sources. Use before building connectors to understand API shapes.
tools: Read, Bash, Grep, Glob
model: sonnet
---

You are a research specialist. You investigate external APIs, libraries, and data sources to understand their structure before implementation.

When given an API to research:
1. Make sample requests (with appropriate rate limiting)
2. Document the response shape and key fields
3. Identify rate limits, authentication requirements, and gotchas
4. Write a brief summary with example responses
5. Save findings to /docs/research/{topic}.md

Be thorough but concise. The builder agent will use your findings.
```

### 12.4 Development Workflow Per Milestone

```
1. Orchestrator reads the PRD milestone requirements
2. Orchestrator spawns RESEARCHER subagent if the milestone involves new external APIs
   → Researcher investigates API shapes, saves findings to /docs/research/
3. Orchestrator spawns BUILDER subagent with:
   - Specific implementation task from PRD
   - File targets
   - Acceptance criteria
   - Reference to researcher's findings (if applicable)
4. Builder implements and runs tests
5. Orchestrator spawns VERIFIER subagent with:
   - The same acceptance criteria
   - Instruction to run all tests and checks
6. If verifier reports FAIL:
   → Orchestrator spawns Builder again with verifier's feedback
   → Repeat until verifier reports PASS
7. Orchestrator moves to next milestone
```

### 12.5 Additional Claude Code Best Practices

**Context management:**
- Do manual `/compact` at ~50% context usage, don't wait for auto-compact
- Use `/clear` when switching between milestones
- Delegate all research and investigation to subagents to keep orchestrator context clean
- Use `/rename` to label sessions (e.g., "M3 - Lineup Adjustment Engine")

**Development patterns:**
- Start each milestone by reading relevant existing code
- Write tests alongside code, not after
- Use TDD for all calculation logic (prediction model, edge calculator, Kelly calculator)
- Run linters and type checkers after every implementation
- Commit per-file with descriptive messages

**Error recovery:**
- Use `Esc Esc` or `/rewind` if Claude goes off-track rather than trying to fix in the same context
- If a build/test is failing in a confusing way, start a fresh session

**Model selection:**
- Opus for architecture planning, complex design decisions, and reviewing the overall system
- Sonnet for implementation (builder and verifier subagents)
- Haiku for simple file reading, grep searches, routine tasks

---

## 13. Testing Strategy

### Unit Tests

| Module | What to Test | Framework |
|--------|-------------|-----------|
| Data Connectors | Response parsing, error handling, retry logic (with mocked responses) | pytest + responses/httpx-mock |
| Validation Layer | Range checks, cross-source comparison, anomaly detection | pytest |
| Lineup Adjustment | Single player absence, multi-player, edge cases (all starters out), confidence scoring | pytest |
| Prediction Model | NRtg → spread mapping, win probability calculation, total projection | pytest |
| Edge Calculator | Edge calculation, Kelly fraction, verdict thresholds, both YES and NO sides | pytest |
| API Endpoints | Response shape, error responses, query parameters | pytest + httpx (TestClient) |
| Frontend Components | Game card rendering, edge colors, copy-to-clipboard | Jest + React Testing Library |

### Integration Tests

| Test | Description |
|------|-------------|
| Full pipeline | Mock external APIs → data ingestion → validation → lineup adjustment → prediction → edge calculation → API response |
| Injury → recalculation | Set player OUT → verify adjusted ratings change → verify edge recalculates |
| Data staleness | Advance clock → verify staleness flags appear |
| Cross-source disagreement | Feed conflicting data from NBA API vs PBP Stats → verify validation catches it |

### Manual Test Scenarios

| Scenario | Steps |
|----------|-------|
| Game night flow | Open dashboard → verify all games show → verify injuries are current → check edges → copy AI prompt → verify format |
| Star player ruled OUT | Add player to OUT list → verify team ratings adjust → verify edges update |
| All starters out | Set all 5 starters OUT → verify model handles gracefully (confidence = LOW, ratings still reasonable) |
| Polymarket API down | Kill Polymarket connection → verify dashboard shows stale warning, doesn't crash |
| No games tonight | Verify dashboard shows empty state gracefully |

---

## 14. Deployment & Infrastructure

### Local Development

```bash
# Prerequisites: Python 3.11+, Node.js 18+, PostgreSQL (or Docker)

# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Configure DB URL, etc.
alembic upgrade head   # Run migrations
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
cp .env.example .env.local  # Configure API URL
npm run dev  # Runs on port 3000
```

### Production (Railway + Vercel)

**Railway (Backend + Database):**
- Python FastAPI service
- PostgreSQL add-on (free tier: 1GB, sufficient for MVP)
- Redis add-on (optional, for caching — can use in-memory for MVP)
- Environment variables for API keys, DB URL
- APScheduler runs within the FastAPI process

**Vercel (Frontend):**
- Next.js deployment (automatic from Git push)
- Environment variable: `NEXT_PUBLIC_API_URL=https://courtedge-api.railway.app`

### Environment Variables

```env
# Backend
DATABASE_URL=postgresql://...
REDIS_URL=redis://...  (optional for MVP)
ENVIRONMENT=production  # development | staging | production
LOG_LEVEL=INFO
CORS_ORIGINS=https://courtedge.vercel.app

# API keys (when needed)
# ODDS_API_KEY=...  (Phase 3)
# CLEANING_THE_GLASS_COOKIE=...  (Phase 3)

# Frontend
NEXT_PUBLIC_API_URL=https://courtedge-api.railway.app/api/v1
```

---

## 15. Future Considerations

### Monetization Architecture (Don't Build Now, Design For)
- API rate limiting middleware (currently unlimited, add tiers later)
- User identification middleware (currently anonymous, add auth later)
- Feature flags system (gate advanced features behind subscription tiers)
- The frontend and API should have clear separation so a public/free version and a premium version can coexist

### Live Betting (Future)
- WebSocket connection for real-time Polymarket price updates
- Live game score integration
- In-game model adjustments (e.g., if a player gets injured mid-game)

### Additional Data Sources (Future)
- Cleaning the Glass (paid, excellent garbage-time filtering)
- The Odds API (sportsbook consensus odds)
- Synergy Stats (play type data)
- NBA player tracking data (shot quality, defensive metrics)

### Model Evolution Path
```
V1: Additive on/off splits → NRtg-based linear model
V2: RAPM player impact values → more accurate multi-player adjustment
V3: Lineup combination data → specific 5-man unit performance
V4: ML model trained on historical outcomes → learns non-linear effects
V5: Ensemble model → combines V2-V4 with market movement signals
```

---

## Appendix A: Data Source Quick Reference

| Source | URL | Free? | Key Data | Rate Limits |
|--------|-----|-------|----------|-------------|
| NBA API | `stats.nba.com` | Yes | Team/player stats, game schedule, injury report | ~60 req/min (unofficial, can be flaky) |
| PBP Stats | `pbpstats.com/api` | Yes | On/off splits, lineup data, play-by-play derived stats | Be respectful, ~30 req/min |
| Basketball Reference | `basketball-reference.com` | Yes | Box scores, game logs, historical data | Scraping required, be gentle |
| Polymarket Gamma | `gamma-api.polymarket.com` | Yes | Market prices, volume, liquidity | No official limits, poll every 5m |
| Rotowire | `rotowire.com` | Partial | Injury updates, news | Scraping required |

## Appendix B: Polymarket Market Slug Conventions

```
NBA game slugs follow this pattern:
nba-{away_abbrev}-{home_abbrev}-{YYYY-MM-DD}

Examples:
- nba-det-orl-2026-04-06  (Detroit @ Orlando, April 6, 2026)
- nba-mem-cle-2026-04-07  (Memphis @ Cleveland, April 7, 2026)

Market types within a game:
- Moneyline: "Will [Team] win?"
- Spread: "Will [Team] cover [+/-X.5]?"
- Total: "Will the total be over [X.5]?"

Each market has:
- condition_id: unique identifier
- outcome_prices: [YES_price, NO_price]
- These sum to ~$1.00 (minus Polymarket's small spread)
```

## Appendix C: Team Abbreviation Mapping

```
ATL, BOS, BKN, CHA, CHI, CLE, DAL, DEN, DET, GSW,
HOU, IND, LAC, LAL, MEM, MIA, MIL, MIN, NOP, NYK,
OKC, ORL, PHI, PHX, POR, SAC, SAS, TOR, UTA, WAS
```

---

**END OF PRD**

*This document is the source of truth for the CourtEdge project. All implementation decisions should reference this PRD. If a question arises that isn't covered here, flag it for discussion before implementing.*
