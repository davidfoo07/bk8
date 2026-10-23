"""Tests for in-game market probabilities used to price live edges."""

import pytest

from app.schemas.prediction import GamePrediction
from app.services.pipeline import _calculate_live_prediction, _live_market_probs

# DEN @ OKC pre-game: OKC by 8.9, total 233.3, OKC 82%
PRE_GAME = GamePrediction(
    nrtg_differential=5.9,
    schedule_adjustment=0.0,
    projected_spread=-8.9,
    projected_total=233.3,
    home_win_prob=0.823,
    spread_cover_prob=0.51,
    over_prob=0.437,
)


def _live(home: int, away: int, period: int, clock: str):
    live = _calculate_live_prediction(PRE_GAME, 2, home, away, period, clock)
    return live, _live_market_probs(PRE_GAME, live, home, away, -8.5, 236.5)


class TestLiveMarketProbs:
    def test_early_deficit_lowers_home_probs(self):
        # DEN leads 15-9, 6:46 left in the 1st
        live, (ml, cover, over) = _live(9, 15, 1, "6:46")
        assert ml == live.home_win_prob
        assert ml < PRE_GAME.home_win_prob
        assert cover < PRE_GAME.spread_cover_prob

    def test_tip_off_matches_pre_game(self):
        _, (ml, cover, over) = _live(0, 0, 1, "12:00")
        assert ml == pytest.approx(PRE_GAME.home_win_prob, abs=0.01)
        # Cover/over use the pre-game margin & total with full-game uncertainty
        assert cover == pytest.approx(0.51, abs=0.03)
        assert over == pytest.approx(0.43, abs=0.03)

    def test_late_blowout_is_near_certain(self):
        # OKC up 25 with 2 minutes left: wins, covers -8.5
        _, (ml, cover, _) = _live(120, 95, 4, "2:00")
        assert ml > 0.99
        assert cover > 0.99

    def test_high_scoring_pace_raises_over(self):
        # 140 points at halftime → on pace to clear 236.5 easily
        _, (_, _, over) = _live(72, 68, 2, "0:00")
        assert over > 0.8

    def test_no_lines_falls_back_to_pre_game(self):
        live = _calculate_live_prediction(PRE_GAME, 2, 9, 15, 1, "6:46")
        _, cover, over = _live_market_probs(PRE_GAME, live, 9, 15, None, None)
        assert cover == PRE_GAME.spread_cover_prob
        assert over == PRE_GAME.over_prob
