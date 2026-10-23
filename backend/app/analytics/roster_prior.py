"""
Roster-based early-season prior — rate *this* season's roster, not last
season's team.

season_blend regresses tiny current-season samples toward a prior.  Using last
season's TEAM rating as that prior ignores the offseason: a team that adds
three starters is still rated as last year's roster for the first ~15 games.

Instead we rebuild each team's prior from last season's player-level estimated
metrics (playerestimatedmetrics E_OFF_RATING / E_DEF_RATING — on-court team
ratings while the player played), weighted by projected minutes on the
CURRENT roster:

  1. Each rostered player gets last season's MPG and on-court ratings, pooled
     with the season before at half weight (a star who missed most of last
     season — Haliburton, Lillard, Tatum — is rated on his last healthy year,
     not as a replacement player), then shrunk toward replacement level by
     games played (small samples are noise).  Players with no row in either
     season (rookies, returning from abroad) are replacement level.
  2. Projected minutes fill a 240-minute rotation in MPG order; any minutes
     left over go to replacement level.
  3. Minutes-weighted ORtg/DRtg per team, re-centred on last season's league
     average (deviations stretched by SPREAD_SCALE, then regressed to the mean
     by PRIOR_REGRESSION — see below).

For an unchanged roster this lands close to last season's team rating (the
minutes-weighted average of on-court ratings IS the team rating); moving a
player moves his on-court impact with him.

Roster turnover is reported alongside so the pipeline can flag teams whose
prior is stale (high turnover AND no roster-based prior available).
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.analytics.season_blend import LEAGUE_AVG_RATINGS
from app.services.validation import DataValidator

ROTATION_MINUTES = 240.0
# Games of prior-season data at which a player is 50% his own numbers, 50% replacement.
PLAYER_SHRINK_GP = 10.0
# Replacement-level on-court ratings relative to league average (NRtg ≈ −4).
REPLACEMENT_OFFSET = 2.0
# Minutes we expect a player with no prior-season data to play.
NO_DATA_MPG = 10.0
MAX_MPG = 38.0
# Anchoring to the league average needs most of the league, or it biases the subset.
MIN_TEAMS_FOR_ANCHOR = 20
# Minutes-weighted on-court ratings are compressed vs real team ratings (every
# player's on-court number includes his teammates).  Backtest: 2025-26 rosters
# vs 2025-26 team NRtg → corr 0.985, slope 0.83, so deviations from the league
# average are stretched by 1/0.83 ≈ 1.2.
SPREAD_SCALE = 1.2
# ...but that fit is in-sample: it rates a season's rosters on the SAME season's
# player numbers.  Out of sample (2025-26 rosters rated on 2024-25 player
# metrics vs actual 2025-26 team NRtg) the stretched prior has corr 0.49 and
# slope 0.59: teams regress hard toward the mean year to year (last season's
# team NRtg → next season: slope 0.54).  Without this the prior was ~1.7× too
# extreme (WAS −10, SAS +10) and drove 15-30 pt disagreements with Polymarket.
PRIOR_REGRESSION = 0.6
# Weight of the season before last relative to last season, per game played.
OLDER_SEASON_WEIGHT = 0.5


def _valid_player_row(row: dict[str, Any], validator: DataValidator, source: str) -> bool:
    ortg, drtg, nrtg = row.get("E_OFF_RATING"), row.get("E_DEF_RATING"), row.get("E_NET_RATING")
    mpg = row.get("MIN")
    if ortg is None or drtg is None or mpg is None:
        return False
    if nrtg is None:
        nrtg = float(ortg) - float(drtg)
    results = validator.validate_team_ratings(float(ortg), float(drtg), float(nrtg), source=source)
    results.append(validator.validate_range("player_minutes", float(mpg), source=source))
    return all(r.is_valid for r in results)


def _player_projection(
    row: dict[str, Any] | None,
    league_avg: float,
    validator: DataValidator,
    older_row: dict[str, Any] | None = None,
    older_league_avg: float | None = None,
) -> tuple[float, float, float, bool]:
    """(mpg, ortg, drtg, has_data) for one rostered player.

    ``older_row`` (the season before last) is pooled in at OLDER_SEASON_WEIGHT
    per game, re-centred from its own league average onto ``league_avg``.
    """
    repl_ortg = league_avg - REPLACEMENT_OFFSET
    repl_drtg = league_avg + REPLACEMENT_OFFSET
    seasons: list[tuple[float, float, float, float]] = []  # (weighted gp, mpg, ortg, drtg)
    for r, avg, weight in ((row, league_avg, 1.0),
                           (older_row, older_league_avg or league_avg, OLDER_SEASON_WEIGHT)):
        pid = r.get("PLAYER_ID") if r else None
        if not r or not _valid_player_row(r, validator, source=f"player_metrics:{pid}"):
            continue
        gp = max(0.0, float(r.get("GP", 0) or 0)) * weight
        shift = league_avg - avg
        seasons.append((gp, float(r["MIN"]), float(r["E_OFF_RATING"]) + shift,
                        float(r["E_DEF_RATING"]) + shift))
    if not seasons:
        return NO_DATA_MPG, repl_ortg, repl_drtg, False

    gp = sum(s[0] for s in seasons)
    if gp > 0:
        mpg, ortg, drtg = (sum(s[0] * s[i] for s in seasons) / gp for i in (1, 2, 3))
    else:
        _, mpg, ortg, drtg = seasons[0]
    w = gp / (gp + PLAYER_SHRINK_GP)
    ortg = w * ortg + (1 - w) * repl_ortg
    drtg = w * drtg + (1 - w) * repl_drtg
    return min(MAX_MPG, mpg), ortg, drtg, True


def _raw_roster_rating(
    player_ids: list[int],
    metrics_by_id: dict[int, dict[str, Any]],
    league_avg: float,
    validator: DataValidator,
    older_by_id: dict[int, dict[str, Any]] | None = None,
    older_league_avg: float | None = None,
) -> dict[str, float]:
    """Un-anchored minutes-weighted on-court ratings for one roster."""
    older_by_id = older_by_id or {}
    projections = [
        _player_projection(
            metrics_by_id.get(pid), league_avg, validator,
            older_row=older_by_id.get(pid), older_league_avg=older_league_avg,
        )
        for pid in player_ids
    ]
    projections.sort(key=lambda p: p[0], reverse=True)

    remaining = ROTATION_MINUTES
    ortg_sum = drtg_sum = covered = 0.0
    for mpg, ortg, drtg, has_data in projections:
        minutes = min(mpg, remaining)
        if minutes <= 0:
            break
        ortg_sum += minutes * ortg
        drtg_sum += minutes * drtg
        covered += minutes if has_data else 0.0
        remaining -= minutes

    # Short/thin roster: the unfilled rotation minutes go to replacement level.
    ortg_sum += remaining * (league_avg - REPLACEMENT_OFFSET)
    drtg_sum += remaining * (league_avg + REPLACEMENT_OFFSET)

    return {
        "ortg": ortg_sum / ROTATION_MINUTES,
        "drtg": drtg_sum / ROTATION_MINUTES,
        "coverage": covered / ROTATION_MINUTES,
    }


def league_average_rating(prior_team_ratings: dict[str, dict[str, float]]) -> float:
    """Last season's league-average ORtg (= DRtg), or the static default."""
    ortgs = [float(r["ortg"]) for r in prior_team_ratings.values() if r.get("ortg") is not None]
    return sum(ortgs) / len(ortgs) if ortgs else LEAGUE_AVG_RATINGS["ortg"]


