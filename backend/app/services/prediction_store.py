"""Prediction persistence — save/load daily analyses as JSON files.

Simple file-based storage: one JSON per date under backend/data/predictions/.
No DB dependency, no ORM, just Pydantic serialization.

IMPORTANT: Pre-game predictions (with full Polymarket edges) are protected.
Later pipeline runs (post-game, when Polymarket has delisted markets) will NOT
overwrite a richer pre-game snapshot.  This ensures the simulation tab always
has the full set of BUY/STRONG BUY bets for grading.
"""

import json
from datetime import date, datetime
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


def save_predictions(analysis: DailyAnalysis) -> Path:
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

    new_data = json.loads(analysis.model_dump_json())
    new_data["saved_at"] = datetime.now().isoformat()
    new_market_count = _count_markets(new_data)

    # Check existing file
    if filepath.exists():
        try:
            existing_data = json.loads(filepath.read_text(encoding="utf-8"))
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
        f"({analysis.games_count} games, {new_market_count} markets)"
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
