"""Tests for the roster-based early-season prior, roster turnover and verdict capping."""

from __future__ import annotations

from typing import Any

import pytest

from app.analytics.edge_calculator import calculate_edge, cap_verdict
from app.analytics.roster_prior import (
    REPLACEMENT_OFFSET,
    compute_roster_priors,
    compute_roster_turnover,
    is_stale_prior,
    league_average_rating,
)
from app.services.pipeline import NBA_TEAM_ID_TO_ABBR

TEAMS = sorted(NBA_TEAM_ID_TO_ABBR.values())
LEAGUE_AVG = 115.0


def _player(pid: int, nrtg: float, mpg: float = 24.0, gp: int = 70) -> dict[str, Any]:
    return {
        "PLAYER_ID": pid, "PLAYER_NAME": f"P{pid}", "GP": gp, "MIN": mpg,
        "E_OFF_RATING": LEAGUE_AVG + nrtg / 2, "E_DEF_RATING": LEAGUE_AVG - nrtg / 2,
        "E_NET_RATING": nrtg,
    }


League = tuple[dict[str, list[int]], dict[int, dict[str, Any]], dict[str, dict[str, float]]]


def _league(spread: float = 0.5) -> League:
    """30 teams of 10 × 24-MPG players whose on-court NRtg equals their team's NRtg.

    Team i has NRtg (i − 14.5) × spread, so the league averages to 0.
    """
    rosters: dict[str, list[int]] = {}
    metrics: dict[int, dict[str, Any]] = {}
    team_ratings: dict[str, dict[str, float]] = {}
    for i, abbr in enumerate(TEAMS):
        nrtg = (i - 14.5) * spread
        ids = [i * 100 + j for j in range(10)]
        rosters[abbr] = ids
        metrics.update({pid: _player(pid, nrtg) for pid in ids})
        team_ratings[abbr] = {
            "ortg": LEAGUE_AVG + nrtg / 2, "drtg": LEAGUE_AVG - nrtg / 2,
            "nrtg": nrtg, "pace": 99.0,
        }
    return rosters, metrics, team_ratings


class TestRosterPriors:
    def test_league_average_preserved(self) -> None:
        rosters, metrics, team_ratings = _league()
        priors = compute_roster_priors(rosters, metrics, team_ratings)
        assert len(priors) == 30
        assert sum(p["ortg"] for p in priors.values()) / 30 == pytest.approx(LEAGUE_AVG, abs=0.01)
        assert sum(p["drtg"] for p in priors.values()) / 30 == pytest.approx(LEAGUE_AVG, abs=0.01)
        assert sum(p["nrtg"] for p in priors.values()) / 30 == pytest.approx(0.0, abs=0.02)

    def test_unchanged_rosters_track_last_season(self) -> None:
        rosters, metrics, team_ratings = _league()
        priors = compute_roster_priors(rosters, metrics, team_ratings)
        order_prior = sorted(priors, key=lambda a: priors[a]["nrtg"])
        order_last = sorted(team_ratings, key=lambda a: team_ratings[a]["nrtg"])
        assert order_prior == order_last
        for abbr in TEAMS:
            # Same sign and magnitude (within the spread calibration).
            assert priors[abbr]["nrtg"] == pytest.approx(team_ratings[abbr]["nrtg"], abs=2.0)
            assert priors[abbr]["pace"] == 99.0

    def test_phi_adding_stars_raises_prior_nrtg(self) -> None:
        """PHI-style offseason: stars from other teams replace PHI's rotation."""
        rosters, metrics, team_ratings = _league(spread=0.0)  # flat league: every team NRtg 0
        baseline = compute_roster_priors(rosters, metrics, team_ratings)

        stars = {2544: 3.8, 1627759: 5.4, 203484: -1.0, 1629014: 1.3}  # LeBron, Brown, KCP, Simons
        donors = ["LAL", "BOS", "DEN", "POR"]
        for (pid, nrtg), donor in zip(stars.items(), donors, strict=True):
            metrics[pid] = _player(pid, nrtg, mpg=33.0)
            rosters[donor] = rosters[donor][:-1]  # star left the donor team
        rosters["PHI"] = rosters["PHI"][:6] + list(stars)

        after = compute_roster_priors(rosters, metrics, team_ratings)
        assert after["PHI"]["nrtg"] > baseline["PHI"]["nrtg"] + 1.0
        assert after["PHI"]["nrtg"] > team_ratings["PHI"]["nrtg"] + 1.0
        # League average still anchored.
        assert sum(p["nrtg"] for p in after.values()) / 30 == pytest.approx(0.0, abs=0.02)

    def test_rookies_are_replacement_level(self) -> None:
        rosters, metrics, team_ratings = _league(spread=0.0)
        rosters["SAS"] = [900_000 + j for j in range(12)]  # all players without prior data
        priors = compute_roster_priors(rosters, metrics, team_ratings)
        assert priors["SAS"]["coverage"] == 0.0
        assert priors["SAS"]["nrtg"] < min(p["nrtg"] for a, p in priors.items() if a != "SAS")
        assert priors["SAS"]["nrtg"] < -REPLACEMENT_OFFSET

    def test_small_sample_shrunk_toward_replacement(self) -> None:
        rosters, metrics, team_ratings = _league(spread=0.0)
        rosters["MIA"] = rosters["MIA"][:9] + [777]
        rosters["MIL"] = rosters["MIL"][:9] + [778]
        metrics[777] = _player(777, 20.0, mpg=24.0, gp=2)   # hot 2-game sample
        metrics[778] = _player(778, 20.0, mpg=24.0, gp=80)  # same numbers, full season
        priors = compute_roster_priors(rosters, metrics, team_ratings)
        assert priors["MIL"]["nrtg"] > priors["MIA"]["nrtg"]

    def test_invalid_player_rows_treated_as_no_data(self) -> None:
        rosters, metrics, team_ratings = _league(spread=0.0)
        bad = rosters["OKC"][0]
        metrics[bad] = {**metrics[bad], "E_OFF_RATING": 150.0, "E_NET_RATING": 35.0}
        priors = compute_roster_priors(rosters, metrics, team_ratings)
        assert priors["OKC"]["coverage"] < 1.0
        assert priors["OKC"]["nrtg"] < 0.5  # the 150 ORtg did not inflate OKC

    def test_all_priors_pass_validation_ranges(self) -> None:
        rosters, metrics, team_ratings = _league(spread=1.5)
        for abbr, p in compute_roster_priors(rosters, metrics, team_ratings).items():
            assert 90 <= p["ortg"] <= 130, abbr
            assert 90 <= p["drtg"] <= 130, abbr
            assert -25 <= p["nrtg"] <= 25, abbr

    def test_too_few_rosters_returns_empty(self) -> None:
        rosters, metrics, team_ratings = _league()
        partial = {abbr: rosters[abbr] for abbr in TEAMS[:10]}
        assert compute_roster_priors(partial, metrics, team_ratings) == {}

    def test_no_player_metrics_returns_empty(self) -> None:
        rosters, _, team_ratings = _league()
        assert compute_roster_priors(rosters, {}, team_ratings) == {}

    def test_league_average_defaults_without_prior_ratings(self) -> None:
        assert league_average_rating({}) == 112.0
        _, _, team_ratings = _league()
        assert league_average_rating(team_ratings) == pytest.approx(LEAGUE_AVG)


