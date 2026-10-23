"""Tests for model vs market evaluation over synthetic History rows."""

import math
from datetime import UTC, date, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.database import async_session_factory
from app.models.tables import DailyPrediction
from app.schemas.game import DailyAnalysis
from app.services import evaluation
from app.services.evaluation import MIN_GAMES, _yes_outcome, evaluate

DAY = date(2026, 10, 22)


def _market(mtype: str, model: float, price: float, *, line: float | None = None,
            verdict: str = "HOLD", best_side: str = "YES") -> dict:
    home_label, away_label = ("Over", "Under") if mtype == "total" else ("Home", "Away")
    if best_side == "YES":
        best_side = home_label
    elif best_side == "NO":
        best_side = away_label
    return {
        "market_type": mtype,
        "line": line,
        "polymarket_home_yes": price,
        "polymarket_home_no": round(1 - price, 3),
        "home_label": home_label,
        "away_label": away_label,
        "model_probability": model,
        "edge": {
            "yes_edge": 0, "no_edge": 0, "yes_ev": 0, "no_ev": 0,
            "best_side": best_side, "best_edge": abs(model - price), "verdict": verdict,
        },
    }


def _team(abbr: str) -> dict:
    return {
        "team": abbr, "full_name": abbr, "season_ortg": 110, "season_drtg": 110,
        "season_nrtg": 0, "adjusted_ortg": 110, "adjusted_drtg": 110,
        "adjusted_nrtg": 0, "nrtg_delta": 0,
    }


def _game(away: str, home: str, markets: dict[str, dict]) -> dict:
    return {
        "game_id": f"{DAY}_{away}_{home}",
        "home": _team(home),
        "away": _team(away),
        "model": {
            "nrtg_differential": 0, "schedule_adjustment": 0,
            "projected_spread": 0, "projected_total": 220, "home_win_prob": 0.5,
        },
        "markets": markets,
    }


def _day(games: list[dict], day: date = DAY) -> DailyAnalysis:
    return DailyAnalysis.model_validate({"date": day.isoformat(), "games": games})


def _final(home: int, away: int, status: int = 3) -> dict:
    return {"home_score": home, "away_score": away, "status": status}


class TestYesOutcome:
    def test_moneyline(self):
        assert _yes_outcome("moneyline", None, 100, 90) is True
        assert _yes_outcome("moneyline", None, 90, 100) is False

    def test_spread_home_favoured(self):
        assert _yes_outcome("spread", -3.5, 104, 100) is True
        assert _yes_outcome("spread", -3.5, 103, 100) is False

    def test_total(self):
        assert _yes_outcome("total", 220.5, 111, 110) is True
        assert _yes_outcome("total", 220.5, 110, 110) is False

    def test_push_and_missing_line_are_ungraded(self):
        assert _yes_outcome("spread", -3.0, 103, 100) is None
        assert _yes_outcome("total", 220.0, 110, 110) is None
        assert _yes_outcome("spread", None, 103, 100) is None