def compute_roster_priors(
    rosters: dict[str, list[int]],
    prior_player_metrics: dict[int, dict[str, Any]],
    prior_team_ratings: dict[str, dict[str, float]],
    validator: DataValidator | None = None,
    min_teams: int = MIN_TEAMS_FOR_ANCHOR,
    older_player_metrics: dict[int, dict[str, Any]] | None = None,
    older_team_ratings: dict[str, dict[str, float]] | None = None,
) -> dict[str, dict[str, float]]:
    """Roster-based prior ratings per team → {abbr: {ortg, drtg, nrtg, pace, coverage}}.

    Args:
        rosters: current-season roster per team (abbr → NBA player IDs).
        prior_player_metrics: last season's playerestimatedmetrics rows by PLAYER_ID.
        prior_team_ratings: last season's team ratings (league average + pace).
        older_player_metrics / older_team_ratings: the same for the season
            before last (optional; covers players who missed last season).

    Returns {} when too few teams have rosters to anchor the league average or
    there are no player metrics.  Teams whose anchored prior fails validation
    are dropped (the caller falls back to last season's team rating).
    """
    validator = validator or DataValidator()
    if not prior_player_metrics:
        return {}
    rosters = {abbr: ids for abbr, ids in rosters.items() if ids}
    if len(rosters) < min_teams:
        logger.warning(f"Roster prior: only {len(rosters)} rosters (need {min_teams}); skipping")
        return {}

    league_avg = league_average_rating(prior_team_ratings)
    older_league_avg = league_average_rating(older_team_ratings) if older_team_ratings else None
    raw = {
        abbr: _raw_roster_rating(
            ids, prior_player_metrics, league_avg, validator,
            older_by_id=older_player_metrics, older_league_avg=older_league_avg,
        )
        for abbr, ids in rosters.items()
    }

    mean_ortg = sum(r["ortg"] for r in raw.values()) / len(raw)
    mean_drtg = sum(r["drtg"] for r in raw.values()) / len(raw)

    result: dict[str, dict[str, float]] = {}
    for abbr, r in raw.items():
        ortg = league_avg + PRIOR_REGRESSION * SPREAD_SCALE * (r["ortg"] - mean_ortg)
        drtg = league_avg + PRIOR_REGRESSION * SPREAD_SCALE * (r["drtg"] - mean_drtg)
        pace = float((prior_team_ratings.get(abbr) or LEAGUE_AVG_RATINGS)["pace"])
        row = {
            "ortg": round(ortg, 2),
            "drtg": round(drtg, 2),
            "nrtg": round(ortg - drtg, 2),
            "pace": pace,
            "coverage": round(r["coverage"], 3),
        }
        checks = validator.validate_team_ratings(
            row["ortg"], row["drtg"], row["nrtg"], source=f"roster_prior:{abbr}",
        )
        if not all(c.is_valid for c in checks):
            logger.warning(f"{abbr} roster prior out of range {row}; dropping")
            continue
        result[abbr] = row

    return result


