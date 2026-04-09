"""System simulation API — virtual P&L if you followed every model recommendation."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from app.connectors.nba_api import NBAApiConnector
from app.services.prediction_store import list_saved_dates, load_predictions

router = APIRouter(prefix="/simulation", tags=["Simulation"])

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

KELLY_BANKROLL = 100.0  # $100 virtual bankroll for Kelly-sized bets


# ─── Pydantic Schemas ──────────────────────────────────────────────

class SimBet(BaseModel):
    """A single virtual bet from the simulation."""
    game: str
    market_type: str
    selection: str
    side: str
    verdict: str
    entry_price: float
    model_prob: float
    edge: float
    kelly_fraction: float
    flat_result: str | None = None
    flat_pnl: float = 0.0
    kelly_amount: float = 0.0
    kelly_result: str | None = None
    kelly_pnl: float = 0.0


class DailySimulation(BaseModel):
    """Full simulation results for a single date."""
    date: str
    total_bets: int
    flat_wins: int
    flat_losses: int
    flat_record: str
    flat_pnl: float
    flat_roi: float
    kelly_wins: int
    kelly_losses: int
    kelly_pnl: float
    kelly_roi: float
    bets: list[SimBet]


# ─── Grading Helpers ───────────────────────────────────────────────

def _grade_yes_outcome(
    market_type: str,
    line: float | None,
    home_score: int,
    away_score: int,
) -> bool | None:
    """Determine if YES (home-perspective) outcome occurred.

    YES mapping:
      moneyline → home wins
      spread    → home covers (actual_margin + home_line > 0)
      total     → Over (actual_total > line)
    """
    actual_margin = home_score - away_score
    actual_total = home_score + away_score

    if market_type == "moneyline":
        return actual_margin > 0

    if market_type == "spread":
        if line is None:
            return None
        return (actual_margin + line) > 0

    if market_type == "total":
        if line is None:
            return None
        return actual_total > line

    return None


def _calc_pnl(won: bool, amount: float, price: float) -> float:
    """Calculate P&L for a bet. WIN pays (1-price)/price * amount, LOSS pays -amount."""
    if won:
        return round(amount * (1 - price) / price, 2) if price > 0 else 0.0
    return round(-amount, 2)


def _build_selection_label(
    market_type: str,
    away_team: str,
    home_team: str,
    side: str,
    best_side_name: str,
    line: float | None,
) -> str:
    """Build human-readable selection text (e.g. 'DEN covers -3.5')."""
    if market_type == "moneyline":
        team = home_team if side == "YES" else away_team
        return f"{team} ML"

    if market_type == "spread":
        if line is not None:
            # line is home perspective; if YES (home covers), show home + home_line
            if side == "YES":
                home_line = line
                sign = "+" if home_line > 0 else ""
                return f"{home_team} covers {sign}{home_line}"
            else:
                away_line = -line
                sign = "+" if away_line > 0 else ""
                return f"{away_team} covers {sign}{away_line}"
        return f"{best_side_name} covers"

    if market_type == "total":
        if line is not None:
            direction = "Over" if side == "YES" else "Under"
            return f"{direction} {line}"
        return best_side_name

    return best_side_name


# ─── Endpoints ─────────────────────────────────────────────────────

@router.get("/", response_model=list[dict])
async def list_simulation_dates() -> list[dict]:
    """List all dates that have saved predictions (available for simulation)."""
    return list_saved_dates()


@router.get("/{game_date}", response_model=DailySimulation)
async def get_simulation(game_date: str) -> DailySimulation:
    """Run a full simulation for a given date: find all BUY/STRONG BUY edges,
    place virtual bets, grade against actual NBA scores, return summary + detail."""
    try:
        parsed_date = date.fromisoformat(game_date)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {game_date}")

    analysis = load_predictions(parsed_date)
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"No saved predictions for {game_date}")

    # ── Fetch actual NBA scores ────────────────────────────────────
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
            if status == 3:  # Only grade FINAL games
                actuals[f"{at}_{ht}"] = {"home_score": hs, "away_score": as_}
    except Exception as e:
        logger.warning(f"Failed to fetch scores for simulation {game_date}: {e}")
    finally:
        await nba.close()

    # ── Build virtual bets from every BUY/STRONG BUY edge ─────────
    sim_bets: list[SimBet] = []

    for game in analysis.games:
        away = game.away.team
        home = game.home.team
        game_label = f"{away} @ {home}"
        key = f"{away}_{home}"
        actual = actuals.get(key)

        for mkt_type, mkt in game.markets.items():
            edge = mkt.edge
            verdict = edge.verdict

            # Only simulate BUY and STRONG BUY verdicts
            if verdict not in ("BUY", "STRONG BUY"):
                continue

            # Determine side: map best_side (team nickname or Over/Under) to YES/NO
            best_side_name = edge.best_side
            home_label = (mkt.home_label or "").lower()
            away_label = (mkt.away_label or "").lower()

            if best_side_name.lower() == home_label:
                side = "YES"
            elif best_side_name.lower() in ("over",):
                side = "YES"
            elif best_side_name.lower() == away_label:
                side = "NO"
            elif best_side_name.lower() in ("under",):
                side = "NO"
            elif best_side_name.upper() == "YES":
                side = "YES"
            elif best_side_name.upper() == "NO":
                side = "NO"
            else:
                # Fallback: check if best_side matches home/away team abbreviation
                if best_side_name.upper() == home:
                    side = "YES"
                else:
                    side = "NO"

            # Entry price based on side
            poly_home_yes = mkt.polymarket_home_yes or 0.5
            if side == "YES":
                entry_price = poly_home_yes
            else:
                entry_price = round(1 - poly_home_yes, 4)

            # Avoid degenerate prices
            entry_price = max(0.01, min(0.99, entry_price))

            # Kelly-sized bet
            kelly_frac = edge.kelly_fraction
            kelly_amount = round(kelly_frac * KELLY_BANKROLL, 2)

            # Build human-readable selection
            selection = _build_selection_label(
                mkt_type, away, home, side, best_side_name, mkt.line,
            )

            # ── Grade the bet ──────────────────────────────────────
            flat_result: str | None = None
            flat_pnl = 0.0
            kelly_result: str | None = None
            kelly_pnl = 0.0

            if actual:
                hs = actual["home_score"]
                as_ = actual["away_score"]

                yes_outcome = _grade_yes_outcome(mkt_type, mkt.line, hs, as_)

                if yes_outcome is not None:
                    won = yes_outcome if side == "YES" else not yes_outcome

                    flat_result = "WIN" if won else "LOSS"
                    flat_pnl = _calc_pnl(won, 1.0, entry_price)

                    kelly_result = "WIN" if won else "LOSS"
                    kelly_pnl = _calc_pnl(won, kelly_amount, entry_price)

            sim_bets.append(SimBet(
                game=game_label,
                market_type=mkt_type,
                selection=selection,
                side=side,
                verdict=verdict,
                entry_price=entry_price,
                model_prob=mkt.model_probability,
                edge=edge.best_edge,
                kelly_fraction=kelly_frac,
                flat_result=flat_result,
                flat_pnl=flat_pnl,
                kelly_amount=kelly_amount,
                kelly_result=kelly_result,
                kelly_pnl=kelly_pnl,
            ))

    # ── Aggregate stats ────────────────────────────────────────────
    total_bets = len(sim_bets)
    flat_wins = sum(1 for b in sim_bets if b.flat_result == "WIN")
    flat_losses = sum(1 for b in sim_bets if b.flat_result == "LOSS")
    flat_pnl_total = round(sum(b.flat_pnl for b in sim_bets), 2)
    flat_wagered = sum(1.0 for b in sim_bets if b.flat_result is not None)
    flat_roi = round((flat_pnl_total / flat_wagered * 100) if flat_wagered > 0 else 0.0, 1)

    kelly_wins = sum(1 for b in sim_bets if b.kelly_result == "WIN")
    kelly_losses = sum(1 for b in sim_bets if b.kelly_result == "LOSS")
    kelly_pnl_total = round(sum(b.kelly_pnl for b in sim_bets), 2)
    kelly_wagered = round(sum(b.kelly_amount for b in sim_bets if b.kelly_result is not None), 2)
    kelly_roi = round((kelly_pnl_total / kelly_wagered * 100) if kelly_wagered > 0 else 0.0, 1)

    graded = flat_wins + flat_losses
    flat_record = f"{flat_wins}/{graded}" if graded > 0 else f"0/{total_bets}"

    logger.info(
        f"Simulation {game_date}: {total_bets} bets, "
        f"flat {flat_wins}W-{flat_losses}L PnL=${flat_pnl_total:+.2f}, "
        f"kelly PnL=${kelly_pnl_total:+.2f}"
    )

    return DailySimulation(
        date=game_date,
        total_bets=total_bets,
        flat_wins=flat_wins,
        flat_losses=flat_losses,
        flat_record=flat_record,
        flat_pnl=flat_pnl_total,
        flat_roi=flat_roi,
        kelly_wins=kelly_wins,
        kelly_losses=kelly_losses,
        kelly_pnl=kelly_pnl_total,
        kelly_roi=kelly_roi,
        bets=sim_bets,
    )
