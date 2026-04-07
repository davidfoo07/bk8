"""Tests for the Prediction Model."""

import pytest

from app.analytics.prediction_model import (
    predict_game,
    estimate_total,
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
