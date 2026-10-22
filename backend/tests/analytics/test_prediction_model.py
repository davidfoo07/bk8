"""Tests for the Prediction Model."""

import pytest

from app.analytics.prediction_model import (
    LEAGUE_LEVEL_K_GAMES,
    SEASON_SCORING_DRIFT,
    TOTAL_OT_ADJUSTMENT,
    TOTAL_STD_DEV,
    predict_game,
    estimate_total,
    league_scoring_baseline,
    calculate_schedule_modifier,
    margin_to_win_probability,
    win_probability_to_margin,
)


class TestPredictGame:
    """Tests for the core prediction model."""

    def test_even_matchup(self):
        """Two equal teams at neutral site should be ~50/50."""
        result = predict_game(
            home_adj_nrtg=0.0, away_adj_nrtg=0.0,
            home_adj_ortg=110.0, home_adj_drtg=110.0,
            away_adj_ortg=110.0, away_adj_drtg=110.0,
            home_court_advantage=0.0,
        )
        assert result.home_win_prob == pytest.approx(0.5, abs=0.01)

    def test_home_court_advantage(self):
        """Home team with equal NRtg should have >50% win prob."""
        result = predict_game(
            home_adj_nrtg=5.0, away_adj_nrtg=5.0,
            home_adj_ortg=115.0, home_adj_drtg=110.0,
            away_adj_ortg=115.0, away_adj_drtg=110.0,
            home_court_advantage=3.0,
        )
        assert result.home_win_prob > 0.5
        assert result.projected_spread < 0  # Home favored

    def test_strong_team_advantage(self):
        """Strong home team should have high win probability."""
        result = predict_game(
            home_adj_nrtg=10.0, away_adj_nrtg=-5.0,
            home_adj_ortg=118.0, home_adj_drtg=108.0,
            away_adj_ortg=107.0, away_adj_drtg=112.0,
        )
        assert result.home_win_prob > 0.8
        assert result.nrtg_differential == 15.0

    def test_schedule_adjustment(self):
        """Schedule modifiers should affect projected spread."""
        # Home team on B2B, away well-rested
        result = predict_game(
            home_adj_nrtg=5.0, away_adj_nrtg=5.0,
            home_adj_ortg=115.0, home_adj_drtg=110.0,
            away_adj_ortg=115.0, away_adj_drtg=110.0,
            home_schedule_mod=-2.5,
            away_schedule_mod=0.0,
        )
        assert result.schedule_adjustment == -2.5


