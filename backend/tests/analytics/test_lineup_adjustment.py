"""Tests for the Lineup Adjustment Engine."""

import pytest

from app.analytics.lineup_adjustment import OnOffSplitModel, compute_player_impact
from app.schemas.team import PlayerAbsence


class TestOnOffSplitModel:
    """Tests for the V1 On/Off Split Model."""

    def setup_method(self):
        self.model = OnOffSplitModel()

    def test_no_missing_players(self):
        """With no missing players, adjusted = season ratings."""
        result = self.model.calculate_adjusted_ratings(
            team_id="DET",
            season_ortg=112.5,
            season_drtg=114.2,
            missing_players=[],
        )
        assert result.adjusted_ortg == 112.5
        assert result.adjusted_drtg == 114.2
        assert result.adjusted_nrtg == pytest.approx(112.5 - 114.2, abs=0.1)
        assert result.ortg_delta == 0.0
        assert result.confidence == "HIGH"

    def test_single_player_absence(self, sample_player_absence):
        """Single player out should adjust ratings by their impact."""
        result = self.model.calculate_adjusted_ratings(
            team_id="DET",
            season_ortg=112.5,
            season_drtg=114.2,
            missing_players=[sample_player_absence],
        )
        # First player has factor=1.0, so impacts apply directly
        assert result.adjusted_ortg == pytest.approx(112.5 + (-3.5), abs=0.1)
        assert result.adjusted_drtg == pytest.approx(114.2 + 1.2, abs=0.1)
        assert result.team == "DET"
        assert len(result.missing_players) == 1

    def test_multi_player_diminishing_returns(self, sample_player_absences):
        """Multiple missing players should have diminishing returns."""
        result = self.model.calculate_adjusted_ratings(
            team_id="DET",
            season_ortg=112.5,
            season_drtg=114.2,
            missing_players=sample_player_absences,
        )
        # Second player should have 0.85 factor
        expected_ortg = 112.5 + (-3.5 * 1.0) + (-1.5 * 0.85)
        assert result.adjusted_ortg == pytest.approx(expected_ortg, abs=0.1)

    def test_confidence_with_minutes_context(self):
        """Confidence should reflect on/off minutes sample size."""
        player = PlayerAbsence(
            player_id="1", name="Test", status="OUT",
            ortg_impact=-2.0, drtg_impact=1.0, nrtg_impact=-3.0,
            minutes_share=0.3,
        )
        # High confidence (>200 minutes)
        result = self.model.calculate_adjusted_ratings(
            team_id="TST", season_ortg=110.0, season_drtg=110.0,
            missing_players=[player],
            minutes_context={"1": {"on_minutes": 250, "off_minutes": 200}},
        )
        assert result.confidence == "HIGH"

        # Low confidence (<100 minutes)
        result = self.model.calculate_adjusted_ratings(
            team_id="TST", season_ortg=110.0, season_drtg=110.0,
            missing_players=[player],
            minutes_context={"1": {"on_minutes": 30, "off_minutes": 20}},
        )
        assert result.confidence == "LOW"


class TestComputePlayerImpact:
    """Tests for the player impact calculation helper."""

    def test_positive_impact_player(self):
        """Star player: high on-court, low off-court ORtg."""
        ortg_imp, drtg_imp, nrtg_imp = compute_player_impact(
            on_ortg=118.0, off_ortg=110.5,
            on_drtg=106.0, off_drtg=112.0,
            minutes_share=0.40,
        )
        # Player helps offense: on > off → negative impact when OUT
        assert ortg_imp < 0  # Team gets worse offensively
        # Player helps defense: on < off (lower is better) → positive when OUT
        assert drtg_imp > 0  # Team gets worse defensively

    def test_zero_minutes_share(self):
        """Zero minutes share = zero impact."""
        ortg_imp, drtg_imp, nrtg_imp = compute_player_impact(
            on_ortg=120.0, off_ortg=100.0,
            on_drtg=100.0, off_drtg=120.0,
            minutes_share=0.0,
        )
        assert ortg_imp == 0.0
        assert drtg_imp == 0.0
        assert nrtg_imp == 0.0
