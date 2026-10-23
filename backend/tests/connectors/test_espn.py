"""Tests for the ESPN connector parsers (recorded 2026-10-22 responses)."""

import copy
import json
from datetime import date
from pathlib import Path

import pytest

from app.connectors.espn import _clock, parse_boxscore, parse_scoreboard
from app.schemas.game import LivePlayerStats

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "espn"
GAME_DATE = date(2026, 10, 22)


@pytest.fixture
def scoreboard() -> dict:
    return json.loads((FIXTURES / "scoreboard_2026-10-22.json").read_text())


@pytest.fixture
def summary() -> dict:
    return json.loads((FIXTURES / "summary_den_okc_live.json").read_text())


class TestParseScoreboard:
    def test_games_and_ids(self, scoreboard):
        games = parse_scoreboard(scoreboard, GAME_DATE)
        assert [g["game_id"] for g in games] == ["2026-10-22_CLE_PHI", "2026-10-22_DEN_OKC"]
        assert games[1]["espn_event_id"] == "401909094"

    def test_final_game(self, scoreboard):
        g = parse_scoreboard(scoreboard, GAME_DATE)[0]
        assert (g["game_status"], g["game_status_text"]) == (3, "Final")
        assert (g["away_score"], g["home_score"]) == (106, 114)
        assert [p["score"] for p in g["home_periods"]] == [18, 27, 37, 32]
        assert g["game_clock"] == ""
        assert g["venue"] == "Xfinity Mobile Arena"
        assert g["tipoff"].isoformat() == "2026-10-22T23:00:00+00:00"

    def test_live_game(self, scoreboard):
        g = parse_scoreboard(scoreboard, GAME_DATE)[1]
        assert g["game_status"] == 2
        assert (g["period"], g["game_clock"]) == (2, "3:30")
        assert (g["away_score"], g["home_score"]) == (43, 36)

    def test_leader_only_takes_own_rebounds_assists(self, scoreboard):
        cle_phi = parse_scoreboard(scoreboard, GAME_DATE)[0]
        # Maxey led PHI in points and assists, LeBron in rebounds
        assert cle_phi["home_leader"] == {"name": "Tyrese Maxey", "points": 32, "assists": 6}

    def test_scheduled_game_shows_eastern_tipoff(self, scoreboard):
        data = copy.deepcopy(scoreboard)
        ev = data["events"][1]
        ev["status"]["type"].update(state="pre", name="STATUS_SCHEDULED")
        g = parse_scoreboard(data, GAME_DATE)[1]
        assert g["game_status"] == 1
        assert g["game_status_text"] == "9:30 pm ET"
        assert (g["period"], g["game_clock"]) == (0, "")

    def test_espn_abbreviations_are_mapped(self, scoreboard):
        data = copy.deepcopy(scoreboard)
        for c in data["events"][0]["competitions"][0]["competitors"]:
            c["team"]["abbreviation"] = "GS" if c["homeAway"] == "home" else "WSH"
        assert parse_scoreboard(data, GAME_DATE)[0]["game_id"] == "2026-10-22_WAS_GSW"


class TestLiveStatusText:
    def _live(self, scoreboard, clock, short, name="STATUS_IN_PROGRESS"):
        data = copy.deepcopy(scoreboard)
        status = data["events"][1]["status"]
        status["displayClock"] = clock
        status["type"].update(name=name, shortDetail=short)
        return parse_scoreboard(data, GAME_DATE)[1]["game_status_text"]

    def test_running_clock(self, scoreboard):
        assert self._live(scoreboard, "5:47", "5:47 - 3rd") == "5:47 - 3rd"

    def test_last_minute_seconds(self, scoreboard):
        assert self._live(scoreboard, "45.2", "45.2 - 4th") == "0:45 - 4th"

    def test_end_of_quarter(self, scoreboard):
        assert self._live(scoreboard, "0.0", "0.0 - 3rd") == "End of 3rd"

    def test_halftime(self, scoreboard):
        assert self._live(scoreboard, "0.0", "Halftime", "STATUS_HALFTIME") == "Halftime"


class TestClock:
    @pytest.mark.parametrize(
        "raw, expected",
        [("3:30", "3:30"), ("45.2", "0:45"), ("0.0", "0:00"), ("", ""), (None, "")],
    )
    def test_clock(self, raw, expected):
        assert _clock(raw) == expected


class TestParseBoxscore:
    def test_sides_and_dnp(self, summary):
        home, away = parse_boxscore(summary)
        assert {p["team"] for p in home} == {"OKC"}
        assert {p["team"] for p in away} == {"DEN"}
        assert len(away) == 10  # 14 listed, 4 did not play
        assert len(home) == 11

    def test_player_fields_fit_schema(self, summary):
        _, away = parse_boxscore(summary)
        gordon = LivePlayerStats(**next(p for p in away if p["name"] == "Aaron Gordon"))
        assert (gordon.minutes, gordon.points, gordon.rebounds, gordon.assists) == ("11", 8, 3, 1)
        assert gordon.plus_minus == 6
        assert gordon.fg_pct == pytest.approx(0.667)
        assert gordon.three_pct == 0.0
        assert gordon.position == "F"