def regress_team_ratings(
    team_ratings: dict[str, dict[str, float]],
    factor: float = PRIOR_REGRESSION,
) -> dict[str, dict[str, float]]:
    """Last season's team ratings regressed toward the league average.

    Used as the prior for teams without a roster-based one: a team's NRtg
    carries over to the next season with slope ≈ 0.54 (see PRIOR_REGRESSION).
    """
    if not team_ratings:
        return {}
    mean_ortg = sum(float(r["ortg"]) for r in team_ratings.values()) / len(team_ratings)
    mean_drtg = sum(float(r["drtg"]) for r in team_ratings.values()) / len(team_ratings)
    result: dict[str, dict[str, float]] = {}
    for abbr, r in team_ratings.items():
        ortg = mean_ortg + factor * (float(r["ortg"]) - mean_ortg)
        drtg = mean_drtg + factor * (float(r["drtg"]) - mean_drtg)
        result[abbr] = {**r, "ortg": round(ortg, 2), "drtg": round(drtg, 2),
                        "nrtg": round(ortg - drtg, 2)}
    return result


def compute_roster_turnover(
    current_rosters: dict[str, list[int]],
    prior_rosters: dict[str, list[int]],
    prior_player_metrics: dict[int, dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Per-team roster turnover vs last season → {abbr: {minutes_left, minutes_new, turnover}}.

    minutes_left: share of last season's roster minutes (MPG × GP) whose player is gone.
    minutes_new:  share of this season's projected rotation minutes from new players.
    turnover:     mean of the two (0 = same team, 1 = entirely new team).

    Teams missing either roster are omitted (turnover unknown).
    """
    result: dict[str, dict[str, float]] = {}
    for abbr, current_ids in current_rosters.items():
        old_ids = prior_rosters.get(abbr)
        if not current_ids or not old_ids:
            continue
        current, old = set(current_ids), set(old_ids)

        def total_minutes(pid: int) -> float:
            row = prior_player_metrics.get(pid) or {}
            return float(row.get("MIN", 0) or 0) * float(row.get("GP", 0) or 0)

        old_total = sum(total_minutes(pid) for pid in old)
        left = sum(total_minutes(pid) for pid in old - current)
        minutes_left = left / old_total if old_total > 0 else 0.0

        def projected_mpg(pid: int) -> float:
            mpg = (prior_player_metrics.get(pid) or {}).get("MIN")
            return min(MAX_MPG, float(mpg or NO_DATA_MPG))

        projected = sorted(((projected_mpg(pid), pid) for pid in current), reverse=True)
        remaining, new_minutes, filled = ROTATION_MINUTES, 0.0, 0.0
        for mpg, pid in projected:
            minutes = min(mpg, remaining)
            if minutes <= 0:
                break
            filled += minutes
            new_minutes += minutes if pid not in old else 0.0
            remaining -= minutes
        minutes_new = new_minutes / filled if filled > 0 else 0.0

        result[abbr] = {
            "minutes_left": round(minutes_left, 3),
            "minutes_new": round(minutes_new, 3),
            "turnover": round((minutes_left + minutes_new) / 2, 3),
        }
    return result


def is_stale_prior(
    prior_source: str,
    turnover: float | None,
    current_weight: float,
    turnover_threshold: float,
    max_current_weight: float = 0.5,
) -> bool:
    """True when a team's rating leans on a prior that ignores its new roster.

    Only matters while the prior dominates the blend (current weight < 0.5).
    Unknown turnover (rosters unavailable) is treated as high — we can't rule
    out a rebuilt roster.
    """
    if prior_source == "roster" or current_weight >= max_current_weight:
        return False
    return turnover is None or turnover >= turnover_threshold