class TestEstimateTotal:
    """Tests for total points estimation."""

    def test_average_game(self):
        """Average teams should produce ~220 total."""
        total = estimate_total(
            home_ortg=110.0, home_drtg=110.0,
            away_ortg=110.0, away_drtg=110.0,
        )
        assert 200 < total < 240

    def test_high_scoring_game(self):
        """Two high-offense, weak-defense teams → higher total."""
        total_high = estimate_total(
            home_ortg=120.0, home_drtg=115.0,
            away_ortg=120.0, away_drtg=115.0,
        )
        total_low = estimate_total(
            home_ortg=105.0, home_drtg=100.0,
            away_ortg=105.0, away_drtg=100.0,
        )
        assert total_high > total_low

    def test_average_teams_reproduce_league_level_plus_ot(self):
        """League-average inputs → 2 × ORtg × pace / 100 plus the OT adjustment."""
        total = estimate_total(
            home_ortg=112.0, home_drtg=112.0, away_ortg=112.0, away_drtg=112.0,
            home_pace=101.0, away_pace=101.0, league_ortg=112.0, league_pace=101.0,
        )
        assert total == pytest.approx(2 * 112.0 * 101.0 / 100 + TOTAL_OT_ADJUSTMENT, abs=0.1)

    def test_baseline_sets_level_for_average_matchup(self):
        """An average matchup projects exactly the league baseline (+ OT)."""
        total = estimate_total(
            home_ortg=112.0, home_drtg=112.0, away_ortg=112.0, away_drtg=112.0,
            home_pace=101.0, away_pace=101.0, league_ortg=112.0, league_pace=101.0,
            baseline_total=236.0,
        )
        assert total == pytest.approx(236.0 + TOTAL_OT_ADJUSTMENT, abs=0.1)

    def test_normalizes_against_inputs_league_level(self):
        """Ratings from a 116-ORtg league are not inflated by a stale 112.7 constant."""
        total = estimate_total(
            home_ortg=116.0, home_drtg=116.0, away_ortg=116.0, away_drtg=116.0,
            home_pace=100.0, away_pace=100.0, league_ortg=116.0, league_pace=100.0,
            baseline_total=230.0,
        )
        assert total == pytest.approx(230.0 + TOTAL_OT_ADJUSTMENT, abs=0.1)

    def test_relative_strength_moves_total_from_baseline(self):
        """Good offenses vs bad defenses score above baseline; the reverse below."""
        kw = dict(home_pace=100.0, away_pace=100.0, league_ortg=112.0, league_pace=100.0,
                  baseline_total=230.0)
        high = estimate_total(home_ortg=116.0, home_drtg=115.0, away_ortg=116.0, away_drtg=115.0, **kw)
        low = estimate_total(home_ortg=108.0, home_drtg=109.0, away_ortg=108.0, away_drtg=109.0, **kw)
        assert high > 230.0 + TOTAL_OT_ADJUSTMENT > low

    def test_home_away_symmetric(self):
        """Swapping home and away does not change the total."""
        a = estimate_total(118.0, 110.0, 108.0, 115.0, 99.0, 104.0, 112.0, 101.0, 232.0)
        b = estimate_total(108.0, 115.0, 118.0, 110.0, 104.0, 99.0, 112.0, 101.0, 232.0)
        assert a == pytest.approx(b, abs=0.05)

    def test_matchup_pace_relative_to_league(self):
        """Two fast teams project more points than two slow ones at equal efficiency."""
        kw = dict(home_ortg=112.0, home_drtg=112.0, away_ortg=112.0, away_drtg=112.0,
                  league_ortg=112.0, league_pace=100.0, baseline_total=230.0)
        fast = estimate_total(home_pace=104.0, away_pace=104.0, **kw)
        slow = estimate_total(home_pace=96.0, away_pace=96.0, **kw)
        assert fast == pytest.approx(230.0 * 1.04 + TOTAL_OT_ADJUSTMENT, abs=0.1)
        assert slow == pytest.approx(230.0 * 0.96 + TOTAL_OT_ADJUSTMENT, abs=0.1)


def _teams(ortg: float, pace: float, gp: float | None = None, n: int = 30) -> dict[str, dict[str, float]]:
    row = {"ortg": ortg, "drtg": ortg, "nrtg": 0.0, "pace": pace}
    if gp is not None:
        row["gp"] = gp
    return {f"T{i}": dict(row) for i in range(n)}


class TestLeagueScoringBaseline:
    """The league scoring level must follow the current season quickly."""

    def test_no_current_games_uses_prior_plus_drift(self):
        prior = _teams(112.0, 100.0)
        base = league_scoring_baseline({}, prior, prior)
        assert base["level_weight"] == 0.0
        assert base["baseline_total"] == pytest.approx(2 * 112.0 * 100.0 / 100 + SEASON_SCORING_DRIFT)

    def test_weight_follows_league_games(self):
        """30 teams × gp games = 15·gp league games; weight = games / (games + K)."""
        prior = _teams(112.0, 100.0)
        current = _teams(115.0, 102.0, gp=2)  # 30 league games
        base = league_scoring_baseline(current, prior, prior)
        w = 30 / (30 + LEAGUE_LEVEL_K_GAMES)
        expected = w * (2 * 115.0 * 102.0 / 100) + (1 - w) * (2 * 112.0 * 100.0 / 100 + SEASON_SCORING_DRIFT)
        assert base["level_weight"] == pytest.approx(w, abs=0.001)
        assert base["baseline_total"] == pytest.approx(expected, abs=0.01)

    def test_full_season_is_almost_all_current(self):
        """By mid-season the level is the current season's, not last season's.

        Regression: the per-team blend (K=15 team games) kept ≥15% of last
        season's level all year, so a season where scoring rose ran Under.
        """
        prior = _teams(111.0, 100.0)
        current = _teams(115.0, 102.0, gp=41)
        base = league_scoring_baseline(current, prior, prior)
        assert base["level_weight"] > 0.95
        assert base["baseline_total"] == pytest.approx(2 * 115.0 * 102.0 / 100, abs=0.5)

    def test_current_level_is_gp_weighted(self):
        prior = _teams(112.0, 100.0)
        current = {"A": {"ortg": 120.0, "drtg": 120.0, "pace": 100.0, "gp": 3.0},
                   "B": {"ortg": 110.0, "drtg": 110.0, "pace": 100.0, "gp": 1.0},
                   "C": {"ortg": 90.0, "drtg": 90.0, "pace": 100.0, "gp": 0.0}}
        base = league_scoring_baseline(current, prior, prior, k_games=0.0001)
        assert base["baseline_total"] == pytest.approx(2 * 117.5, abs=0.1)

    def test_league_ortg_and_pace_from_blended_inputs(self):
        blended = _teams(114.0, 99.0)
        base = league_scoring_baseline({}, _teams(112.0, 100.0), blended)
        assert base["league_ortg"] == pytest.approx(114.0)
        assert base["league_pace"] == pytest.approx(99.0)

    def test_no_data_falls_back_to_static_level(self):
        base = league_scoring_baseline({}, {}, {})
        assert 220 < base["baseline_total"] < 245


