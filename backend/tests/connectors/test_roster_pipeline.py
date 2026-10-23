"""Roster connector + pipeline integration with mocked NBA API responses."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.connectors.nba_api import NBAApiConnector
from app.services import pipeline
from app.services.pipeline import NBA_ABBR_TO_TEAM_ID, NBA_TEAM_ID_TO_ABBR

ROSTER_HEADERS = ["TeamID", "SEASON", "LeagueID", "PLAYER", "PLAYER_ID", "HOW_ACQUIRED"]


def _roster_response(team_id: int, player_ids: list[int]) -> dict[str, Any]:
    return {
        "resultSets": [
            {
                "name": "CommonTeamRoster",
                "headers": ROSTER_HEADERS,
                "rowSet": [[team_id, "2026", "00", f"P{pid}", pid, ""] for pid in player_ids],
            },
            {"name": "Coaches", "headers": ["TEAM_ID"], "rowSet": [[team_id]]},
        ]
    }


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    pipeline.clear_pipeline_cache()


class TestGetTeamRoster:
    async def test_parses_roster_result_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []

        async def fake_fetch(
            self: NBAApiConnector, endpoint: str, params: dict[str, Any] | None = None,
        ) -> Any:
            calls.append((endpoint, params or {}))
            return _roster_response(1610612755, [2544, 1627759])

        monkeypatch.setattr(NBAApiConnector, "fetch", fake_fetch)
        rows = await NBAApiConnector().get_team_roster(1610612755, "2026-27")
        assert [r["PLAYER_ID"] for r in rows] == [2544, 1627759]
        params = {"LeagueID": "00", "Season": "2026-27", "TeamID": 1610612755}
        assert calls == [("/commonteamroster", params)]

    async def test_missing_result_set_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_fetch(
            self: NBAApiConnector, endpoint: str, params: dict[str, Any] | None = None,
        ) -> Any:
            return {"resultSets": [{"name": "Coaches", "headers": [], "rowSet": []}]}

        monkeypatch.setattr(NBAApiConnector, "fetch", fake_fetch)
        assert await NBAApiConnector().get_team_roster(1610612755, "2026-27") == []


class TestFetchRosters:
    async def test_failed_and_tiny_rosters_are_omitted(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_roster(
            self: NBAApiConnector, team_id: int, season: str | None = None,
        ) -> list[dict[str, Any]]:
            abbr = NBA_TEAM_ID_TO_ABBR[team_id]
            if abbr == "PHI":
                raise RuntimeError("HTTP 500")
            n = 3 if abbr == "BOS" else 15
            return [{"PLAYER_ID": team_id * 100 + i} for i in range(n)]

        monkeypatch.setattr(NBAApiConnector, "get_team_roster", fake_roster)
        warnings: list[str] = []
        rosters = await pipeline._fetch_rosters("2026-27", warnings)
        assert len(rosters) == 28
        assert "PHI" not in rosters and "BOS" not in rosters
        assert len(rosters["CLE"]) == 15
        assert any("Rosters unavailable for 2 teams" in w for w in warnings)


# ─── _fetch_team_ratings end-to-end with mocked season data ────────

def _prior_player(pid: int, nrtg: float, mpg: float = 24.0) -> dict[str, Any]:
    return {
        "PLAYER_ID": pid, "PLAYER_NAME": f"P{pid}", "GP": 70, "MIN": mpg,
        "E_OFF_RATING": 115 + nrtg / 2, "E_DEF_RATING": 115 - nrtg / 2, "E_NET_RATING": nrtg,
    }


def _ten_man_rosters() -> dict[str, list[int]]:
    return {abbr: [tid * 100 + i for i in range(10)] for tid, abbr in NBA_TEAM_ID_TO_ABBR.items()}


def _mock_season_data(
    monkeypatch: pytest.MonkeyPatch,
    current_rosters: dict[str, list[int]],
) -> None:
    """Flat 2025-26 league (every team NRtg +0.3), no 2026-27 games yet."""
    prior_rosters = _ten_man_rosters()
    prior_players = {
        f"P{pid}": _prior_player(pid, 0.3) for ids in prior_rosters.values() for pid in ids
    }
    for pid, nrtg in {2544: 3.8, 1627759: 5.4, 1629014: 1.3, 203484: -1.0}.items():
        prior_players[f"P{pid}"] = _prior_player(pid, nrtg, mpg=33.0)
    prior_teams = {
        abbr: {"ortg": 115.15, "drtg": 114.85, "nrtg": 0.3, "pace": 99.0, "gp": 82.0}
        for abbr in NBA_TEAM_ID_TO_ABBR.values()
    }

    async def fake_team_ratings(
        season: str, warnings: list[str], ttl_seconds: int = 3600,
    ) -> dict[str, Any]:
        return prior_teams if season == "2025-26" else {}

    async def fake_rosters(
        season: str, warnings: list[str], ttl_seconds: int = 0,
    ) -> dict[str, list[int]]:
        return prior_rosters if season == "2025-26" else current_rosters

    async def fake_players(
        season: str, warnings: list[str], ttl_seconds: int = 3600,
    ) -> dict[str, Any]:
        return prior_players if season == "2025-26" else {}

    monkeypatch.setattr(pipeline, "current_season", lambda: "2026-27")
    monkeypatch.setattr(pipeline, "_fetch_season_team_ratings", fake_team_ratings)
    monkeypatch.setattr(pipeline, "_fetch_rosters", fake_rosters)
    monkeypatch.setattr(pipeline, "_fetch_season_player_metrics", fake_players)


def _phi_rebuilt_rosters() -> dict[str, list[int]]:
    phi = NBA_ABBR_TO_TEAM_ID["PHI"]
    rosters = _ten_man_rosters()
    rosters["PHI"] = [phi * 100 + i for i in range(6)] + [2544, 1627759, 1629014, 203484]
    return rosters


class TestFetchTeamRatingsRosterPrior:
    async def test_phi_prior_reflects_new_roster(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_season_data(monkeypatch, _phi_rebuilt_rosters())
        ratings = await pipeline._fetch_team_ratings([])

        phi = ratings["PHI"]
        assert phi["prior_source"] == "roster"
        assert phi["last_season_nrtg"] == 0.3
        # Clearly above last season's +0.3 and every unchanged team (margins
        # are after regression to the mean, PRIOR_REGRESSION).
        assert phi["prior_nrtg"] > phi["last_season_nrtg"] + 0.3
        others = max(r["prior_nrtg"] for abbr, r in ratings.items() if abbr != "PHI")
        assert phi["prior_nrtg"] > others + 0.6
        assert phi["nrtg"] == pytest.approx(phi["prior_nrtg"], abs=0.01)  # 0 GP → all prior
        # 40% of old minutes left; 4 × 33 of 240 rotation minutes are new.
        assert phi["roster_turnover"] == pytest.approx((0.4 + 132 / 240) / 2, abs=0.01)
        assert phi["stale_prior"] is False
        assert ratings["CLE"]["roster_turnover"] == 0.0
        assert sum(r["nrtg"] for r in ratings.values()) / 30 == pytest.approx(0.0, abs=0.05)

    async def test_no_current_rosters_falls_back_and_flags_unknown_turnover(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _mock_season_data(monkeypatch, {})
        warnings: list[str] = []
        ratings = await pipeline._fetch_team_ratings(warnings)

        phi = ratings["PHI"]
        assert phi["prior_source"] == "team"
        assert phi["nrtg"] == pytest.approx(0.3)
        assert phi["roster_turnover"] is None
        assert phi["stale_prior"] is True
        assert any("Roster-based prior unavailable" in w for w in warnings)


class TestStalePriorCapsVerdicts:
    async def _analyse(self, monkeypatch: pytest.MonkeyPatch, stale: bool) -> Any:
        def fake_prices(away: str, home: str, game_date: date, event: Any) -> dict[str, Any]:
            return {"moneyline_home_yes": 0.25, "spread_home_yes": 0.5, "spread_line": 6.5}

        monkeypatch.setattr(pipeline, "_find_polymarket_prices", fake_prices)
        home = {"ortg": 120.0, "drtg": 108.0, "nrtg": 12.0, "pace": 100.0,
                "prior_source": "team", "roster_turnover": 0.5, "stale_prior": stale}
        away = {"ortg": 110.0, "drtg": 116.0, "nrtg": -6.0, "pace": 100.0,
                "prior_source": "roster", "roster_turnover": 0.1, "stale_prior": False}
        return await pipeline._process_single_game(
            game_raw={"home_team": "PHI", "away_team": "BOS", "game_id": "g1", "game_status": 1},
            game_date=date(2026, 10, 22),
            ratings_data={"PHI": home, "BOS": away},
            standings_data={}, injuries_data={}, player_metrics={},
            polymarket_event=None, warnings=[],
        )

    async def test_stale_prior_downgrades_confidence_and_caps(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        analysis = await self._analyse(monkeypatch, stale=True)
        assert analysis.model.confidence == "LOW"
        assert analysis.markets["moneyline"].edge.best_edge >= 0.12
        assert {m.edge.verdict for m in analysis.markets.values()} <= {"LEAN", "NO EDGE"}
        assert analysis.home.stale_prior is True
        assert "Stale roster prior for PHI" in analysis.data_quality.warnings[0]
        assert pipeline._extract_top_edges([analysis]) == []

    async def test_fresh_prior_keeps_strong_buy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Market guard off: this test is about the stale-prior cap only.
        monkeypatch.setattr(pipeline.settings, "market_disagreement_threshold", 1.0)
        analysis = await self._analyse(monkeypatch, stale=False)
        assert analysis.model.confidence == "MEDIUM"
        assert analysis.markets["moneyline"].edge.verdict == "STRONG BUY"
