"""Tests for the Edge Calculator."""

import pytest

from app.analytics.edge_calculator import calculate_edge, calculate_game_edges, _kelly_fraction, _get_verdict


class TestCalculateEdge:
    """Tests for the edge calculation."""

    def test_positive_yes_edge(self):
        """Model higher than market → YES edge."""
        result = calculate_edge(model_probability=0.60, market_price=0.45)
        assert result.yes_edge > 0
        assert result.best_side == "YES"
        assert result.verdict in ("STRONG BUY", "BUY")

    def test_positive_no_edge(self):
        """Model lower than market → NO edge."""
        result = calculate_edge(model_probability=0.40, market_price=0.55)
        assert result.no_edge > 0
        assert result.best_side == "NO"

    def test_no_edge(self):
        """Model agrees with market → NO EDGE."""
        result = calculate_edge(model_probability=0.50, market_price=0.50)
        assert abs(result.best_edge) < 0.03
        assert result.verdict == "NO EDGE"

    def test_strong_buy(self):
        """Large edge (>=12%) → STRONG BUY."""
        result = calculate_edge(model_probability=0.70, market_price=0.50)
        assert result.verdict == "STRONG BUY"
        assert result.best_edge >= 0.12

    def test_kelly_is_positive_for_positive_edge(self):
        """Kelly fraction should be positive when there's an edge."""
        result = calculate_edge(model_probability=0.60, market_price=0.40)
        assert result.kelly_fraction > 0

    def test_kelly_is_zero_for_no_edge(self):
        """Kelly fraction should be zero when no edge."""
        result = calculate_edge(model_probability=0.50, market_price=0.50)
        assert result.kelly_fraction == 0.0

    def test_ev_calculation(self):
        """EV should be positive for the favored side."""
        result = calculate_edge(model_probability=0.60, market_price=0.40)
        assert result.yes_ev > 0
        assert result.no_ev < 0

    def test_clamped_inputs(self):
        """Edge cases: extreme probabilities are clamped."""
        result = calculate_edge(model_probability=0.0, market_price=1.0)
        assert result is not None  # Should not crash


class TestKellyFraction:
    """Tests for Kelly criterion calculation."""

    def test_positive_kelly(self):
        """Favorable odds → positive Kelly."""
        kelly = _kelly_fraction(0.6, 2.0)  # 60% chance at 2:1 odds
        assert kelly > 0

    def test_zero_kelly_no_edge(self):
        """Fair odds → zero Kelly."""
        kelly = _kelly_fraction(0.5, 2.0)
        assert kelly == 0.0

    def test_kelly_at_unit_odds(self):
        """Odds of 1.0 should return 0."""
        kelly = _kelly_fraction(0.6, 1.0)
        assert kelly == 0.0


class TestGetVerdict:
    """Tests for verdict determination."""

    def test_strong_buy(self):
        assert _get_verdict(0.15) == "STRONG BUY"

    def test_buy(self):
        assert _get_verdict(0.08) == "BUY"

    def test_lean(self):
        assert _get_verdict(0.04) == "LEAN"

    def test_no_edge(self):
        assert _get_verdict(0.02) == "NO EDGE"

    def test_negative_edge(self):
        assert _get_verdict(-0.05) == "NO EDGE"


class TestCalculateGameEdges:
    """Tests for batch game edge calculation."""

    def test_all_markets(self):
        """Should calculate edges for all three market types."""
        edges = calculate_game_edges(
            home_win_prob=0.65,
            spread_cover_prob=0.55,
            over_prob=0.48,
            moneyline_price=0.72,
            spread_price=0.50,
            total_price=0.52,
        )
        assert edges["moneyline"] is not None
        assert edges["spread"] is not None
        assert edges["total"] is not None

    def test_missing_prices(self):
        """Missing prices should result in None edges."""
        edges = calculate_game_edges(
            home_win_prob=0.65,
            spread_cover_prob=0.55,
            over_prob=0.48,
        )
        assert edges["moneyline"] is None
        assert edges["spread"] is None
        assert edges["total"] is None
