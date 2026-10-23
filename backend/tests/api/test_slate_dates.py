"""Tests for the dashboard's slate picker endpoints (/games/schedule, /games/date)."""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.api.v1 import games
from app.main import app
from app.schemas.game import DailyAnalysis

client = TestClient(app)
TODAY = date(2026, 10, 22)


def _patch(monkeypatch, counts: dict[int, int]):
    monkeypatch.setattr(games, "_get_nba_game_date", lambda: TODAY)

    async def fake_schedule(d):
        return [{}] * counts.get((d - TODAY).days, 0)

    monkeypatch.setattr(games, "fetch_schedule", fake_schedule)


def test_schedule_keeps_today_and_days_with_games(monkeypatch):
    _patch(monkeypatch, {0: 0, 1: 12, 2: 0, 3: 7})
    res = client.get("/api/v1/games/schedule?days=3").json()
    assert res == [
        {"date": "2026-10-22", "games_count": 0, "is_today": True},
        {"date": "2026-10-23", "games_count": 12, "is_today": False},
        {"date": "2026-10-25", "games_count": 7, "is_today": False},
    ]


def test_date_endpoint_rejects_past_and_far_future(monkeypatch):
    _patch(monkeypatch, {})
    assert client.get("/api/v1/games/date/2026-10-21").status_code == 400
    far = TODAY + timedelta(days=games.MAX_DAYS_AHEAD + 1)
    assert client.get(f"/api/v1/games/date/{far}").status_code == 400


def test_date_endpoint_runs_pipeline_for_that_date(monkeypatch):
    _patch(monkeypatch, {})
    seen = []

    async def fake_pipeline(game_date=None, injury_overrides=None):
        seen.append(game_date)
        return DailyAnalysis(date=game_date, games_count=0, games=[], top_edges=[])

    monkeypatch.setattr(games, "run_daily_pipeline", fake_pipeline)
    res = client.get("/api/v1/games/date/2026-10-24")
    assert res.status_code == 200 and res.json()["date"] == "2026-10-24"
    assert seen == [date(2026, 10, 24)]


def test_overrides_use_selected_date(monkeypatch):
    _patch(monkeypatch, {})
    seen = []

    async def fake_pipeline(game_date=None, injury_overrides=None):
        seen.append((game_date, injury_overrides))
        return DailyAnalysis(date=game_date or TODAY, games_count=0, games=[], top_edges=[])

    monkeypatch.setattr(games, "run_daily_pipeline", fake_pipeline)
    body = {"injury_overrides": {"Jarrett Allen": "OFF"}, "game_date": "2026-10-24"}
    assert client.post("/api/v1/games/today", json=body).status_code == 200
    assert seen == [(date(2026, 10, 24), {"Jarrett Allen": "OFF"})]
