"""Results comparison API — matches predictions against actual NBA scores."""

from datetime import date

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from app.connectors.nba_api import NBAApiConnector
from app.services.prediction_store import load_predictions, list_saved_dates

router = APIRouter(prefix="/results", tags=["Results"])

NBA_TEAM_ID_TO_ABBR: dict[int, str] = {
    1610612737: "ATL", 1610612738: "BOS", 1610612751: "BKN", 1610612766: "CHA",
    1610612741: "CHI", 1610612739: "CLE", 1610612742: "DAL", 1610612743: "DEN",
    1610612765: "DET", 1610612744: "GSW", 1610612745: "HOU", 1610612754: "IND",
    1610612746: "LAC", 1610612747: "LAL", 1610612763: "MEM", 1610612748: "MIA",
    1610612749: "MIL", 1610612750: "MIN", 1610612740: "NOP", 1610612752: "NYK",
    1610612760: "OKC", 1610612753: "ORL", 1610612755: "PHI", 1610612756: "PHX",
    1610612757: "POR", 1610612758: "SAC", 1610612759: "SAS", 1610612761: "TOR",
    1610612762: "UTA", 1610612764: "WAS",
}


class GameResult(BaseModel):
    game_id: str
    away_team: str
    home_team: str
    # Predictions
    model_home_win_prob: float
    model_spread: float
    model_total: float
    favored_team: str
    favored_prob: float
    # Polymarket lines (from saved predictions, null if not available)
    poly_spread_line: float | None = None  # e.g. -3.5 (home perspective)
    poly_spread_team: str | None = None    # e.g. "SAS" (who the line is for)
    poly_total_line: float | None = None   # e.g. 229.5
    # Actual results (null if game not finished)
    home_score: int | None = None
    away_score: int | None = None
    actual_total: int | None = None
    actual_margin: int | None = None  # home - away
    winner: str | None = None
    # Grading
    ml_correct: bool | None = None
    spread_cover_correct: bool | None = None  # did the model's spread pick cover?
    total_ou_correct: bool | None = None      # did the model's O/U pick hit?
    spread_error: float | None = None
    total_error: float | None = None
    status: str = "SCHEDULED"


class DailyResults(BaseModel):
    date: str
    games: list[GameResult]
    # Aggregate stats
    ml_record: str
    ml_accuracy: float | None = None
    spread_record: str = "0/0"
    spread_accuracy: float | None = None
    ou_record: str = "0/0"
    ou_accuracy: float | None = None
    avg_total_error: float | None = None
    avg_spread_error: float | None = None
    total_bias: float | None = None


