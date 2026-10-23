"""Tests for the NBA connector's disk cache, 403 pause and schedule fallback."""

import asyncio
import os
import time
from datetime import date

import httpx
import pytest

from app.connectors import disk_cache, nba_api
from app.connectors.nba_api import NBAApiConnector, NBABlockedError
from app.services import pipeline

ROSTER = "/commonteamroster"
PARAMS = {"TeamID": 1610612755, "Season": "2026-27"}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(disk_cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(nba_api, "_blocked_until", 0.0)
    nba_api.stale_endpoints.clear()
    yield
    nba_api.stale_endpoints.clear()


def _run(coro):
    return asyncio.run(coro)


class FakeClient:
    """Stands in for httpx.AsyncClient; records calls."""

    def __init__(self, status: int = 200, payload: dict | None = None):
        self.status, self.payload, self.calls = status, payload or {"ok": True}, 0

    async def get(self, endpoint, params=None):
        self.calls += 1
        req = httpx.Request("GET", f"https://stats.nba.com/stats{endpoint}")
        return httpx.Response(self.status, json=self.payload, request=req)


def _connector(client: FakeClient) -> NBAApiConnector:
    nba = NBAApiConnector()

    async def get_client():
        return client

    nba._get_client = get_client
    return nba


class TestDiskCache:
    def test_fresh_cache_skips_network(self):
        client = FakeClient(payload={"v": 1})
        nba = _connector(client)
        assert _run(nba.fetch(ROSTER, PARAMS)) == {"v": 1}
        assert _run(nba.fetch(ROSTER, PARAMS)) == {"v": 1}
        assert client.calls == 1

    def test_expired_cache_refetches(self):
        client = FakeClient(payload={"v": 1})
        nba = _connector(client)
        _run(nba.fetch(ROSTER, PARAMS))
        path = disk_cache.cache_path("nba", ROSTER, PARAMS)
        old = time.time() - nba_api.DISK_CACHE_TTL[ROSTER] - 60
        os.utime(path, (old, old))
        _run(nba.fetch(ROSTER, PARAMS))
        assert client.calls == 2

    def test_live_endpoints_not_cached(self):
        client = FakeClient()
        nba = _connector(client)
        _run(nba.fetch("/scoreboardv3", {"GameDate": "2026-10-22"}))
        _run(nba.fetch("/scoreboardv3", {"GameDate": "2026-10-22"}))
        assert client.calls == 2

    def test_stale_copy_served_when_blocked(self):
        _run(_connector(FakeClient(payload={"v": "saved"})).fetch(ROSTER, PARAMS))
        path = disk_cache.cache_path("nba", ROSTER, PARAMS)
        old = time.time() - 3 * 86400
        os.utime(path, (old, old))

        blocked = FakeClient(status=403)
        assert _run(_connector(blocked).fetch(ROSTER, PARAMS)) == {"v": "saved"}
        assert ROSTER in nba_api.stale_endpoints


class TestBlockPause:
    def test_403_is_not_retried_and_pauses_calls(self):
        client = FakeClient(status=403)
        nba = _connector(client)
        with pytest.raises(NBABlockedError):
            _run(nba.fetch(ROSTER, PARAMS))
        assert client.calls == 1  # no retries on a block

        with pytest.raises(NBABlockedError):
            _run(nba.fetch("/playerestimatedmetrics", {"Season": "2026-27"}))
        assert client.calls == 1  # paused: no request sent at all


class TestScheduleFallback:
    def test_nba_used_when_espn_fails(self, monkeypatch):
        async def espn_down(self, game_date):
            raise httpx.ConnectError("espn down")

        nba_game = {
            "gameId": "0022600001", "gameStatus": 3, "gameStatusText": "Final",
            "homeTeam": {"teamTricode": "PHI", "score": 114},
            "awayTeam": {"teamTricode": "CLE", "score": 106},
        }

        async def nba_games(self, game_date=None):
            return [nba_game]

        monkeypatch.setattr(pipeline.ESPNConnector, "get_games", espn_down)
        monkeypatch.setattr(pipeline.NBAApiConnector, "get_todays_games", nba_games)
        scores = _run(pipeline.fetch_scores(date(2026, 10, 22)))
        assert scores == {"CLE_PHI": {"home_score": 114, "away_score": 106, "status": 3}}

    def test_espn_preferred(self, monkeypatch):
        async def espn_games(self, game_date):
            return [{
                "game_id": "2026-10-22_DEN_OKC", "home_team": "OKC", "away_team": "DEN",
                "home_score": 36, "away_score": 43, "game_status": 2,
            }]

        async def nba_should_not_run(self, game_date=None):
            raise AssertionError("NBA scoreboard called although ESPN worked")

        monkeypatch.setattr(pipeline.ESPNConnector, "get_games", espn_games)
        monkeypatch.setattr(pipeline.NBAApiConnector, "get_todays_games", nba_should_not_run)
        scores = _run(pipeline.fetch_scores(date(2026, 10, 22)))
        assert scores["DEN_OKC"]["status"] == 2