class TestOverProbability:
    """Over/under probabilities use the backtested total-score σ."""

    def test_sigma_is_backtested_value(self):
        assert 18.0 <= TOTAL_STD_DEV <= 20.0

    def test_one_sigma_line(self):
        """A line one σ above the projection → P(over) ≈ 15.9%."""
        kw = dict(home_adj_nrtg=0.0, away_adj_nrtg=0.0, home_adj_ortg=112.0, home_adj_drtg=112.0,
                  away_adj_ortg=112.0, away_adj_drtg=112.0, home_pace=100.0, away_pace=100.0,
                  league_ortg=112.0, league_pace=100.0, baseline_total=230.0)
        projected = predict_game(**kw).projected_total
        result = predict_game(total_line=projected + TOTAL_STD_DEV, **kw)
        assert result.over_prob == pytest.approx(0.159, abs=0.005)

    def test_small_gap_is_not_a_strong_edge(self):
        """Regression (2026-10-22): a ~6-pt gap to the line was a 'STRONG BUY' Under
        (P≈0.66 at σ=13.5).  At the backtested σ it is well under a 12% edge."""
        result = predict_game(
            home_adj_nrtg=0.0, away_adj_nrtg=0.0, home_adj_ortg=112.0, home_adj_drtg=112.0,
            away_adj_ortg=112.0, away_adj_drtg=112.0, home_pace=100.0, away_pace=100.0,
            league_ortg=112.0, league_pace=100.0, baseline_total=229.4,
            total_line=236.5,
        )
        assert 1 - result.over_prob < 0.62


class TestScheduleModifier:
    """Tests for schedule modifier calculation."""

    def test_b2b_penalty(self):
        """Back-to-back should incur negative modifier."""
        mod = calculate_schedule_modifier(is_b2b=True)
        assert mod < 0

    def test_no_fatigue(self):
        """Well-rested team with no travel = no modifier."""
        mod = calculate_schedule_modifier(rest_days=3, opponent_rest_days=3)
        assert mod == 0.0

    def test_rest_advantage(self):
        """More rest days than opponent = positive modifier."""
        mod = calculate_schedule_modifier(rest_days=3, opponent_rest_days=0)
        assert mod > 0

    def test_coast_to_coast_travel(self):
        """Long travel should incur penalty."""
        mod = calculate_schedule_modifier(travel_distance_miles=2500)
        assert mod < 0


class TestProbabilityConversion:
    """Tests for probability ↔ margin conversion."""

    def test_margin_zero_is_fifty_percent(self):
        """Zero margin = 50% probability."""
        assert margin_to_win_probability(0.0) == pytest.approx(0.5, abs=0.001)

    def test_roundtrip_conversion(self):
        """Converting margin→prob→margin should roundtrip."""
        original = 5.0
        prob = margin_to_win_probability(original)
        recovered = win_probability_to_margin(prob)
        assert recovered == pytest.approx(original, abs=0.01)

    def test_large_margin(self):
        """Large positive margin → high probability."""
        assert margin_to_win_probability(20.0) > 0.95

    def test_negative_margin(self):
        """Negative margin → low probability."""
        assert margin_to_win_probability(-10.0) < 0.3
