"""
Prediction Model — V2: Pace-Adjusted, Calibrated, Late-Season Aware.

Improvements over V1:
  - Multiplicative total estimation using per-team pace (not pace=100 hardcode)
  - Proper matchup pace calculation: geometric mean of both teams' pace
  - Late-season scoring bias correction (+1.0 pts for March/April)
  - GAME_STD_DEV tuned from 12.0 → 11.5 (tighter probabilities, fewer coin-flips)
  - Over/under standard deviation separate from spread stdev (backtested
    σ_total ≈ 19)
  - Totals level tracks the current season's league scoring, not last season's
  - Motivation modifier feeds into projected margin for end-of-season games
  - Spread cover uses proper continuous CDF (handles positive/negative lines)
"""

from __future__ import annotations

import math
from datetime import date

from loguru import logger
from scipy.stats import norm

from app.schemas.prediction import GamePrediction


# ─── Calibration Constants ──────────────────────────────────────────
# Tuned against 2024-25 and early 2025-26 historical data.

HOME_COURT_ADVANTAGE = 3.0         # points; NBA long-run average ≈ 2.8-3.2
SPREAD_TO_WIN_PROB_SIGMA = 5.8     # logistic function width; lower = more decisive
                                    # (V1 was 6.0; 5.8 better calibrates 60-70% picks)
GAME_STD_DEV = 11.5                # spread variance; NBA actual ≈ 11-12
TOTAL_STD_DEV = 19.0               # σ of (actual total − projected total).  Backtest
                                    # 2018-19…2025-26 (7.4k games, as-of-date ratings):
                                    # residual sd 18.7-19.6 per season; σ=19 maximises
                                    # likelihood and matches the >5 / >10 pt tail rates.
                                    # The old 13.5 made 3-5 pt gaps look like 12%+ edges.
LEAGUE_AVG_ORTG = 112.7            # 2025-26 league average ORtg (fallback only)
LEAGUE_AVG_PACE = 102.0            # 2025-26 league average pace (fallback only)

# ─── Totals calibration ─────────────────────────────────────────────
# ORtg × pace from teamestimatedmetrics is per 48 minutes, so league-average
# inputs reproduce the regulation scoring level only.  Overtime (~5% of games,
# ~+20 pts each) plus estimated-metric shrinkage put real totals 1.1-1.9 pts
# higher every season 2017-18…2025-26 (mean 1.4).
TOTAL_OT_ADJUSTMENT = 1.4

# The league scoring level moves season to season (2017-18 → 2025-26:
# +9.5, +0.8, +1.2, −2.9, +7.7, −0.6, −0.7, +3.7 pts; mean +2.3).  Before any
# current-season games the level is last season's plus this drift.
SEASON_SCORING_DRIFT = 2.0

# League-games at which the current season's own scoring level gets 50%
# weight.  The per-team rating blend (K=15 team games) is far too slow for the
# league level: it kept ≥15% of last season's level all year, which ran every
# total 3-6 pts low in seasons where scoring rose (2018-19, 2022-23, 2025-26).
LEAGUE_LEVEL_K_GAMES = 20.0

# Late-season scoring bias: March/April games score higher than the
# season-to-date average (playoff urgency, tanking, garbage time).  Backtested
# at half the old 2.0: with the level fix above, the full 2.0 over-projected
# 2023-24…2025-26 by 0.3-2 pts.
LATE_SEASON_TOTAL_BIAS = 1.0       # additive points for games in March/April

# Motivation impact on margin (points)
MOTIVATION_MARGIN_ADJUSTMENTS = {
    # (home_motivation, away_motivation) → margin adjustment for home team
    "DESPERATE": +1.5,      # desperate teams try harder → bonus
    "FIGHTING": +0.5,       # actively competing → small bonus
    "NEUTRAL": 0.0,
    "REST_EXPECTED": -2.0,  # may rest key players → penalty
}


