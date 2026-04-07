"""Tests for the REST API endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestHealthEndpoint:
    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestGamesEndpoints:
    def test_get_todays_games(self):
        response = client.get("/api/v1/games/today")
        assert response.status_code == 200
        data = response.json()
        assert "games" in data
        assert "top_edges" in data
        assert "date" in data

    def test_get_ai_prompt(self):
        response = client.get("/api/v1/games/today/ai-prompt")
        assert response.status_code == 200
        data = response.json()
        assert "prompt" in data
        assert isinstance(data["prompt"], str)
        assert len(data["prompt"]) > 0

    def test_get_game_detail(self):
        response = client.get("/api/v1/games/2026-04-07_CLE_MEM")
        assert response.status_code == 200
        data = response.json()
        assert data["game_id"] == "2026-04-07_CLE_MEM"

    def test_get_game_not_found(self):
        response = client.get("/api/v1/games/nonexistent")
        assert response.status_code == 404


class TestTeamsEndpoints:
    def test_list_teams(self):
        response = client.get("/api/v1/teams")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 30  # All NBA teams

    def test_get_team(self):
        response = client.get("/api/v1/teams/CLE")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "CLE"
        assert data["full_name"] == "Cleveland Cavaliers"

    def test_get_team_not_found(self):
        response = client.get("/api/v1/teams/XYZ")
        assert response.status_code == 404


class TestBetsEndpoints:
    def test_create_bet(self):
        bet_data = {
            "game_id": "2026-04-07_CLE_MEM",
            "market_type": "moneyline",
            "selection": "MEM wins",
            "side": "NO",
            "entry_price": 0.28,
            "model_probability": 0.365,
            "edge_at_entry": 0.085,
            "amount_usd": 50.0,
            "kelly_fraction": 0.041,
            "notes": "Test bet",
        }
        response = client.post("/api/v1/bets", json=bet_data)
        assert response.status_code == 200
        data = response.json()
        assert data["selection"] == "MEM wins"
        assert data["id"] > 0

    def test_get_bet_history(self):
        response = client.get("/api/v1/bets/history")
        assert response.status_code == 200
        data = response.json()
        assert "total_bets" in data
        assert "bets" in data


class TestInjuryEndpoints:
    def test_override_injury(self):
        override_data = {
            "player_name": "Cade Cunningham",
            "player_id": "1630595",
            "team": "DET",
            "status": "OUT",
            "reason": "Rest",
        }
        response = client.post("/api/v1/injuries/override", json=override_data)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "OUT"
        assert data["source"] == "Manual Override"

    def test_get_overrides(self):
        response = client.get("/api/v1/injuries/overrides")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_invalid_status(self):
        response = client.post("/api/v1/injuries/override", json={
            "player_name": "Test",
            "player_id": "999",
            "team": "TST",
            "status": "INVALID",
        })
        assert response.status_code == 400