class TestCalibration:
    def test_brier_and_log_loss_for_model_and_market(self):
        day = _day([_game("AAA", "BBB", {"moneyline": _market("moneyline", 0.8, 0.6)})])
        out = evaluate([(day, {"AAA_BBB": _final(110, 100)})])
        ml = out.calibration[0]
        assert ml.market_type == "moneyline" and ml.n == 1
        assert ml.model_brier == pytest.approx(0.04)
        assert ml.market_brier == pytest.approx(0.16)
        assert ml.model_log_loss == pytest.approx(-math.log(0.8), abs=1e-4)
        assert ml.market_log_loss == pytest.approx(-math.log(0.6), abs=1e-4)
        assert ml.brier_diff == pytest.approx(-0.12)
        assert ml.brier_diff_se is None
        assert ml.conclusion == "too_few"
        assert out.graded_games == 1 and not out.conclusive
        assert out.dates == ["2026-10-22"]

    def test_unfinished_settled_and_pushed_markets_are_skipped(self):
        day = _day([
            _game("AAA", "BBB", {"moneyline": _market("moneyline", 0.7, 0.5)}),  # live
            _game("CCC", "DDD", {
                "moneyline": _market("moneyline", 0.7, 0.99, verdict="SETTLED"),
                "spread": _market("spread", 0.6, 0.5, line=-5.0),  # pushes
            }),
        ])
        scores = {"AAA_BBB": _final(50, 40, status=2), "CCC_DDD": _final(105, 100)}
        out = evaluate([(day, scores)])
        assert out.graded_games == 0
        assert all(c.n == 0 for c in out.calibration)
        assert out.dates == []

    def test_large_sample_overconfident_model_loses_to_market(self):
        # Market is perfectly calibrated at 0.5; the model says 0.8 every time.
        games, scores = [], {}
        for i in range(MIN_GAMES * 2):
            away, home = f"A{i}", f"H{i}"
            games.append(_game(away, home, {"moneyline": _market("moneyline", 0.8, 0.5)}))
            scores[f"{away}_{home}"] = _final(110, 100) if i % 2 else _final(100, 110)
        out = evaluate([(_day(games), scores)])
        ml = out.calibration[0]
        assert out.conclusive
        assert ml.model_brier == pytest.approx(0.34)
        assert ml.market_brier == pytest.approx(0.25)
        assert ml.brier_diff == pytest.approx(0.09)
        assert ml.conclusion == "market_better"
        assert ml.avg_abs_disagreement == pytest.approx(0.3)

    def test_large_sample_identical_forecasts_no_difference(self):
        games, scores = [], {}
        for i in range(MIN_GAMES):
            away, home = f"A{i}", f"H{i}"
            games.append(_game(away, home, {
                "total": _market("total", 0.5 + (i % 3) / 10, 0.5 + (i % 3) / 10, line=220.5),
            }))
            scores[f"{away}_{home}"] = _final(115, 110) if i % 2 else _final(100, 100)
        tot = evaluate([(_day(games), scores)]).calibration[2]
        assert tot.n == MIN_GAMES
        assert tot.brier_diff == 0
        assert tot.conclusion == "no_difference"


class TestBets:
    def test_flat_roi_at_saved_price_for_both_sides(self):
        day = _day([
            # BUY home at 0.40 → wins, +1.5
            _game("AAA", "BBB", {"moneyline": _market("moneyline", 0.6, 0.40, verdict="BUY")}),
            # STRONG BUY Under at 1 − 0.75 = 0.25 → loses, −1
            _game("CCC", "DDD", {
                "total": _market(
                    "total", 0.4, 0.75, line=220.5, verdict="STRONG BUY", best_side="NO",
                ),
                "spread": _market("spread", 0.55, 0.5, line=-2.5, verdict="LEAN"),  # not a bet
            }),
        ])
        scores = {"AAA_BBB": _final(110, 100), "CCC_DDD": _final(115, 110)}
        out = evaluate([(day, scores)])
        by = {b.market_type: b for b in out.bets}
        assert by["moneyline"].n == 1 and by["moneyline"].wins == 1
        assert by["moneyline"].pnl == pytest.approx(1.5)
        assert by["total"].n == 1 and by["total"].wins == 0
        assert by["total"].avg_price == pytest.approx(0.25)
        assert by["spread"].n == 0
        assert by["all"].n == 2
        assert by["all"].pnl == pytest.approx(0.5)
        assert by["all"].roi == pytest.approx(0.25)
        assert by["all"].hit_rate == 0.5
        assert out.graded_games == 2


class TestClv:
    def test_reported_unsupported(self):
        out = evaluate([])
        assert out.clv.supported is False
        assert "append-only" in out.clv.needed


class TestEndpoint:
    async def test_reads_saved_history_and_skips_future_dates(self, monkeypatch):
        buy = _market("moneyline", 0.7, 0.6, verdict="BUY")
        past = _day([_game("AAA", "BBB", {"moneyline": buy})])
        future = _day([_game("CCC", "DDD", {"moneyline": buy})], day=date(2099, 1, 1))
        async with async_session_factory() as session, session.begin():
            for a in (past, future):
                session.add(DailyPrediction(
                    game_date=a.date, data=a.model_dump(mode="json"),
                    games_count=len(a.games), saved_at=datetime.now(UTC),
                ))

        fetched: list[date] = []

        async def fake_scores(d: date) -> dict:
            fetched.append(d)
            return {"AAA_BBB": _final(100, 90)}

        monkeypatch.setattr(evaluation, "fetch_scores", fake_scores)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/results/evaluation")
        assert resp.status_code == 200
        body = resp.json()
        assert fetched == [DAY]
        assert body["graded_games"] == 1
        assert body["conclusive"] is False
        assert body["min_games"] == MIN_GAMES
        assert body["calibration"][0]["n"] == 1
        assert body["bets"][-1] == {**body["bets"][-1], "market_type": "all", "n": 1, "wins": 1}
