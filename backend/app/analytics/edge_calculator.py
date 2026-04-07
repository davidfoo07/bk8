"""
Edge Calculator — compares model probability against Polymarket prices.
Calculates EV, Kelly criterion, and verdict for each market.
"""

from __future__ import annotations

import math

from loguru import logger

from app.schemas.market import EdgeResult


def calculate_edge(
    model_probability: float,
    market_price: float,
) -> EdgeResult:
    """
    Compare model's probability against Polymarket price.

    Args:
        model_probability: Our model's estimated true probability (0-1)
        market_price: Polymarket YES price (0-1), which IS the implied probability

    Returns:
        EdgeResult with edge, EV, Kelly fraction, and verdict for both sides.
    """
    # Clamp inputs
    model_probability = max(0.001, min(0.999, model_probability))
    market_price = max(0.01, min(0.99, market_price))

    # YES side
    yes_edge = model_probability - market_price
    decimal_odds_yes = 1.0 / market_price
    yes_ev = (model_probability * decimal_odds_yes) - 1.0

    # NO side
    no_model_prob = 1.0 - model_probability
    no_price = 1.0 - market_price
    no_edge = no_model_prob - no_price
    decimal_odds_no = 1.0 / no_price
    no_ev = (no_model_prob * decimal_odds_no) - 1.0

    # Kelly Criterion (full Kelly)
    # Kelly% = (p * b - q) / b where p=prob, b=decimal_odds-1, q=1-p
    kelly_yes = _kelly_fraction(model_probability, decimal_odds_yes)
    kelly_no = _kelly_fraction(no_model_prob, decimal_odds_no)

    # Quarter Kelly for conservative sizing
    quarter_kelly_yes = kelly_yes * 0.25
    quarter_kelly_no = kelly_no * 0.25

    # Determine best side
    best_side = "YES" if yes_edge > no_edge else "NO"
    best_edge = max(yes_edge, no_edge)
    best_kelly = quarter_kelly_yes if best_side == "YES" else quarter_kelly_no

    # Determine verdict
    verdict = _get_verdict(best_edge)

    result = EdgeResult(
        yes_edge=round(yes_edge, 4),
        no_edge=round(no_edge, 4),
        yes_ev=round(yes_ev, 4),
        no_ev=round(no_ev, 4),
        best_side=best_side,
        best_edge=round(best_edge, 4),
        verdict=verdict,
        kelly_fraction=round(best_kelly, 4),
        suggested_bet_pct=round(best_kelly * 100, 2),
    )

    logger.debug(
        f"Edge calc: model={model_probability:.3f}, market={market_price:.3f}, "
        f"best={best_side} edge={best_edge:.4f}, verdict={verdict}"
    )

    return result


def _kelly_fraction(probability: float, decimal_odds: float) -> float:
    """
    Calculate Kelly criterion fraction.
    Kelly% = (p * b - q) / b
    where p = probability of winning, b = decimal_odds - 1, q = 1 - p
    """
    if decimal_odds <= 1.0:
        return 0.0
    b = decimal_odds - 1.0
    q = 1.0 - probability
    kelly = (probability * b - q) / b
    return max(0.0, kelly)


def _get_verdict(edge: float) -> str:
    """
    Determine betting verdict based on edge size.
    - STRONG BUY: >= 12% edge
    - BUY: >= 6% edge
    - LEAN: >= 3% edge
    - NO EDGE: < 3% edge
    """
    if edge >= 0.12:
        return "STRONG BUY"
    elif edge >= 0.06:
        return "BUY"
    elif edge >= 0.03:
        return "LEAN"
    else:
        return "NO EDGE"


def calculate_game_edges(
    home_win_prob: float,
    spread_cover_prob: float,
    over_prob: float,
    moneyline_price: float | None = None,
    spread_price: float | None = None,
    total_price: float | None = None,
) -> dict[str, EdgeResult | None]:
    """
    Calculate edges for all three market types of a game.
    Returns dict with keys: moneyline, spread, total.
    """
    edges: dict[str, EdgeResult | None] = {
        "moneyline": None,
        "spread": None,
        "total": None,
    }

    if moneyline_price is not None:
        edges["moneyline"] = calculate_edge(home_win_prob, moneyline_price)

    if spread_price is not None:
        edges["spread"] = calculate_edge(spread_cover_prob, spread_price)

    if total_price is not None:
        edges["total"] = calculate_edge(over_prob, total_price)

    return edges
