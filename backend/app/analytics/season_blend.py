"""
Early-season rating blend — regress small-sample current-season ratings
toward last season's ratings.

After 1-5 games a team's ORtg/DRtg is mostly noise (e.g. DRtg 81 after one
blowout).  We weight the current season by games played:

    w_current = gp / (gp + K)
    blended   = w_current * current + (1 - w_current) * prior

With K=15 a team is 50/50 at 15 GP and ~85% current-season by game 82.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.services.validation import DataValidator

LEAGUE_AVG_RATINGS: dict[str, float] = {"ortg": 112.0, "drtg": 112.0, "nrtg": 0.0, "pace": 100.0}

_RATING_KEYS = ("ortg", "drtg", "pace")


def blend_weight(games_played: float, k: float) -> float:
    """Weight on the current season given games played (0 → 0.0, ∞ → 1.0)."""
    gp = max(0.0, float(games_played or 0))
    if k <= 0:
        return 1.0 if gp > 0 else 0.0
    return gp / (gp + k)


def _ratings_valid(ratings: dict[str, float], validator: DataValidator, source: str) -> bool:
    results = validator.validate_team_ratings(
        ratings["ortg"], ratings["drtg"], ratings["nrtg"], source=source,
    )
    results.append(validator.validate_range("pace", ratings["pace"], source=source))
    return all(r.is_valid for r in results)


def blend_team_ratings(
    current: dict[str, dict[str, float]],
    prior: dict[str, dict[str, float]],
    k: float,
    validator: DataValidator | None = None,
) -> dict[str, dict[str, float]]:
    """Blend per-team current-season ratings with prior-season ratings.

    Both inputs map team abbr → {"ortg", "drtg", "pace", "gp"?}.  NRtg is
    recomputed as ORtg − DRtg so it stays consistent after blending.

    Fallbacks:
      - team missing from current (no games yet) → prior season as-is
      - team missing from prior (should not happen) → current, regressed to
        league average with the same weight
      - blended result outside validation ranges → prior, else league average

    Each output row carries "gp" (current-season games) and "current_weight".
    """
    validator = validator or DataValidator()
    result: dict[str, dict[str, float]] = {}

    for abbr in set(current) | set(prior):
        cur = current.get(abbr)
        base = prior.get(abbr) or LEAGUE_AVG_RATINGS
        gp = float(cur.get("gp", 0) or 0) if cur else 0.0
        w = blend_weight(gp, k) if cur else 0.0

        blended = {
            key: w * float(cur[key]) + (1 - w) * float(base[key]) if cur else float(base[key])
            for key in _RATING_KEYS
        }
        blended["nrtg"] = blended["ortg"] - blended["drtg"]
        blended = {key: round(val, 2) for key, val in blended.items()}

        if not _ratings_valid(blended, validator, source=f"blend:{abbr}"):
            fallback = prior.get(abbr) or LEAGUE_AVG_RATINGS
            logger.warning(f"{abbr} blended ratings out of range {blended}; falling back to prior season")
            blended = {key: float(fallback[key]) for key in (*_RATING_KEYS, "nrtg")}
            w = 0.0

        blended["gp"] = gp
        blended["current_weight"] = round(w, 3)
        result[abbr] = blended

    return result


def blend_player_metrics(
    current: dict[str, dict[str, Any]],
    prior: dict[str, dict[str, Any]],
    k: float,
) -> dict[str, dict[str, Any]]:
    """Blend per-player estimated metrics (keyed by player name) by GP.

    Injured players often have 0 current-season games, so the prior season is
    what keeps their absence impact meaningful early in the year.  Rookies
    (no prior row) use current-season numbers as-is.

    Each row also carries CURRENT_GP / PRIOR_GP and CURRENT_WEIGHT (the share
    of the blended numbers that comes from the current season).
    """
    blended_keys = ("MIN", "E_OFF_RATING", "E_DEF_RATING", "E_NET_RATING")
    result: dict[str, dict[str, Any]] = {}

    for name in set(current) | set(prior):
        cur = current.get(name)
        old = prior.get(name)
        cur_gp = float((cur or {}).get("GP", 0) or 0)
        old_gp = float((old or {}).get("GP", 0) or 0)
        if not cur or not old:
            result[name] = {
                **(cur or old),  # type: ignore[dict-item]
                "CURRENT_GP": cur_gp, "PRIOR_GP": old_gp, "CURRENT_WEIGHT": 1.0 if cur else 0.0,
            }
            continue

        w = blend_weight(cur_gp, k)
        row = {**cur, "CURRENT_GP": cur_gp, "PRIOR_GP": old_gp, "CURRENT_WEIGHT": w}
        for key in blended_keys:
            c, p = cur.get(key), old.get(key)
            if c is None or p is None:
                row[key] = c if c is not None else p
            else:
                row[key] = w * float(c) + (1 - w) * float(p)
        result[name] = row

    return result