@router.get("/{game_date}", response_model=DailyResults)
async def get_results_for_date(game_date: str) -> DailyResults:
    """Compare saved predictions for a date against actual NBA scores."""
    try:
        parsed_date = date.fromisoformat(game_date)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {game_date}")

    analysis = load_predictions(parsed_date)
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"No saved predictions for {game_date}")

    # Fetch actual scores from NBA API
    nba = NBAApiConnector()
    actuals: dict[str, dict] = {}
    try:
        raw_games = await nba.get_todays_games(parsed_date)
        for g in raw_games:
            home_team = g.get("homeTeam", {})
            away_team = g.get("awayTeam", {})
            ht_id = home_team.get("teamId", 0)
            at_id = away_team.get("teamId", 0)
            ht = NBA_TEAM_ID_TO_ABBR.get(ht_id, home_team.get("teamTricode", "???"))
            at = NBA_TEAM_ID_TO_ABBR.get(at_id, away_team.get("teamTricode", "???"))
            hs = int(home_team.get("score", 0) or 0)
            as_ = int(away_team.get("score", 0) or 0)
            status = g.get("gameStatus", 1)
            key = f"{at}_{ht}"
            actuals[key] = {"home_score": hs, "away_score": as_, "status": status}
    except Exception as e:
        logger.warning(f"Failed to fetch actual scores for {game_date}: {e}")
    finally:
        await nba.close()

    # Build per-game comparisons
    results: list[GameResult] = []
    ml_correct_count = 0
    ml_total_count = 0
    spread_correct_count = 0
    spread_graded_count = 0
    ou_correct_count = 0
    ou_graded_count = 0
    total_errors: list[float] = []
    spread_errors: list[float] = []
    total_biases: list[float] = []

    for game in analysis.games:
        away = game.away.team
        home = game.home.team
        model = game.model

        # Determine favored team
        if model.home_win_prob >= 0.5:
            favored, favored_prob = home, model.home_win_prob
        else:
            favored, favored_prob = away, 1 - model.home_win_prob

        # Extract Polymarket lines from saved markets
        poly_spread_line: float | None = None
        poly_spread_team: str | None = None
        poly_total_line: float | None = None

        spread_mkt = game.markets.get("spread")
        if spread_mkt and spread_mkt.line is not None:
            poly_spread_line = spread_mkt.line
            poly_spread_team = home  # line is always from home perspective

        total_mkt = game.markets.get("total")
        if total_mkt and total_mkt.line is not None:
            poly_total_line = total_mkt.line

        # Look up actuals
        key = f"{away}_{home}"
        actual = actuals.get(key)

        gr = GameResult(
            game_id=game.game_id,
            away_team=away,
            home_team=home,
            model_home_win_prob=model.home_win_prob,
            model_spread=model.projected_spread,
            model_total=model.projected_total,
            favored_team=favored,
            favored_prob=favored_prob,
            poly_spread_line=poly_spread_line,
            poly_spread_team=poly_spread_team,
            poly_total_line=poly_total_line,
        )

        if actual and actual["status"] == 3:
            hs = actual["home_score"]
            as_ = actual["away_score"]
            gr.home_score = hs
            gr.away_score = as_
            gr.actual_total = hs + as_
            gr.actual_margin = hs - as_
            gr.winner = home if hs > as_ else away
            gr.status = "FINAL"

            # Grade moneyline
            model_picked_home = model.home_win_prob >= 0.5
            home_won = hs > as_
            gr.ml_correct = (model_picked_home and home_won) or (not model_picked_home and not home_won)
            ml_correct_count += int(gr.ml_correct)
            ml_total_count += 1

            # Grade spread cover (against Polymarket line)
            if poly_spread_line is not None:
                actual_margin = hs - as_
                # spread_line is from home perspective: -3.5 means home favored by 3.5
                # Home covers if actual_margin > abs(spread_line) when favored
                # More precisely: home covers if actual_margin + spread_line > 0
                home_covers = (actual_margin + poly_spread_line) > 0
                # Model's spread pick: if model spread < poly line, model says home covers
                # e.g. model says -5.0 (home by 5), poly line is -3.5 → model says home covers
                model_says_home_covers = model.projected_spread <= poly_spread_line
                gr.spread_cover_correct = (model_says_home_covers == home_covers)
                spread_correct_count += int(gr.spread_cover_correct)
                spread_graded_count += 1

            # Grade O/U (against Polymarket line)
            if poly_total_line is not None:
                actual_total = hs + as_
                went_over = actual_total > poly_total_line
                # Model says over if projected_total > poly_total_line
                model_says_over = model.projected_total > poly_total_line
                gr.total_ou_correct = (model_says_over == went_over)
                ou_correct_count += int(gr.total_ou_correct)
                ou_graded_count += 1

            # Spread error
            projected_margin = -model.projected_spread
            gr.spread_error = round(abs((hs - as_) - projected_margin), 1)
            spread_errors.append(gr.spread_error)

            # Total error
            gr.total_error = round((hs + as_) - model.projected_total, 1)
            total_errors.append(abs(gr.total_error))
            total_biases.append(gr.total_error)

        elif actual and actual["status"] == 2:
            gr.home_score = actual["home_score"]
            gr.away_score = actual["away_score"]
            gr.status = "LIVE"

        results.append(gr)

    # Aggregates
    n = ml_total_count
    ml_record = f"{ml_correct_count}/{n}" if n > 0 else "0/0"
    ml_accuracy = ml_correct_count / n if n > 0 else None

    spread_record = f"{spread_correct_count}/{spread_graded_count}" if spread_graded_count > 0 else "0/0"
    spread_accuracy = spread_correct_count / spread_graded_count if spread_graded_count > 0 else None

    ou_record = f"{ou_correct_count}/{ou_graded_count}" if ou_graded_count > 0 else "0/0"
    ou_accuracy = ou_correct_count / ou_graded_count if ou_graded_count > 0 else None

    avg_total_err = round(sum(total_errors) / len(total_errors), 1) if total_errors else None
    avg_spread_err = round(sum(spread_errors) / len(spread_errors), 1) if spread_errors else None
    total_bias = round(sum(total_biases) / len(total_biases), 1) if total_biases else None

    return DailyResults(
        date=game_date,
        games=results,
        ml_record=ml_record,
        ml_accuracy=ml_accuracy,
        spread_record=spread_record,
        spread_accuracy=spread_accuracy,
        ou_record=ou_record,
        ou_accuracy=ou_accuracy,
        avg_total_error=avg_total_err,
        avg_spread_error=avg_spread_err,
        total_bias=total_bias,
    )


@router.get("/", response_model=list[dict])
async def list_available_results() -> list[dict]:
    """List all dates that have saved predictions (suitable for results comparison)."""
    return list_saved_dates()
