# CourtEdge Betting Cheatsheet

> Your morning routine for Polymarket NBA edge detection.
> Games tip off 7:00-10:30am SGT. Check dashboard at **6:45am SGT**.

---

## The 5-Minute Pre-Game Routine

```
6:45 AM SGT  →  Open dashboard, scan summary table
6:50 AM      →  Check injury report (anyone new OUT?)
6:55 AM      →  Place bets on Tier 1 & 2 edges
7:00 AM      →  Games start. Monitor live tab.
```

### Step 1: Read the Summary Table (top of dashboard)

Look at the **Edge** column. Only care about:
- **STRONG BUY** (edge > 15%) — your bread and butter
- **BUY** (edge 8-15%) — solid if the teams are real (not tanking)

**Skip** everything else. LEANs and NO EDGEs are noise.

### Step 2: Apply the Filters

Before placing any STRONG BUY, run it through these 3 filters:

| Filter | Rule | Why |
|--------|------|-----|
| **Confidence** | Skip if `LOW` confidence | Means too many injuries, model is guessing |
| **Tank Check** | Skip if both teams < 25 wins | G-league players = coin flip regardless of model |
| **Line Sanity** | If total line is within 3pts of model, skip | Not enough margin of safety |

### Step 3: Size Your Bets

| Tier | Criteria | Bet Size |
|------|----------|----------|
| **Tier 1** | STRONG BUY + HIGH/MED confidence + real teams | 3-5% of bankroll |
| **Tier 2** | BUY + any confidence, or STRONG BUY + LOW confidence | 1-2% of bankroll |
| **Tier 3** | LEAN or tank-bowl STRONG BUY | Skip or $1 tracker bet |

---

## What to Bet: Priority Order

Based on Day 1 results and model backtesting:

### 1. TOTALS (Best Edge) ★★★★★

Your model's strongest suit. Day 1: **2W-1L on totals**.

**Why it works**: The pace-adjusted multiplicative formula is more accurate than
Polymarket's crowd wisdom for scoring projections. Late-season bias (+2pts for
March/April) catches lines that haven't adjusted.

**When to bet**:
- Model projected total is **5+ points away** from the line → STRONG BUY
- Model projected total is **3-5 points away** → BUY, bet smaller

**Example tonight**: BOS@NYK Over 216.5 — model says 226.6. That's **10 points**
above the line. This is as good as it gets.

### 2. SPREADS (Good Edge) ★★★★

Day 1: **3W-2L on spreads**.

**Why it works**: Injury-adjusted NRtg differential catches mispriced spreads,
especially when star players are OUT and Polymarket hasn't fully adjusted.

**When to bet**:
- Edge > 15% on a spread → bet it
- The larger the spread, the more likely the model is right (big underdogs
  cover more than Polymarket thinks)

**When to skip**:
- Edge < 8% — not enough margin
- Both teams tanking — irrelevant who covers

### 3. MONEYLINES (Use Carefully) ★★★

Day 1: **0W-2L on MLs**. Both were underdog MLs — very risky.

**Rules for MLs**:
- Only bet ML if model probability > 65% AND price < 60¢
- This means you're getting a favorite at a discount
- **NEVER** bet an underdog ML unless the edge is > 30% (and even then, size small)
- Underdog MLs are high-variance: you'll lose 3 out of 4, and the wins need
  to pay enough to compensate

**Example tonight**: GSW ML at 62¢, model says 72%. Edge +9.2%. This is a good
ML bet — you're buying a favorite slightly below fair value.

**Anti-example**: BOS ML at 36¢ yesterday = betting against the model (model said
NYK 76%). This is burning money.

---

## The NEVER List

| Rule | Why |
|------|-----|
| **Never bet against the model** | If model says 27%, don't buy at 90¢. You're fighting your own system. |
| **Never bet LEANs** | < 8% edge = no margin of safety. One bad bounce and you lose. Day 1: 0W-1L on LEANs. |
| **Never bet tank bowls big** | CHI@WAS, IND@BKN type games. The model adjusts for injuries but can't predict which G-leaguer has a career night. |
| **Never chase losses** | If you lose 2 in a row, don't double up. Stick to Kelly sizing. |
| **Never bet more than 5% on one game** | Even STRONG BUY can lose. Diversify across 3-5 bets per night. |

---

## Live Game Strategy

Once games tip off, your dashboard shows live probabilities. Here's how to use them:

### When to Watch (Not Bet)
- **First half**: The model blends pre-game with live score. Just monitor.
- If your pre-game bet is tracking well (model prob going up) → relax.
- If it's going badly → don't panic. NBA has 12-0 runs all the time.

### When to Act Live
- **Q3 mid-game**: If you see a new edge developing (pre-game prob was 65%,
  now live says 85% but Polymarket is still at 70¢) → this is a live edge.
  Polymarket is slow to update during games.
- **Injury during game**: If a star gets hurt mid-game, the model adjusts
  but Polymarket doesn't. This is your biggest live edge.

### When to Cash Out (Sell Your Position)
- If you bought at 40¢ and it's now trading at 75¢ in Q3 → you can sell
  for guaranteed +35¢ profit instead of risking a comeback.