# ─── Schedule Adjustments ───────────────────────────────────────────
SCHEDULE_ADJUSTMENTS = {
    "b2b": -2.5,              # Back-to-back: 2nd game in 2 nights
    "3_in_4": -3.5,           # 3rd game in 4 nights
    "4_in_6": -4.0,           # 4th game in 6 nights
    "road_trip_extra": -1.0,  # Per game beyond 3rd consecutive road game
    "rest_advantage": 1.5,    # Per extra rest day (max +3.0)
    "home_court": HOME_COURT_ADVANTAGE,
    "travel_coast": -1.5,     # Coast-to-coast travel (>2000 mi)
    "travel_medium": -0.5,    # Medium distance travel (>500 mi)
}


def calculate_schedule_modifier(
    is_b2b: bool = False,
    is_3_in_4: bool = False,
    is_4_in_6: bool = False,
    rest_days: int = 1,
    road_trip_game: int = 0,
    opponent_rest_days: int = 1,
    travel_distance_miles: float = 0.0,
) -> float:
    """
    Calculate schedule-based point adjustment for a team.
    Returns a modifier to add to the projected spread (negative = disadvantage).
    """
    modifier = 0.0

    # Fatigue adjustments (take the worst applicable)
    if is_4_in_6:
        modifier += SCHEDULE_ADJUSTMENTS["4_in_6"]
    elif is_3_in_4:
        modifier += SCHEDULE_ADJUSTMENTS["3_in_4"]
    elif is_b2b:
        modifier += SCHEDULE_ADJUSTMENTS["b2b"]

    # Road trip penalty (beyond 3rd game)
    if road_trip_game > 3:
        modifier += SCHEDULE_ADJUSTMENTS["road_trip_extra"] * (road_trip_game - 3)

    # Rest advantage
    rest_diff = rest_days - opponent_rest_days
    if rest_diff > 0:
        rest_bonus = min(rest_diff * SCHEDULE_ADJUSTMENTS["rest_advantage"], 3.0)
        modifier += rest_bonus

    # Travel distance
    if travel_distance_miles > 2000:
        modifier += SCHEDULE_ADJUSTMENTS["travel_coast"]
    elif travel_distance_miles > 500:
        modifier += SCHEDULE_ADJUSTMENTS["travel_medium"]

    return round(modifier, 1)


def _calculate_motivation_modifier(
    home_motivation: str,
    away_motivation: str,
) -> float:
    """
    Motivation-based margin adjustment.

    If home team is DESPERATE and away is REST_EXPECTED, home gets up to +3.5.
    If reversed, home loses up to -3.5.  Symmetric around both teams.
    """
    home_mod = MOTIVATION_MARGIN_ADJUSTMENTS.get(home_motivation, 0.0)
    away_mod = MOTIVATION_MARGIN_ADJUSTMENTS.get(away_motivation, 0.0)
    return home_mod - away_mod


