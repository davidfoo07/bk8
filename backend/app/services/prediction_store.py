"""Prediction persistence — History, one saved DailyAnalysis per NBA date.

Stored in the ``daily_predictions`` table (date → full analysis as JSONB), so
History lives in the database (local Postgres or Supabase), not on one machine.

IMPORTANT: Pre-game predictions (with full Polymarket edges) are protected.
Later pipeline runs (post-game, when Polymarket has delisted markets) will NOT
overwrite a richer pre-game snapshot.  This ensures the simulation tab always
has the full set of BUY/STRONG BUY bets for grading.

Each game is locked at tip-off: once it has started, its saved version is never
replaced, and a game first seen after tip-off is not saved at all — a
prediction made with in-game knowledge isn't a prediction.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path

from loguru import logger
from sqlalchemy import func, select

from app.models.database import async_session_factory
from app.models.tables import DailyPrediction
from app.schemas.game import DailyAnalysis

# Where History used to live; read once by import_json_files().
LEGACY_PREDICTIONS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "predictions"


def _count_markets(data: dict) -> int:
    """Count total non-empty market entries across all games in a prediction JSON."""
    total = 0
    for game in data.get("games", []):
        markets = game.get("markets", {})
        total += len(markets)
    return total


def _game_market_count(game: dict) -> int:
    """Count markets for a single game."""
    return len(game.get("markets", {}))


def _has_started(game: dict, now: datetime) -> bool:
    """True once a game is live/final or its scheduled tip-off has passed."""
    live = game.get("live") or {}
    if (live.get("game_status") or 1) >= 2:
        return True
    tipoff = game.get("tipoff")
    if not tipoff:
        return False
    try:
        tip = datetime.fromisoformat(str(tipoff).replace("Z", "+00:00"))
    except ValueError:
        return False
    if tip.tzinfo is None:
        tip = tip.replace(tzinfo=UTC)
    return tip <= now


def _lock_started_games(existing: dict | None, new: dict, now: datetime) -> dict:
    """Return ``new`` with every started game replaced by its saved pre-game version.

    Started games with no saved version are dropped. Top edges follow their games:
    frozen games keep their saved edges, dropped games lose theirs.
    """
    existing_games = {g.get("game_id"): g for g in (existing or {}).get("games", [])}
    games: list[dict] = []
    frozen: set[str] = set()
    dropped: set[str] = set()
    for game in new.get("games", []):
        gid = game.get("game_id")
        if not _has_started(game, now):
            games.append(game)
        elif gid in existing_games:
            games.append(existing_games[gid])
            frozen.add(gid)
        else:
            dropped.add(gid)
            logger.info(f"🔒 Not saving {gid}: first seen after tip-off")

    top_edges = [
        e for e in new.get("top_edges", []) if e.get("game_id") not in frozen | dropped
    ] + [e for e in (existing or {}).get("top_edges", []) if e.get("game_id") in frozen]
    top_edges.sort(key=lambda e: e.get("edge") or 0, reverse=True)

    result = dict(new)
    result["games"] = games
    result["games_count"] = len(games)
    result["top_edges"] = top_edges
    return result


def combine_predictions(existing: dict | None, new: dict, now: datetime) -> dict | None:
    """The day's snapshot to store after a pipeline run, or None to leave it as is.

    Per-game merge logic:
      - Started games keep their saved pre-game version (see _lock_started_games).
      - For each game, keep whichever version (existing vs new) has MORE markets.
      - This handles: initial save has 2/6 games with markets, later run has 5/6.
        Result: all 6 games get the best available market data.
    """
    new_data = _lock_started_games(existing, new, now)
    if not new_data["games"]:
        return None
    new_data["saved_at"] = now.isoformat()

    if existing and _count_markets(existing) > 0:
        merged = _merge_predictions(existing, new_data)
        if _count_markets(merged) > _count_markets(new_data):
            merged["saved_at"] = now.isoformat()
            return merged
    return new_data


async def save_predictions(analysis: DailyAnalysis) -> bool:
    """Merge a pipeline run into that date's saved History. Returns True if written."""
    now = datetime.now(UTC)
    async with async_session_factory() as session, session.begin():
        row = await session.get(DailyPrediction, analysis.date, with_for_update=True)
        new = json.loads(analysis.model_dump_json())
        data = combine_predictions(row.data if row else None, new, now)
        if data is None:
            logger.info(f"🔒 Nothing to save for {analysis.date}: every game already tipped off")
            return False
        if row is None:
            session.add(DailyPrediction(
                game_date=analysis.date, data=data, games_count=data["games_count"], saved_at=now,
            ))
        else:
            row.data, row.games_count, row.saved_at = data, data["games_count"], now
    logger.info(
        f"💾 Saved predictions for {analysis.date} "
        f"({data['games_count']} games, {_count_markets(data)} markets)"
    )
    return True


