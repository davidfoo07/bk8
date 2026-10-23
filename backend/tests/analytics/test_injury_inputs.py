"""Injury-impact inputs: name matching, stats-team baseline, GP shrink, team reassignment."""

from __future__ import annotations

from typing import Any

import pytest

from app.analytics.season_blend import blend_player_metrics
from app.services.pipeline import (
    _build_player_absences,
    _lookup_player,
    _normalize_name,
    _reassign_injury_teams,
    _with_team_context,
)


def _row(pid: int, enet: float, mpg: float = 25.0, **extra: Any) -> dict[str, Any]:
    return {"PLAYER_ID": pid, "MIN": mpg, "E_NET_RATING": enet, **extra}


CONTEXT = {
    "team": {1: "BOS", 2: "LAC", 3: "UTA"},
    "prior_team": {1: "SAC", 2: "TOR", 3: "UTA"},
    "current_nrtg": {"BOS": 5.0, "LAC": 2.0, "UTA": -9.0, "SAC": -10.0, "TOR": 5.0},
    "prior_nrtg": {"SAC": -9.8, "TOR": 2.8, "UTA": -8.0, "BOS": 7.8},
}


class TestNameMatching:
    def test_normalize_strips_diacritics_and_punctuation(self) -> None:
        assert _normalize_name("Jusuf Nurkić") == "jusuf nurkic"
        assert _normalize_name("Kristaps Porziņģis") == "kristaps porzingis"
        assert _normalize_name("De'Aaron  Fox") == "deaaron fox"

    def test_espn_ascii_name_finds_nba_accented_row(self) -> None:
        pm = {"Jusuf Nurkić": _row(3, -8.6)}
        assert _lookup_player(pm, "Jusuf Nurkic") is pm["Jusuf Nurkić"]
        assert _lookup_player(pm, "Someone Else") is None

    def test_accented_injury_uses_real_stats_not_default(self) -> None:
        pm = {"Jusuf Nurkić": _row(3, 6.0, GP=60)}
        [absence] = _build_player_absences(
            [{"player_name": "Jusuf Nurkic", "status": "OUT"}], pm, team_nrtg=0.0,
        )
        assert absence.nrtg_impact < -1.0  # default for unknown players is −0.8


class TestTeamContext:
    def test_mover_measured_against_team_his_stats_came_from(self) -> None:
        """Devin Carter: −7.6 on SAC (−9.8) is above SAC's level, so losing him
        hurts BOS a little — not +2.9 (old: relative to BOS's +5)."""
        pm = _with_team_context(
            {"Devin Carter": _row(1, -7.6, mpg=18.4, GP=38, CURRENT_GP=0, PRIOR_GP=38,
                                  CURRENT_WEIGHT=0.0)},
            CONTEXT,
        )
        assert pm["Devin Carter"]["TEAM_CONTEXT_NRTG"] == pytest.approx(-9.8)
        [absence] = _build_player_absences(
            [{"player_name": "Devin Carter", "status": "OUT"}], pm, team_nrtg=5.0,
        )
        assert absence.nrtg_impact < 0

    def test_context_blends_current_and_prior_team_by_weight(self) -> None:
        pm = _with_team_context(
            {"P": _row(1, 0.0, CURRENT_GP=10, PRIOR_GP=70, CURRENT_WEIGHT=0.5)}, CONTEXT,
        )
        assert pm["P"]["TEAM_CONTEXT_NRTG"] == pytest.approx(0.5 * 5.0 + 0.5 * -9.8)

    def test_unknown_player_keeps_row_and_falls_back_to_team_nrtg(self) -> None:
        pm = _with_team_context({"Q": _row(99, 4.0, GP=70)}, CONTEXT)
        assert "TEAM_CONTEXT_NRTG" not in pm["Q"]
        [absence] = _build_player_absences(
            [{"player_name": "Q", "status": "OUT"}], pm, team_nrtg=4.0,
        )
        assert absence.nrtg_impact == pytest.approx(0.0)


class TestGamesPlayedShrink:
    def test_six_game_sample_barely_moves_team(self) -> None:
        """Beal: 6 GP at −9.3 used to make LAC +2.9 better without him."""
        beal = _row(2, -9.3, mpg=20.2, CURRENT_GP=0, PRIOR_GP=6)
        full = _row(2, -9.3, mpg=20.2, CURRENT_GP=0, PRIOR_GP=80)
        [small] = _build_player_absences([{"player_name": "B", "status": "OUT"}], {"B": beal},
                                         team_nrtg=2.0)
        [big] = _build_player_absences([{"player_name": "B", "status": "OUT"}], {"B": full},
                                       team_nrtg=2.0)
        assert 0 < small.nrtg_impact < 0.45 * big.nrtg_impact

    def test_blended_rows_shrink_on_both_seasons_games(self) -> None:
        rows = blend_player_metrics(
            {"P": {"GP": 1, "MIN": 30.0, "E_NET_RATING": 9.0}},
            {"P": {"GP": 70, "MIN": 30.0, "E_NET_RATING": 9.0}},
            k=10,
        )
        assert rows["P"]["CURRENT_GP"] == 1 and rows["P"]["PRIOR_GP"] == 70
        [absence] = _build_player_absences([{"player_name": "P", "status": "OUT"}], rows)
        # 71 GP → ~88% of the unshrunk impact (−9 × 30/48 × 0.6 = −3.4).
        assert absence.nrtg_impact == pytest.approx(-3.375 * 71 / 81, abs=0.02)


class TestReassignInjuryTeams:
    def test_traded_player_moves_to_roster_team(self) -> None:
        injuries = {
            "TOR": [{"player_name": "Brandon Ingram", "team": "TOR", "status": "OUT"},
                    {"player_name": "Rookie Guy", "team": "TOR", "status": "OUT"}],
        }
        pm = {"Brandon Ingram": _row(2, 0.8)}
        out = _reassign_injury_teams(injuries, pm, CONTEXT)
        assert [i["player_name"] for i in out["LAC"]] == ["Brandon Ingram"]
        assert out["LAC"][0]["team"] == "LAC"
        assert [i["player_name"] for i in out["TOR"]] == ["Rookie Guy"]  # unknown: stays
        assert out["LAC"][0]["team_corrected_from"] == "TOR"
        assert injuries["TOR"][0]["team"] == "TOR"  # input not mutated

    def test_no_context_is_noop(self) -> None:
        injuries = {"TOR": [{"player_name": "Brandon Ingram", "team": "TOR"}]}
        assert _reassign_injury_teams(injuries, {}, {}) is injuries