def predict_game(
    home_adj_nrtg: float,
    away_adj_nrtg: float,
    home_adj_ortg: float,
    home_adj_drtg: float,
    away_adj_ortg: float,
    away_adj_drtg: float,
    home_schedule_mod: float = 0.0,
    away_schedule_mod: float = 0.0,
    home_court_advantage: float = HOME_COURT_ADVANTAGE,
    spread_line: float | None = None,
    total_line: float | None = None,
    home_pace: float = LEAGUE_AVG_PACE,
    away_pace: float = LEAGUE_AVG_PACE,
    home_motivation: str = "NEUTRAL",
    away_motivation: str = "NEUTRAL",
    game_date: date | None = None,
    league_ortg: float | None = None,
    league_pace: float | None = None,
    baseline_total: float | None = None,
) -> GamePrediction:
    """
    Core prediction model (V2):
    1. NRtg differential → projected margin
    2. Add home court, schedule, motivation modifiers
    3. Convert margin → win probability (logistic function, σ=5.8)
    4. Estimate total via multiplicative pace-adjusted formula
    5. Apply late-season bias correction
    6. Calculate spread cover probability (σ=11.5)
    7. Calculate over probability (σ=TOTAL_STD_DEV)

    league_ortg / league_pace / baseline_total come from
    league_scoring_baseline(); without them the total uses the static league
    averages (see estimate_total).
    """
    # Step 1: Raw NRtg differential (positive = home advantage)
    nrtg_diff = home_adj_nrtg - away_adj_nrtg

    # Step 2: Add modifiers
    schedule_adj = home_schedule_mod - away_schedule_mod
    motivation_adj = _calculate_motivation_modifier(home_motivation, away_motivation)
    projected_margin = nrtg_diff + home_court_advantage + schedule_adj + motivation_adj

    # Step 3: Margin → Win Probability (logistic function)
    home_win_prob = 1.0 / (1.0 + math.exp(-projected_margin / SPREAD_TO_WIN_PROB_SIGMA))

    # Step 4: Projected total (pace-adjusted multiplicative method)
    projected_total = estimate_total(
        home_adj_ortg, home_adj_drtg, away_adj_ortg, away_adj_drtg,
        home_pace=home_pace, away_pace=away_pace,
        league_ortg=league_ortg, league_pace=league_pace,
        baseline_total=baseline_total,
    )

    # Step 5: Late-season scoring bias
    if game_date and game_date.month in (3, 4):
        projected_total += LATE_SEASON_TOTAL_BIAS
    elif game_date and game_date.month in (1, 2):
        projected_total += LATE_SEASON_TOTAL_BIAS * 0.5  # partial effect mid-season

    # Step 6: Spread cover probability (σ = GAME_STD_DEV)
    spread_cover_prob = 0.5
    if spread_line is not None:
        # spread_line: negative means home favored (e.g. -6.5)
        # Home covers if actual_margin > |spread_line|
        # P(margin > -spread_line) = P(margin - projected_margin > -spread_line - projected_margin)
        # = 1 - Φ((-spread_line - projected_margin) / σ)
        # Equivalently: P(home covers) = Φ((projected_margin + spread_line) / σ)
        # For spread_line = -6.5 and margin = 8: Φ((8 + (-6.5)) / 11.5) = Φ(0.13)
        spread_cover_prob = norm.cdf(
            (projected_margin + spread_line) / GAME_STD_DEV
        )

    # Step 7: Over probability (σ = TOTAL_STD_DEV — wider than spread variance)
    over_prob = 0.5
    if total_line is not None:
        over_prob = 1.0 - norm.cdf(
            total_line, loc=projected_total, scale=TOTAL_STD_DEV
        )

    confidence = "MEDIUM"

    prediction = GamePrediction(
        nrtg_differential=round(nrtg_diff, 1),
        schedule_adjustment=round(schedule_adj + motivation_adj, 1),
        home_court=home_court_advantage,
        projected_spread=round(-projected_margin, 1),  # Negative = home favored
        projected_total=round(projected_total, 1),
        home_win_prob=round(home_win_prob, 3),
        spread_cover_prob=round(spread_cover_prob, 3),
        over_prob=round(over_prob, 3),
        confidence=confidence,
    )

    logger.info(
        f"Prediction: NRtg diff={nrtg_diff:.1f}, margin={projected_margin:.1f} "
        f"(sched={schedule_adj:+.1f}, motiv={motivation_adj:+.1f}), "
        f"win prob={home_win_prob:.3f}, spread={prediction.projected_spread}, "
        f"total={projected_total:.1f} (pace={home_pace:.0f}/{away_pace:.0f}), "
        f"spread_cover={spread_cover_prob:.3f}, over={over_prob:.3f}"
    )

    return prediction


