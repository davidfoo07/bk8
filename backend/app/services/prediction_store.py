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


def save_predictions(analysis: DailyAnalysis) -> Path:
    """Save a DailyAnalysis to a dated JSON file.

    Protection logic:
      - If no existing file → save unconditionally.
      - If existing file has MORE markets than the new data → skip the overwrite.
        This prevents post-game pipeline runs (where Polymarket delisted settled
        markets) from clobbering the pre-game snapshot that had full edge data.
      - If equal or fewer markets → overwrite (new data is richer or same).
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

            if existing_market_count > new_market_count:
                logger.info(
                    f"🛡️ Skipping save for {analysis.date}: existing file has "
                    f"{existing_market_count} markets vs new {new_market_count} "
                    f"(protecting pre-game snapshot)"
                )
                return filepath
        except Exception:
            pass  # Corrupted file — overwrite it

    filepath.write_text(json.dumps(new_data, indent=2), encoding="utf-8")
    logger.info(
        f"💾 Saved predictions for {analysis.date} → {filepath.name} "
        f"({analysis.games_count} games, {new_market_count} markets)"
    )
    return filepath


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
