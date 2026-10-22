"""Tests for the season helper, early-season rating blend and motivation guard."""

from datetime import date

import pytest

from app.analytics.schedule_engine import determine_motivation
from app.analytics.season_blend import (
    LEAGUE_AVG_RATINGS,
    blend_player_metrics,
    blend_team_ratings,
    blend_weight,
)
from app.config import current_season, previous_season, season_for_date, settings


class TestSeasonHelper:
    @pytest.mark.parametrize(
        "d, expected",
        [
            (date(2026, 10, 22), "2026-27"),  # opening week
            (date(2026, 10, 1), "2026-27"),   # rollover day
            (date(2026, 9, 30), "2025-26"),   # offseason still counts as last season
            (date(2027, 4, 10), "2026-27"),   # end of regular season
            (date(2027, 6, 15), "2026-27"),   # finals
            (date(2026, 1, 1), "2025-26"),
            (date(1999, 11, 1), "1999-00"),   # century wrap
        ],
    )
    def test_season_for_date(self, d: date, expected: str) -> None:
        assert season_for_date(d) == expected

    def test_custom_rollover_month(self) -> None:
        assert season_for_date(date(2026, 9, 15), rollover_month=9) == "2026-27"

    def test_previous_season(self) -> None:
        assert previous_season("2026-27") == "2025-26"
        assert previous_season("2000-01") == "1999-00"

    def test_current_season_uses_date(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "nba_season_override", None)
        assert current_season(date(2026, 10, 22)) == "2026-27"

    def test_current_season_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "nba_season_override", "2025-26")
        assert current_season(date(2026, 10, 22)) == "2025-26"


class TestBlendWeight:
    def test_zero_games_is_all_prior(self) -> None:
        assert blend_weight(0, 15) == 0.0

    def test_half_at_k(self) -> None:
        assert blend_weight(15, 15) == pytest.approx(0.5)

    def test_monotonic_and_bounded(self) -> None:
        weights = [blend_weight(gp, 15) for gp in range(0, 83)]
        assert weights == sorted(weights)
        assert all(0.0 <= w < 1.0 for w in weights)

    def test_nonpositive_k_uses_current(self) -> None:
        assert blend_weight(3, 0) == 1.0
        assert blend_weight(0, 0) == 0.0


PRIOR = {
    "TOR": {"ortg": 112.0, "drtg": 114.0, "nrtg": -2.0, "pace": 99.0, "gp": 82},
    "BOS": {"ortg": 120.0, "drtg": 110.0, "nrtg": 10.0, "pace": 97.0, "gp": 82},
}


class TestBlendTeamRatings:
    def test_one_game_outlier_is_mostly_prior(self) -> None:
        # Real 2026-27 opening-night row: DRtg 81.2 / NRtg +38 would fail validation raw.
        current = {"TOR": {"ortg": 119.2, "drtg": 81.2, "nrtg": 38.0, "pace": 113.2, "gp": 1}}
        out = blend_team_ratings(current, PRIOR, k=15)
        tor = out["TOR"]
        w = 1 / 16
        assert tor["current_weight"] == pytest.approx(w, abs=1e-3)
        assert tor["ortg"] == pytest.approx(w * 119.2 + (1 - w) * 112.0, abs=0.01)
        assert tor["drtg"] == pytest.approx(w * 81.2 + (1 - w) * 114.0, abs=0.01)
        assert tor["nrtg"] == pytest.approx(tor["ortg"] - tor["drtg"], abs=0.01)
        assert tor["gp"] == 1

    def test_team_without_games_uses_prior(self) -> None:
        out = blend_team_ratings({}, PRIOR, k=15)
        assert out["BOS"]["ortg"] == 120.0
        assert out["BOS"]["nrtg"] == 10.0
        assert out["BOS"]["current_weight"] == 0.0

    def test_late_season_tracks_current(self) -> None:
        current = {"BOS": {"ortg": 110.0, "drtg": 112.0, "pace": 98.0, "gp": 70}}
        out = blend_team_ratings(current, PRIOR, k=15)
        assert out["BOS"]["current_weight"] > 0.8
        assert out["BOS"]["ortg"] < 112.0

    def test_missing_prior_regresses_to_league_average(self) -> None:
        current = {"NOP": {"ortg": 125.0, "drtg": 100.0, "pace": 101.0, "gp": 15}}
        out = blend_team_ratings(current, {}, k=15)
        assert out["NOP"]["ortg"] == pytest.approx(0.5 * 125.0 + 0.5 * LEAGUE_AVG_RATINGS["ortg"])

    def test_out_of_range_blend_falls_back_to_prior(self) -> None:
        # Absurd current value with enough GP to drag the blend out of [90, 130].
        current = {"BOS": {"ortg": 300.0, "drtg": 110.0, "pace": 97.0, "gp": 50}}
        out = blend_team_ratings(current, PRIOR, k=15)
        assert out["BOS"]["ortg"] == 120.0
        assert out["BOS"]["current_weight"] == 0.0

    def test_all_blended_outputs_pass_ranges(self) -> None:
        current = {"TOR": {"ortg": 140.0, "drtg": 75.0, "pace": 120.0, "gp": 1}}
        tor = blend_team_ratings(current, PRIOR, k=15)["TOR"]
        assert 90 <= tor["ortg"] <= 130
        assert 90 <= tor["drtg"] <= 130
        assert -25 <= tor["nrtg"] <= 25
        assert 90 <= tor["pace"] <= 110


class TestBlendPlayerMetrics:
    def test_injured_player_with_no_current_games_keeps_prior(self) -> None:
        prior = {"Star": {"GP": 70, "MIN": 34.0, "E_NET_RATING": 8.0}}
        out = blend_player_metrics({}, prior, k=10)
        assert out["Star"]["E_NET_RATING"] == 8.0

    def test_rookie_uses_current(self) -> None:
        current = {"Rookie": {"GP": 2, "MIN": 20.0, "E_NET_RATING": -5.0}}
        out = blend_player_metrics(current, {}, k=10)
        assert out["Rookie"]["E_NET_RATING"] == -5.0

    def test_blends_by_games_played(self) -> None:
        current = {"P": {"GP": 10, "MIN": 30.0, "E_NET_RATING": 20.0}}
        prior = {"P": {"GP": 80, "MIN": 20.0, "E_NET_RATING": 0.0}}
        out = blend_player_metrics(current, prior, k=10)
        assert out["P"]["E_NET_RATING"] == pytest.approx(10.0)
        assert out["P"]["MIN"] == pytest.approx(25.0)
        assert out["P"]["GP"] == 10


class TestEarlySeasonMotivation:
    def test_top_seed_after_one_game_is_neutral(self) -> None:
        info = determine_motivation(
            team="TOR", record="1-0", conference_seed=1,
            games_remaining=81, early_season_games=20,
        )
        assert info.motivation_flag == "NEUTRAL"
        assert "Early season" in info.motivation_note

    def test_late_season_logic_unchanged(self) -> None:
        info = determine_motivation(
            team="ORL", record="45-37", conference_seed=8,
            games_remaining=5, early_season_games=20,
        )
        assert info.motivation_flag == "FIGHTING"