def estimate_total(
    home_ortg: float,
    home_drtg: float,
    away_ortg: float,
    away_drtg: float,
    home_pace: float = LEAGUE_AVG_PACE,
    away_pace: float = LEAGUE_AVG_PACE,
    league_ortg: float | None = None,
    league_pace: float | None = None,
    baseline_total: float | None = None,
) -> float:
    """
    Estimate game total points: league scoring level × matchup factor.

      matchup_pace = geometric_mean(home_pace, away_pace)
      efficiency   = (home_ortg × away_drtg + away_ortg × home_drtg) / (2 × league_ortg²)
      total        = baseline_total × efficiency × matchup_pace / league_pace
                     + TOTAL_OT_ADJUSTMENT

    league_ortg / league_pace are the league averages of the ratings passed in,
    so the ratings only say how far a matchup sits from average.  The level
    itself comes from baseline_total (league_scoring_baseline), which tracks the
    current season's scoring much faster than the per-team rating blend does.
    Without a baseline the ratings' own level is used (2 × ORtg × pace / 100).

    Geometric mean for pace is more accurate than arithmetic mean because
    pace is a rate, and a very slow team (BOS 98) vs a very fast team
    (MIA 106) doesn't play at 102 — the slow team's half-court style
    pulls pace down more than the fast team pushes it up.
    """
    league_ortg = league_ortg or LEAGUE_AVG_ORTG
    league_pace = league_pace or LEAGUE_AVG_PACE
    if baseline_total is None:
        baseline_total = 2.0 * league_ortg * league_pace / 100.0

    matchup_pace = math.sqrt(home_pace * away_pace)

    # Multiplicative efficiency: two above-average offenses meeting two
    # below-average defenses compound rather than add.
    efficiency = (home_ortg * away_drtg + away_ortg * home_drtg) / (2.0 * league_ortg ** 2)

    total = baseline_total * efficiency * (matchup_pace / league_pace) + TOTAL_OT_ADJUSTMENT

    return round(total, 1)


def league_scoring_baseline(
    current: dict[str, dict[str, float]],
    prior: dict[str, dict[str, float]],
    blended: dict[str, dict[str, float]],
    k_games: float = LEAGUE_LEVEL_K_GAMES,
    drift: float = SEASON_SCORING_DRIFT,
) -> dict[str, float]:
    """League scoring level for estimate_total, from team rating tables.

    current / prior: raw per-team ratings {"ortg", "drtg", "pace", "gp"?} for
    this season and last.  blended: the ratings actually fed to the model.

    Returns:
      league_ortg / league_pace: averages of the blended ratings (what the
        matchup factor is measured against).
      baseline_total: average-matchup regulation total —
        w × this season's level + (1 − w) × (last season's level + drift),
        w = league games / (league games + k_games).
      level_weight: w.
    """
    def mean(rows: list[dict[str, float]], key: str, weights: list[float] | None = None) -> float | None:
        vals = [(float(r[key]), w) for r, w in zip(rows, weights or [1.0] * len(rows)) if r.get(key) is not None]
        total_w = sum(w for _, w in vals)
        return sum(v * w for v, w in vals) / total_w if total_w > 0 else None

    def level(ortg: float | None, pace: float | None) -> float | None:
        return 2.0 * ortg * pace / 100.0 if ortg is not None and pace is not None else None

    blended_rows = list(blended.values())
    league_ortg = mean(blended_rows, "ortg") or LEAGUE_AVG_ORTG
    league_drtg = mean(blended_rows, "drtg") or league_ortg
    league_ortg = (league_ortg + league_drtg) / 2.0
    league_pace = mean(blended_rows, "pace") or LEAGUE_AVG_PACE

    prior_rows = list(prior.values())
    prior_level = level(mean(prior_rows, "ortg"), mean(prior_rows, "pace"))
    if prior_level is None:
        prior_level = level(LEAGUE_AVG_ORTG, LEAGUE_AVG_PACE)
    prior_level += drift

    cur_rows = [r for r in current.values() if float(r.get("gp", 0) or 0) > 0]
    gps = [float(r["gp"]) for r in cur_rows]
    current_level = level(mean(cur_rows, "ortg", gps), mean(cur_rows, "pace", gps))
    league_games = sum(gps) / 2.0
    w = league_games / (league_games + k_games) if current_level is not None and k_games > 0 else 0.0

    baseline = w * current_level + (1.0 - w) * prior_level if w > 0 else prior_level
    return {
        "league_ortg": round(league_ortg, 2),
        "league_pace": round(league_pace, 2),
        "baseline_total": round(baseline, 2),
        "level_weight": round(w, 3),
    }


def margin_to_win_probability(margin: float) -> float:
    """Convert a projected margin to win probability using logistic function."""
    return 1.0 / (1.0 + math.exp(-margin / SPREAD_TO_WIN_PROB_SIGMA))


def win_probability_to_margin(prob: float) -> float:
    """Convert a win probability back to projected margin."""
    if prob <= 0 or prob >= 1:
        return 0.0
    return -SPREAD_TO_WIN_PROB_SIGMA * math.log((1.0 / prob) - 1.0)
