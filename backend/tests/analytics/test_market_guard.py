"""Market-disagreement sanity guard (edge_calculator + _process_single_game)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.analytics.edge_calculator import calculate_edge, guard_market_disagreement
from app.schemas.market import EdgeResult, MarketEdge
from app.services import pipeline


def _market(model_p: float, price: float) -> MarketEdge:
    return MarketEdge(
        market_type="moneyline", polymarket_home_yes=price,
        polymarket_home_no=round(1 - price, 3), model_probability=model_p,
        edge=calculate_edge(model_p, price),
    )


class TestGuardMarketDisagreement:
    def test_large_gap_caps_at_lean_and_sizes_from_blend(self) -> None:
        mkt = _market(0.725, 0.40)  # MIA @ CHA: +32.5 pts
        assert mkt.edge.verdict == "STRONG BUY"
        guarded, gap = guard_market_disagreement(mkt, threshold=0.15, model_weight=0.5)

        assert gap == pytest.approx(0.325)
        assert guarded.edge.verdict == "LEAN"
        # Raw model numbers stay visible.
        assert guarded.model_probability == 0.725
        assert guarded.edge.best_edge == mkt.edge.best_edge
        assert guarded.edge.best_side == mkt.edge.best_side
        # Kelly from the 50/50 blend (0.5625), not the raw 0.725.
        assert guarded.blended_probability == pytest.approx(0.5625)
        assert guarded.edge.kelly_fraction == calculate_edge(0.5625, 0.40).kelly_fraction
        assert guarded.edge.kelly_fraction < mkt.edge.kelly_fraction

    def test_gap_on_no_side_also_trips(self) -> None:
        guarded, gap = guard_market_disagreement(
            _market(0.059, 0.275), threshold=0.15, model_weight=0.5,  # SAS @ DAL
        )
        assert gap == pytest.approx(0.216)
        assert guarded.edge.verdict == "LEAN"

    def test_small_gap_keeps_verdict_but_reports_blend(self) -> None:
        mkt = _market(0.70, 0.57)  # 13 pts: STRONG BUY stays
        guarded, gap = guard_market_disagreement(mkt, threshold=0.15, model_weight=0.5)
        assert gap is None
        assert guarded.edge == mkt.edge
        assert guarded.blended_probability == pytest.approx(0.635)

    def test_exact_threshold_does_not_trip(self) -> None:
        _, gap = guard_market_disagreement(_market(0.65, 0.50), threshold=0.15, model_weight=0.5)
        assert gap is None

    def test_threshold_is_configurable(self) -> None:
        _, gap = guard_market_disagreement(_market(0.62, 0.50), threshold=0.10, model_weight=0.5)
        assert gap == pytest.approx(0.12)

    def test_lower_verdicts_unchanged(self) -> None:
        mkt = _market(0.70, 0.50)
        mkt = mkt.model_copy(update={"edge": mkt.edge.model_copy(update={"verdict": "NO EDGE"})})
        guarded, gap = guard_market_disagreement(mkt, threshold=0.15, model_weight=0.5)
        assert gap is not None
        assert guarded.edge.verdict == "NO EDGE"

    def test_settled_market_passes_through(self) -> None:
        mkt = MarketEdge(
            market_type="moneyline", polymarket_home_yes=0.995, model_probability=0.6,
            edge=EdgeResult(yes_edge=0.0, no_edge=0.0, yes_ev=0.0, no_ev=0.0,
                            best_side="SETTLED", best_edge=0.0, verdict="SETTLED"),
        )
        guarded, gap = guard_market_disagreement(mkt, threshold=0.15, model_weight=0.5)
        assert gap is None
        assert guarded is mkt


class TestPipelineGuard:
    async def _analyse(
        self, monkeypatch: pytest.MonkeyPatch, ml_price: float, game_status: int = 1,
    ) -> Any:
        def fake_prices(away: str, home: str, game_date: date, event: Any) -> dict[str, Any]:
            return {"moneyline_home_yes": ml_price}

        monkeypatch.setattr(pipeline, "_find_polymarket_prices", fake_prices)
        home = {"ortg": 120.0, "drtg": 108.0, "nrtg": 12.0, "pace": 100.0,
                "prior_source": "roster", "roster_turnover": 0.1, "stale_prior": False}
        away = {"ortg": 110.0, "drtg": 116.0, "nrtg": -6.0, "pace": 100.0,
                "prior_source": "roster", "roster_turnover": 0.1, "stale_prior": False}
        return await pipeline._process_single_game(
            game_raw={"home_team": "PHI", "away_team": "BOS", "game_id": "g1",
                      "game_status": game_status},
            game_date=date(2026, 10, 24),
            ratings_data={"PHI": home, "BOS": away},
            standings_data={}, injuries_data={}, player_metrics={},
            polymarket_event=None, warnings=[],
        )

    async def test_disagreement_caps_and_warns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        analysis = await self._analyse(monkeypatch, ml_price=0.40)
        ml = analysis.markets["moneyline"]
        assert ml.model_probability > 0.9  # raw model kept
        assert ml.edge.best_edge > 0.5
        assert ml.edge.verdict == "LEAN"
        assert ml.blended_probability == pytest.approx((ml.model_probability + 0.40) / 2, abs=1e-3)
        assert any(
            w.startswith("Model disagrees with market by moneyline")
            and "check inputs" in w
            for w in analysis.data_quality.warnings
        )
        assert pipeline._extract_top_edges([analysis]) == []

    async def test_agreement_keeps_verdict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        analysis = await self._analyse(monkeypatch, ml_price=0.85)
        ml = analysis.markets["moneyline"]
        assert abs(ml.model_probability - 0.85) <= 0.15
        assert ml.edge.verdict == calculate_edge(ml.model_probability, 0.85).verdict
        assert not any("disagrees" in w for w in analysis.data_quality.warnings)

    async def test_corrected_injury_team_warns_on_that_game(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def fake_prices(away: str, home: str, game_date: date, event: Any) -> dict[str, Any]:
            return {}

        monkeypatch.setattr(pipeline, "_find_polymarket_prices", fake_prices)
        ratings = {"ortg": 115.0, "drtg": 115.0, "nrtg": 0.0, "pace": 100.0}
        analysis = await pipeline._process_single_game(
            game_raw={"home_team": "LAL", "away_team": "LAC", "game_id": "g1", "game_status": 1},
            game_date=date(2026, 10, 23),
            ratings_data={"LAL": ratings, "LAC": ratings},
            standings_data={},
            injuries_data={"LAC": [{"player_name": "Brandon Ingram", "status": "OUT",
                                    "team": "LAC", "team_corrected_from": "TOR"}]},
            player_metrics={}, polymarket_event=None, warnings=[],
        )
        assert any("Brandon Ingram (TOR→LAC)" in w for w in analysis.data_quality.warnings)
