"""
Prediction Model — NRtg-based V1 model.
Converts adjusted ratings to win probability, projected spread, and total.
"""

from __future__ import annotations

import math

from loguru import logger
from scipy.stats import norm

from app.schemas.prediction import GamePrediction


# Calibration constants (from NBA historical data)
HOME_COURT_ADVANTAGE = 3.0
SPREAD_TO_WIN_PROB_SIGMA = 6.0  # logistic function width parameter
GAME_STD_DEV = 12.0  # NBA game-to-game scoring variance (points)

# Schedule impact adjustments (points)
SCHEDULE_ADJUSTMENTS = {
    "b2b": -2.5,          # Back-to-back: 2nd game in 2 nights
    "3_in_4": -3.5,       # 3rd game in 4 nights
    "4_in_6": -4.0,       # 4th game in 6 nights
    "road_trip_extra": -1.0,  # Per game beyond 3rd consecutive road game
    "rest_advantage": 1.5,    # Per extra rest day (max +3.0)
    "home_court": HOME_COURT_ADVANTAGE,
    "travel_coast": -1.5,     # Coast-to-coast travel
    "travel_medium": -0.5,    # Medium distance travel
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
) -> GamePrediction:
    """
    Core prediction model:
    1. NRtg differential → projected margin
    2. Add home court advantage (+3.0 points)
    3. Add schedule modifiers
    4. Convert margin → win probability (logistic function)
    5. Project total points
    6. Calculate spread cover probability
    """
    # Step 1: Raw NRtg differential (positive = home advantage)
    nrtg_diff = home_adj_nrtg - away_adj_nrtg

    # Step 2: Add modifiers
    schedule_adj = home_schedule_mod - away_schedule_mod
    projected_margin = nrtg_diff + home_court_advantage + schedule_adj

    # Step 3: Margin → Win Probability (logistic function)
    # Calibrated: at margin=0, prob=50%. Each point ≈ 2.5% shift.
    home_win_prob = 1.0 / (1.0 + math.exp(-projected_margin / SPREAD_TO_WIN_PROB_SIGMA))

    # Step 4: Projected total
    projected_total = estimate_total(
        home_adj_ortg, home_adj_drtg, away_adj_ortg, away_adj_drtg
    )

    # Step 5: Spread cover probability (if line is available)
    spread_cover_prob = 0.5  # default
    if spread_line is not None:
        # Prob of home team covering the spread
        # If spread is -8.5 (home favored), we need margin > 8.5
        spread_cover_prob = 1.0 - norm.cdf(
            abs(spread_line), loc=abs(projected_margin), scale=GAME_STD_DEV
        )
        if spread_line > 0:
            # If home is underdog (positive spread), flip the calculation
            spread_cover_prob = norm.cdf(
                spread_line, loc=projected_margin, scale=GAME_STD_DEV
            )

    # Step 6: Over probability (if total line is available)
    over_prob = 0.5  # default
    if total_line is not None:
        over_prob = 1.0 - norm.cdf(
            total_line, loc=projected_total, scale=GAME_STD_DEV
        )

    # Determine confidence
    confidence = "MEDIUM"  # Default; will be overridden by lineup confidence

    prediction = GamePrediction(
        nrtg_differential=round(nrtg_diff, 1),
        schedule_adjustment=round(schedule_adj, 1),
        home_court=home_court_advantage,
        projected_spread=round(-projected_margin, 1),  # Negative = home favored
        projected_total=round(projected_total, 1),
        home_win_prob=round(home_win_prob, 3),
        confidence=confidence,
    )

    logger.info(
        f"Prediction: NRtg diff={nrtg_diff:.1f}, margin={projected_margin:.1f}, "
        f"win prob={home_win_prob:.3f}, spread={prediction.projected_spread}, "
        f"total={projected_total:.1f}"
    )

    return prediction


def estimate_total(
    home_ortg: float,
    home_drtg: float,
    away_ortg: float,
    away_drtg: float,
    league_avg_pace: float = 100.0,
) -> float:
    """
    Estimate game total points.

    Method: Average the expected points per 100 possessions for each team,
    then scale by expected pace.

    home_points ≈ (home_ortg + away_drtg) / 2 * pace / 100
    away_points ≈ (away_ortg + home_drtg) / 2 * pace / 100
    """
    # Estimate each team's scoring rate against the other's defense
    home_expected_efficiency = (home_ortg + away_drtg) / 2.0
    away_expected_efficiency = (away_ortg + home_drtg) / 2.0

    # Scale by pace (possessions per game, normalized to per-100)
    pace_factor = league_avg_pace / 100.0

    total = (home_expected_efficiency + away_expected_efficiency) * pace_factor

    return round(total, 1)


def margin_to_win_probability(margin: float) -> float:
    """Convert a projected margin to win probability using logistic function."""
    return 1.0 / (1.0 + math.exp(-margin / SPREAD_TO_WIN_PROB_SIGMA))


def win_probability_to_margin(prob: float) -> float:
    """Convert a win probability back to projected margin."""
    if prob <= 0 or prob >= 1:
        return 0.0
    return -SPREAD_TO_WIN_PROB_SIGMA * math.log((1.0 / prob) - 1.0)
