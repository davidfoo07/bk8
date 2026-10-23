"""Model vs market evaluation — are CourtEdge's edges real?

Scores every graded History game twice for the same event (home win, home
covers, over): once with the model probability and once with the Polymarket
price saved alongside it (both locked at tip-off).  A model that finds real
edges must beat the market on Brier score / log loss; a model that merely
disagrees with the market will lose to it.

Also grades every BUY / STRONG BUY verdict as a flat $1 bet at the saved price.

Closing-line value is not measurable from what is stored (see CLV_NOTE).
"""

from __future__ import annotations

import asyncio
import math
from datetime import date
from typing import TYPE_CHECKING

from loguru import logger
from pydantic import BaseModel

from app.services.pipeline import fetch_scores
from app.services.prediction_store import list_saved_dates, load_predictions

if TYPE_CHECKING:
    from app.schemas.game import DailyAnalysis

MARKET_TYPES = ("moneyline", "spread", "total")
BET_VERDICTS = ("BUY", "STRONG BUY")
# Below this many graded games nothing here says anything about model quality.
MIN_GAMES = 100
PROB_CLIP = 0.001  # keeps log loss finite for 0/1 forecasts


class MarketCalibration(BaseModel):
    """Model vs Polymarket probability quality for one market type."""
    market_type: str
    n: int
    model_brier: float | None = None
    market_brier: float | None = None
    model_log_loss: float | None = None
    market_log_loss: float | None = None
    # model − market: negative means the model forecast better than the market
    brier_diff: float | None = None
    brier_diff_se: float | None = None
    avg_abs_disagreement: float | None = None  # mean |model − market|
    conclusion: str = "too_few"  # too_few | model_better | market_better | no_difference


class BetRecord(BaseModel):
    """Flat $1 results for BUY / STRONG BUY verdicts."""
    market_type: str  # moneyline | spread | total | all
    n: int
    wins: int = 0
    hit_rate: float | None = None
    avg_price: float | None = None  # break-even hit rate
    pnl: float = 0.0
    roi: float | None = None  # pnl per $1 staked
    roi_se: float | None = None


class ClvStatus(BaseModel):
    supported: bool
    reason: str
    needed: str


class ModelEvaluation(BaseModel):
    dates: list[str]
    graded_games: int
    min_games: int = MIN_GAMES
    conclusive: bool
    calibration: list[MarketCalibration]
    bets: list[BetRecord]
    clv: ClvStatus


CLV_NOTE = ClvStatus(
    supported=False,
    reason=(
        "No price history is stored. daily_predictions keeps one locked pre-game "
        "version per game, and market_snapshots keeps one row per game/market — the "
        "highest-edge snapshot, selected on the edge itself — so there is no "
        "first-vs-last-pre-tip pair to compare, and comparing the max-edge snapshot "
        "to the locked price would show fake CLV from regression to the mean."
    ),
    needed=(
        "An append-only market price log written on every pipeline run: game_id, "
        "market_type, line, Polymarket home/yes price, model probability, fetched_at. "
        "CLV = closing price − opening price on the model's side (same line only)."
    ),
)


def _yes_outcome(market_type: str, line: float | None, home: int, away: int) -> bool | None:
    """Did the home/yes/over side win?  None for pushes or missing lines."""
    if market_type == "moneyline":
        return home > away
    if line is None:
        return None
    value = (home - away + line) if market_type == "spread" else (home + away - line)
    return None if value == 0 else value > 0


def _clip(p: float) -> float:
    return min(1 - PROB_CLIP, max(PROB_CLIP, p))


def _log_loss(p: float, y: int) -> float:
    p = _clip(p)
    return -math.log(p if y else 1 - p)


def _mean_se(values: list[float]) -> tuple[float, float | None]:
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, None
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(var / n)