def _merge_predictions(existing: dict, new: dict) -> dict:
    """Merge two prediction snapshots, keeping the richer version per game.

    For each game_id:
      - If only in one snapshot → keep it
      - If in both → keep whichever has more markets
        (tie-break: prefer new data since it has fresher model output)
    """
    # Index existing games by game_id
    existing_games: dict[str, dict] = {}
    for game in existing.get("games", []):
        gid = game.get("game_id", "")
        if gid:
            existing_games[gid] = game

    # Build merged game list from new data, upgrading markets from existing where better
    merged_games = []
    seen_ids = set()

    for game in new.get("games", []):
        gid = game.get("game_id", "")
        seen_ids.add(gid)

        old_game = existing_games.get(gid)
        if old_game and _game_market_count(old_game) > _game_market_count(game):
            # Existing has richer markets — use existing game but update model fields from new
            merged_game = dict(old_game)
            # Keep fresh model predictions from the new run
            merged_game["model"] = game.get("model", old_game.get("model"))
            merged_game["data_quality"] = game.get("data_quality", old_game.get("data_quality"))
            merged_games.append(merged_game)
        else:
            # New has equal or more markets — use new
            merged_games.append(game)

    # Add any games only in existing (shouldn't normally happen, but safety)
    for gid, game in existing_games.items():
        if gid not in seen_ids:
            merged_games.append(game)

    # Build merged result using new data as base (keeps date, top_edges, etc.)
    result = dict(new)
    result["games"] = merged_games
    result["games_count"] = len(merged_games)
    # Recalculate top_edges would be ideal, but we keep new's top_edges
    # since they reflect the latest model run
    return result


def _to_analysis(data: dict) -> DailyAnalysis:
    data = {k: v for k, v in data.items() if k != "saved_at"}
    return DailyAnalysis.model_validate(data)


async def load_predictions(game_date: date) -> DailyAnalysis | None:
    """Load saved predictions for a specific date, or None if not found."""
    async with async_session_factory() as session:
        row = await session.get(DailyPrediction, game_date)
    if row is None:
        return None
    try:
        return _to_analysis(row.data)
    except Exception as e:
        logger.warning(f"Failed to load predictions for {game_date}: {e}")
        return None


async def list_saved_dates() -> list[dict]:
    """All dates with saved predictions, newest first.

    Returns list of {date, games_count, saved_at, file_size_kb}.
    """
    async with async_session_factory() as session:
        rows = await session.execute(
            select(
                DailyPrediction.game_date,
                DailyPrediction.games_count,
                DailyPrediction.saved_at,
                func.pg_column_size(DailyPrediction.data),
            ).order_by(DailyPrediction.game_date.desc())
        )
        return [
            {
                "date": d.isoformat(),
                "games_count": count,
                "saved_at": saved_at.isoformat() if saved_at else None,
                "file_size_kb": round((size or 0) / 1024, 1),
            }
            for d, count, saved_at, size in rows
        ]


async def import_json_files(directory: Path = LEGACY_PREDICTIONS_DIR) -> list[str]:
    """One-off: copy History JSON files (the old storage) into the database.

    Dates already in the database are left alone. Returns the imported dates.
    """
    imported: list[str] = []
    for path in sorted(directory.glob("*.json")):
        try:
            game_date = date.fromisoformat(path.stem)
            data = json.loads(path.read_text(encoding="utf-8"))
            _to_analysis(data)  # validate before storing
        except Exception as e:
            logger.warning(f"Skipping {path.name}: {e}")
            continue
        async with async_session_factory() as session, session.begin():
            if await session.get(DailyPrediction, game_date) is not None:
                continue
            saved_at = data.get("saved_at")
            session.add(DailyPrediction(
                game_date=game_date,
                data=data,
                games_count=data.get("games_count", len(data.get("games", []))),
                saved_at=(
                    datetime.fromisoformat(saved_at).astimezone() if saved_at else datetime.now(UTC)
                ),
            ))
        imported.append(path.stem)
    return imported
