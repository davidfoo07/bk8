"""Tests for locking saved predictions at tip-off."""

import json
from datetime import UTC, date, datetime, timedelta

import pytest

from app.services import prediction_store
from app.services.prediction_store import _has_started, _lock_started_games

NOW = datetime(2026, 10, 22, 23, 30, tzinfo=UTC)


def _game(gid: str, tipoff: datetime, status: int = 1, prob: float = 0.5) -> dict:
    return {
        "game_id": gid,
        "tipoff": tipoff.isoformat().replace("+00:00", "Z"),
        "live": {"game_status": status},
        "model": {"home_win_prob": prob},
        "markets": {"moneyline": {}},
    }


def _edge(gid: str, edge: float) -> dict:
    return {"game_id": gid, "edge": edge}


class TestHasStarted:
    def test_before_tipoff(self):
        assert not _has_started(_game("a", NOW + timedelta(minutes=5)), NOW)

    def test_after_tipoff(self):
        assert _has_started(_game("a", NOW - timedelta(minutes=5)), NOW)

    def test_live_status_counts_even_before_scheduled_tipoff(self):
        assert _has_started(_game("a", NOW + timedelta(minutes=5), status=2), NOW)

    def test_no_tipoff_not_started(self):
        assert not _has_started({"game_id": "a"}, NOW)


class TestLockStartedGames:
    def test_started_game_keeps_saved_pre_game_version(self):
        existing = {
            "games": [_game("early", NOW - timedelta(hours=1), prob=0.40)],
            "top_edges": [_edge("early", 0.10)],
        }
        new = {
            "games": [
                _game("early", NOW - timedelta(hours=1), status=2, prob=0.90),
                _game("late", NOW + timedelta(hours=2), prob=0.60),
            ],
            "top_edges": [_edge("early", 0.30), _edge("late", 0.05)],
        }
        out = _lock_started_games(existing, new, NOW)
        by_id = {g["game_id"]: g for g in out["games"]}
        assert by_id["early"]["model"]["home_win_prob"] == 0.40
        assert by_id["late"]["model"]["home_win_prob"] == 0.60
        assert out["top_edges"] == [_edge("early", 0.10), _edge("late", 0.05)]

    def test_game_first_seen_after_tipoff_is_dropped(self):
        new = {
            "games": [
                _game("missed", NOW - timedelta(hours=1), status=3),
                _game("upcoming", NOW + timedelta(hours=1)),
            ],
            "top_edges": [_edge("missed", 0.2), _edge("upcoming", 0.1)],
        }
        out = _lock_started_games(None, new, NOW)
        assert [g["game_id"] for g in out["games"]] == ["upcoming"]
        assert out["games_count"] == 1
        assert out["top_edges"] == [_edge("upcoming", 0.1)]


class TestSavePredictions:
    @pytest.fixture(autouse=True)
    def _tmp_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(prediction_store, "PREDICTIONS_DIR", tmp_path)
        self.dir = tmp_path

    class _Analysis:
        def __init__(self, games: list[dict]):
            self.date = date(2026, 10, 22)
            self._data = {"date": "2026-10-22", "games": games, "top_edges": []}

        def model_dump_json(self) -> str:
            return json.dumps(self._data)

    def test_rerun_after_tipoff_does_not_change_saved_prediction(self):
        # Pre-game save already on disk for a game that has since tipped off.
        past = datetime.now(UTC) - timedelta(hours=1)
        pre_game = {"date": "2026-10-22", "games": [_game("g", past, prob=0.40)], "top_edges": []}
        (self.dir / "2026-10-22.json").write_text(json.dumps(pre_game))

        prediction_store.save_predictions(self._Analysis([_game("g", past, status=3, prob=0.90)]))

        saved = json.loads((self.dir / "2026-10-22.json").read_text())
        assert saved["games"][0]["model"]["home_win_prob"] == 0.40

    def test_nothing_written_when_every_game_already_started(self):
        past = datetime.now(UTC) - timedelta(hours=1)
        assert prediction_store.save_predictions(self._Analysis([_game("g", past)])) is None
        assert not (self.dir / "2026-10-22.json").exists()