def _calibration(market_type: str, rows: list[tuple[float, float, int]]) -> MarketCalibration:
    """rows: (model prob, market price, outcome) for the yes side."""
    n = len(rows)
    if n == 0:
        return MarketCalibration(market_type=market_type, n=0)
    model_b = [(p - y) ** 2 for p, _, y in rows]
    market_b = [(q - y) ** 2 for _, q, y in rows]
    diff, se = _mean_se([m - k for m, k in zip(model_b, market_b, strict=True)])
    if n < MIN_GAMES or se is None:
        conclusion = "too_few"
    elif diff + 2 * se < 0:
        conclusion = "model_better"
    elif diff - 2 * se > 0:
        conclusion = "market_better"
    else:
        conclusion = "no_difference"
    return MarketCalibration(
        market_type=market_type,
        n=n,
        model_brier=round(sum(model_b) / n, 4),
        market_brier=round(sum(market_b) / n, 4),
        model_log_loss=round(sum(_log_loss(p, y) for p, _, y in rows) / n, 4),
        market_log_loss=round(sum(_log_loss(q, y) for _, q, y in rows) / n, 4),
        brier_diff=round(diff, 4),
        brier_diff_se=round(se, 4) if se is not None else None,
        avg_abs_disagreement=round(sum(abs(p - q) for p, q, _ in rows) / n, 4),
        conclusion=conclusion,
    )


def _bet_record(market_type: str, bets: list[tuple[float, bool]]) -> BetRecord:
    """bets: (entry price, won) for flat $1 stakes."""
    n = len(bets)
    if n == 0:
        return BetRecord(market_type=market_type, n=0)
    pnls = [(1 - price) / price if won else -1.0 for price, won in bets]
    roi, se = _mean_se(pnls)
    wins = sum(won for _, won in bets)
    return BetRecord(
        market_type=market_type,
        n=n,
        wins=wins,
        hit_rate=round(wins / n, 4),
        avg_price=round(sum(price for price, _ in bets) / n, 4),
        pnl=round(sum(pnls), 2),
        roi=round(roi, 4),
        roi_se=round(se, 4) if se is not None else None,
    )


def evaluate(days: list[tuple[DailyAnalysis, dict[str, dict]]]) -> ModelEvaluation:
    """Score saved History against final scores.

    days: (saved analysis, fetch_scores() result for its date).  Only FINAL
    games with a live (non-settled) saved market count.
    """
    calib: dict[str, list[tuple[float, float, int]]] = {m: [] for m in MARKET_TYPES}
    bets: dict[str, list[tuple[float, bool]]] = {m: [] for m in MARKET_TYPES}
    graded_games = 0
    dates: list[str] = []

    for analysis, scores in days:
        day_graded = 0
        for game in analysis.games:
            actual = scores.get(f"{game.away.team}_{game.home.team}")
            if not actual or actual.get("status") != 3:
                continue
            counted = False
            for mtype, mkt in game.markets.items():
                price = mkt.polymarket_home_yes
                if mtype not in calib or mkt.edge.verdict == "SETTLED" or price is None:
                    continue
                if not 0 < price < 1:
                    continue
                outcome = _yes_outcome(mtype, mkt.line, actual["home_score"], actual["away_score"])
                if outcome is None:
                    continue
                counted = True
                calib[mtype].append((mkt.model_probability, price, int(outcome)))
                if mkt.edge.verdict in BET_VERDICTS:
                    side_yes = mkt.edge.best_side in (mkt.home_label, "YES", "Over")
                    entry = price if side_yes else 1 - price
                    bets[mtype].append((entry, outcome == side_yes))
            if counted:
                day_graded += 1
        if day_graded:
            graded_games += day_graded
            dates.append(analysis.date.isoformat())

    all_bets = [b for m in MARKET_TYPES for b in bets[m]]
    return ModelEvaluation(
        dates=sorted(dates),
        graded_games=graded_games,
        conclusive=graded_games >= MIN_GAMES,
        calibration=[_calibration(m, calib[m]) for m in MARKET_TYPES],
        bets=[_bet_record(m, bets[m]) for m in MARKET_TYPES] + [_bet_record("all", all_bets)],
        clv=CLV_NOTE,
    )


async def build_evaluation(today: date | None = None) -> ModelEvaluation:
    """Evaluate every saved History date up to today against final scores."""
    today = today or date.today()
    saved = [date.fromisoformat(d["date"]) for d in await list_saved_dates()]
    saved = [d for d in saved if d <= today]

    limit = asyncio.Semaphore(8)

    async def load(d: date) -> tuple[DailyAnalysis, dict[str, dict]] | None:
        async with limit:
            analysis = await load_predictions(d)
            if analysis is None:
                return None
            try:
                scores = await fetch_scores(d)
            except Exception as e:
                logger.warning(f"Evaluation: no scores for {d}: {e}")
                return None
        return analysis, scores

    loaded = await asyncio.gather(*(load(d) for d in saved))
    return evaluate([day for day in loaded if day is not None])