class TestRosterTurnover:
    def test_unchanged_roster_is_zero(self) -> None:
        rosters, metrics, _ = _league()
        turnover = compute_roster_turnover(rosters, rosters, metrics)
        assert turnover["PHI"] == {"minutes_left": 0.0, "minutes_new": 0.0, "turnover": 0.0}

    def test_entirely_new_roster_is_one(self) -> None:
        rosters, metrics, _ = _league()
        current = {**rosters, "PHI": rosters["BOS"]}
        assert compute_roster_turnover(current, rosters, metrics)["PHI"]["turnover"] == 1.0

    def test_partial_turnover(self) -> None:
        rosters, metrics, _ = _league()
        current = {**rosters, "PHI": rosters["PHI"][:6] + rosters["BOS"][:4]}
        t = compute_roster_turnover(current, rosters, metrics)["PHI"]
        assert t["minutes_left"] == pytest.approx(0.4)
        assert t["minutes_new"] == pytest.approx(0.4)
        assert t["turnover"] == pytest.approx(0.4)

    def test_missing_prior_roster_is_unknown(self) -> None:
        rosters, metrics, _ = _league()
        prior = {k: v for k, v in rosters.items() if k != "PHI"}
        assert "PHI" not in compute_roster_turnover(rosters, prior, metrics)


class TestStalePrior:
    @pytest.mark.parametrize(
        "source, turnover, weight, expected",
        [
            ("roster", 0.9, 0.0, False),   # roster-based prior already reflects moves
            ("team", 0.5, 0.0, True),      # rebuilt roster, last year's team rating
            ("team", 0.1, 0.0, False),     # mostly the same team
            ("team", None, 0.0, True),     # rosters unavailable → can't rule it out
            ("team", 0.9, 0.6, False),     # current season dominates the blend
            ("league", 0.5, 0.1, True),
        ],
    )
    def test_matrix(
        self, source: str, turnover: float | None, weight: float, expected: bool,
    ) -> None:
        assert is_stale_prior(source, turnover, weight, turnover_threshold=0.35) is expected


class TestCapVerdict:
    def test_strong_buy_capped_to_lean(self) -> None:
        edge = calculate_edge(0.80, 0.50)
        assert edge.verdict == "STRONG BUY"
        capped = cap_verdict(edge, "LEAN")
        assert capped.verdict == "LEAN"
        assert capped.best_edge == edge.best_edge  # numbers untouched

    def test_lower_verdicts_unchanged(self) -> None:
        edge = calculate_edge(0.52, 0.50)
        assert cap_verdict(edge, "LEAN").verdict == edge.verdict

    def test_settled_passes_through(self) -> None:
        edge = calculate_edge(0.80, 0.50).model_copy(update={"verdict": "SETTLED"})
        assert cap_verdict(edge, "LEAN").verdict == "SETTLED"
