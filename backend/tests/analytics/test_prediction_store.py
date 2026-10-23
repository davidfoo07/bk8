"""Tests for locking saved predictions at tip-off."""

import json
from datetime import UTC, date, datetime, timedelta

from app.models.database import async_session_factory
from app.models.tables import DailyPrediction
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


async def _saved(game_date: date = date(2026, 10, 22)) -> dict | None:
    async with async_session_factory() as session:
        row = await session.get(DailyPrediction, game_date)
        return row.data if row else None


async def _store(data: dict, game_date: date = date(2026, 10, 22)) -> None:
    async with async_session_factory() as session, session.begin():
        session.add(DailyPrediction(game_date=game_date, data=data, games_count=len(data["games"])))


class _Analysis:
    """Stand-in for DailyAnalysis: save_predictions only needs date + JSON."""

    def __init__(self, games: list[dict]):
        self.date = date(2026, 10, 22)
        self._data = {"date": "2026-10-22", "games": games, "top_edges": []}

    def model_dump_json(self) -> str:
        return json.dumps(self._data)


class TestSavePredictions:
    async def test_first_save_creates_row(self):
        future = datetime.now(UTC) + timedelta(hours=3)
        assert await prediction_store.save_predictions(_Analysis([_game("g", future, prob=0.6)]))
        saved = await _saved()
        assert saved["games"][0]["model"]["home_win_prob"] == 0.6
        assert saved["games_count"] == 1

    async def test_rerun_before_tipoff_updates(self):
        future = datetime.now(UTC) + timedelta(hours=3)
        await prediction_store.save_predictions(_Analysis([_game("g", future, prob=0.6)]))
        await prediction_store.save_predictions(_Analysis([_game("g", future, prob=0.7)]))
        assert (await _saved())["games"][0]["model"]["home_win_prob"] == 0.7

    async def test_rerun_after_tipoff_does_not_change_saved_prediction(self):
        past = datetime.now(UTC) - timedelta(hours=1)
        pre_game = {"date": "2026-10-22", "games": [_game("g", past, prob=0.40)], "top_edges": []}
        await _store(pre_game)

        await prediction_store.save_predictions(_Analysis([_game("g", past, status=3, prob=0.90)]))

        assert (await _saved())["games"][0]["model"]["home_win_prob"] == 0.40

    async def test_nothing_written_when_every_game_already_started(self):
        past = datetime.now(UTC) - timedelta(hours=1)
        assert await prediction_store.save_predictions(_Analysis([_game("g", past)])) is False
        assert await _saved() is None


class TestLoadAndImport:
    async def test_import_json_files_then_load_and_list(self, tmp_path):
        day = {"date": "2026-10-21", "games_count": 0, "games": [], "top_edges": [],
               "saved_at": "2026-10-22T11:58:29.843877"}
        (tmp_path / "2026-10-21.json").write_text(json.dumps(day))
        (tmp_path / "notes.json").write_text("{}")  # not a date → skipped

        assert await prediction_store.import_json_files(tmp_path) == ["2026-10-21"]
        assert await prediction_store.import_json_files(tmp_path) == []  # idempotent

        loaded = await prediction_store.load_predictions(date(2026, 10, 21))
        assert loaded is not None and loaded.games == []
        listed = await prediction_store.list_saved_dates()
        assert [d["date"] for d in listed] == ["2026-10-21"]

    async def test_load_missing_date(self):
        assert await prediction_store.load_predictions(date(2020, 1, 1)) is None