- **Rule of thumb**: If live win prob > 90% and you can sell at 85¢+,
  take the guaranteed profit.

---

## Tonight's Picks (Apr 9 ET / Apr 10 SGT)

### Tier 1 — High Conviction

| Game | Market | Pick | Poly | Model | Edge | Why |
|------|--------|------|------|-------|------|-----|
| BOS@NYK | Total | **Over 216.5** | 40¢ | 77% | +37.8% | Line is 10pts below model. BOS/NYK are elite offenses. Even without Brown. |
| LAL@GSW | Total | **Over 225.5** | 50¢ | 71% | +20.8% | Model says 233. LAL still high-pace even without Doncic. GSW at home = effort. |

### Tier 2 — Good Edge

| Game | Market | Pick | Poly | Model | Edge | Why |
|------|--------|------|------|-------|------|-----|
| LAL@GSW | ML | **Warriors** | 62¢ | 72% | +9.2% | LAL missing Doncic/Smart/Hayes. GSW desperate for play-in. |
| BOS@NYK | ML | **Knicks** | 64¢ | 76% | +11.5% | BOS without Brown. NYK at home, fighting for seeding. |
| MIA@TOR | Total | **Under 236.5** | 48¢ | 64% | +15.7% | Model says 231.6. Line is 5pts above projection. |

### Skip Tonight

| Game | Why |
|------|-----|
| CHI@WAS | Tank bowl. Both teams missing everyone. LOW confidence. Model says 50% edge but it's noise. |
| PHI@HOU | No meaningful edge on any market. |
| IND@BKN | Tank bowl. Big model edge but both teams are 20-win garbage. |

---

## Bankroll Management

For a $100 starting bankroll:

| Tier | Bet Size | Tonight |
|------|----------|---------|
| Tier 1 | $3-5 each | BOS@NYK Over ($5), LAL@GSW Over ($4) |
| Tier 2 | $1-2 each | GSW ML ($2), NYK ML ($2), MIA@TOR Under ($2) |
| Max tonight | | $15 total (15% of bankroll) |

**Kelly Criterion**: The model calculates optimal Kelly% for each bet. Use
**quarter-Kelly** (divide by 4) to survive variance. The Kelly column on the
dashboard tells you the full Kelly — divide by 4 for your actual bet size.

---

## Daily Tracking Checklist

After games finish:

- [ ] Check `/history` page — did model predictions match actuals?
- [ ] Check `/bets` page — update results (WIN/LOSS)
- [ ] Note which market types won (totals? spreads? MLs?)
- [ ] Note if LOW confidence bets were profitable (probably not)
- [ ] Adjust bankroll for tomorrow

### What We're Tracking (Model v2, Week 1)

| Metric | Day 1 (Apr 8) | Day 2 (Apr 9) | Running |
|--------|--------------|--------------|---------|
| Record | 5W-5L | — | — |
| PnL | +$1.97 | — | — |
| Totals | 2W-1L (67%) | — | — |
| Spreads | 3W-2L (60%) | — | — |
| MLs | 0W-2L (0%) | — | — |
| Anti-system | 0W-1L | — | — |

---

## Quick Reference: Reading the Dashboard

```
┌─ AWAY (record) @ HOME (record)  [SCHEDULED / LIVE Q3 5:47 / FINAL]
│
│  Win Prob Bar:  AWAY 35% ████████░░░░░░░░░░░░ 65% HOME
│                 Pre-game: HOME 65%  |  Live: HOME 72%
│
│  NRtg: HOME +5.2 → +3.1 (▼2.1)    AWAY -1.0 → -3.5 (▼2.5)
│        season    adjusted  (injury)
│
│  Markets:
│    ML:     HOME 62¢ vs AWAY 38¢  →  Model: HOME 72%  →  BUY +9.2%
│    Spread: HOME -4.5 (50¢/50¢)  →  Model: 53%       →  LEAN +3.6%
│    Total:  O/U 225.5 (50¢/50¢)  →  Model: 71% over  →  STRONG BUY +20.8%
│
│  ✅ BET: Total Over (STRONG BUY)
│  ✅ BET: ML (BUY, if price holds)
│  ❌ SKIP: Spread (LEAN, not enough edge)
└─
```

**What the numbers mean**:
- **Poly price** (62¢) = implied probability the market assigns
- **Model probability** (72%) = what CourtEdge thinks the true probability is
- **Edge** (+9.2%) = model prob minus market price. Positive = underpriced = bet.
- **Kelly%** = optimal bet size as % of bankroll. Use quarter-Kelly in practice.
- **NRtg adjusted** = team strength after removing injured players' impact

---

## The One Rule

> **Only bet when the model says STRONG BUY or BUY, the confidence is
> MEDIUM or HIGH, and you're betting WITH the model — never against it.**

Everything else is entertainment, not edge.

---

*Last updated: Apr 10, 2026. Model v2 (pace-adjusted, calibrated, late-season aware).*
*Track results daily. Adjust after 2 weeks of data.*
