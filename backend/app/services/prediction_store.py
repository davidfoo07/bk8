"""Prediction persistence — save/load daily analyses as JSON files.

Simple file-based storage: one JSON per date under backend/data/predictions/.
No DB dependency, no ORM, just Pydantic serialization.

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

from app.schemas.game import DailyAnalysis

# Resolve to backend/data/predictions/ relative to this file
PREDICTIONS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "predictions"


def _ensure_dir() -> None:
    """Create the predictions directory if it doesn't exist."""
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)


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


def save_predictions(analysis: DailyAnalysis) -> Path | None:
    """Save a DailyAnalysis to a dated JSON file.

    Per-game merge logic:
      - For each game, keep whichever version (existing vs new) has MORE markets.
      - This handles: initial save has 2/6 games with markets, later run has 5/6.
        Result: all 6 games get the best available market data.
      - Global fallback: if existing has strictly more total markets AND more games,
        skip entirely (e.g. post-game run where Polymarket delisted everything).
    """
    _ensure_dir()
    filepath = PREDICTIONS_DIR / f"{analysis.date.isoformat()}.json"

    existing_data: dict | None = None
    if filepath.exists():
        try:
            existing_data = json.loads(filepath.read_text(encoding="utf-8"))
        except Exception:
            existing_data = None  # Corrupted file — overwrite it

    new_data = _lock_started_games(
        existing_data, json.loads(analysis.model_dump_json()), datetime.now(UTC)
    )
    if not new_data["games"]:
        logger.info(f"🔒 Nothing to save for {analysis.date}: every game already tipped off")
        return None
    new_data["saved_at"] = datetime.now().isoformat()
    new_market_count = _count_markets(new_data)

    if existing_data is not None:
        try:
            existing_market_count = _count_markets(existing_data)

            # Per-game merge: for each game, pick the version with more markets
            if existing_market_count > 0:
                merged = _merge_predictions(existing_data, new_data)
                merged_market_count = _count_markets(merged)

                if merged_market_count > new_market_count:
                    logger.info(
                        f"🔀 Merged predictions for {analysis.date}: "
                        f"existing had {existing_market_count} markets, "
                        f"new has {new_market_count}, merged = {merged_market_count}"
                    )
                    merged["saved_at"] = datetime.now().isoformat()
                    filepath.write_text(json.dumps(merged, indent=2), encoding="utf-8")
                    return filepath

        except Exception:
            pass  # Corrupted file — overwrite it

    filepath.write_text(json.dumps(new_data, indent=2), encoding="utf-8")
    logger.info(
        f"💾 Saved predictions for {analysis.date} → {filepath.name} "
        f"({new_data['games_count']} games, {new_market_count} markets)"
    )
    return filepath


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


def load_predictions(game_date: date) -> DailyAnalysis | None:
    """Load saved predictions for a specific date, or None if not found."""
    filepath = PREDICTIONS_DIR / f"{game_date.isoformat()}.json"
    if not filepath.exists():
        return None

    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
        # Remove our extra field before parsing
        data.pop("saved_at", None)
        return DailyAnalysis.model_validate(data)
    except Exception as e:
        logger.warning(f"Failed to load predictions from {filepath}: {e}")
        return None


def list_saved_dates() -> list[dict]:
    """List all dates that have saved predictions.

    Returns list of {date, games_count, saved_at, file_size_kb} sorted by date desc.
    """
    _ensure_dir()
    results = []
    for filepath in sorted(PREDICTIONS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            results.append({
                "date": filepath.stem,  # e.g. "2026-04-08"
                "games_count": data.get("games_count", 0),
                "saved_at": data.get("saved_at"),
                "file_size_kb": round(filepath.stat().st_size / 1024, 1),
            })
        except Exception:
            continue
    return results
