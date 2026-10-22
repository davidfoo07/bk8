"""Tests for picking moneyline/spread/total out of a Polymarket game event."""

import json
from datetime import date

import pytest

from app.services.pipeline import _find_polymarket_prices


def _mkt(question: str, outcomes: list[str], prices: list[str], smt: str | None = None) -> dict:
    m = {
        "question": question,
        "outcomes": json.dumps(outcomes),
        "outcomePrices": json.dumps(prices),
    }
    if smt:
        m["sportsMarketType"] = smt
    return m


# Market order mirrors the real 2026-10-22 CLE @ PHI event: the moneyline is
# followed by "Team vs. Team: <prop>" markets that used to overwrite it.
CLE_PHI_MARKETS = [
    _mkt("Cavaliers vs. 76ers", ["Cavaliers", "76ers"], ["0.415", "0.585"], "moneyline"),
    _mkt("Spread: 76ers (-2.5)", ["76ers", "Cavaliers"], ["0.535", "0.465"], "spreads"),
    _mkt("Cavaliers vs. 76ers: O/U 236.5", ["Over", "Under"], ["0.48", "0.52"], "totals"),
    _mkt(
        "Cavaliers vs. 76ers: Team to Score First",
        ["Cavaliers", "76ers"],
        ["0.5", "0.5"],
        "basketball_team_to_score_first",
    ),
    _mkt(
        "Cavaliers vs. 76ers: Odd/Even Score",
        ["Odd", "Even"],
        ["0.5", "0.5"],
        "basketball_odd_even",
    ),
    _mkt(
        "Cavaliers vs. 76ers: 1H Moneyline",
        ["Cavaliers", "76ers"],
        ["0.5", "0.5"],
        "first_half_moneyline",
    ),
]


class TestMoneylineParsing:
    def test_prop_markets_do_not_overwrite_moneyline(self):
        prices = _find_polymarket_prices(
            "CLE", "PHI", date(2026, 10, 22), {"markets": CLE_PHI_MARKETS}
        )
        assert prices["moneyline_home_yes"] == pytest.approx(0.585)
        assert prices["moneyline_home_no"] == pytest.approx(0.415)

    def test_fallback_without_sports_market_type(self):
        """Older events have no sportsMarketType — fall back to question text, skipping props."""
        markets = [{k: v for k, v in m.items() if k != "sportsMarketType"} for m in CLE_PHI_MARKETS]
        prices = _find_polymarket_prices("CLE", "PHI", date(2026, 10, 22), {"markets": markets})
        assert prices["moneyline_home_yes"] == pytest.approx(0.585)

    def test_tagged_moneyline_wins_even_if_listed_last(self):
        markets = list(reversed(CLE_PHI_MARKETS))
        prices = _find_polymarket_prices("CLE", "PHI", date(2026, 10, 22), {"markets": markets})
        assert prices["moneyline_home_yes"] == pytest.approx(0.585)


def _spread(team: str, line: float, home_price: str, created: str | None = None) -> dict:
    other = "Cavaliers" if team == "76ers" else "76ers"
    p_team = home_price if team == "76ers" else f"{1 - float(home_price):.3f}"
    m = _mkt(
        f"Spread: {team} ({line})",
        [team, other],
        [p_team, f"{1 - float(p_team):.3f}"],
        "spreads",
    )
    if created:
        m["createdAt"] = created
    return m


class TestSpreadParsing:
    def test_main_line_beats_smaller_alt_line(self):
        """Main PHI -2.5 (opened first) must win over alts added later, incl. -1.5."""
        markets = [
            _spread("76ers", -3.5, "0.485", "2026-10-20T22:53:00Z"),
            _spread("76ers", -2.5, "0.535", "2026-10-16T00:51:04Z"),
            _spread("76ers", -1.5, "0.565", "2026-10-20T22:53:19Z"),
            _spread("Cavaliers", -1.5, "0.615", "2026-10-20T22:53:20Z"),
        ]
        prices = _find_polymarket_prices("CLE", "PHI", date(2026, 10, 22), {"markets": markets})
        assert prices["spread_line"] == pytest.approx(-2.5)
        assert prices["spread_home_yes"] == pytest.approx(0.535)

    def test_listing_order_when_no_created_at(self):
        markets = [
            _spread("76ers", -2.5, "0.535"),
            _spread("76ers", -1.5, "0.565"),
            _spread("Cavaliers", -1.5, "0.615"),
        ]
        prices = _find_polymarket_prices("CLE", "PHI", date(2026, 10, 22), {"markets": markets})
        assert prices["spread_line"] == pytest.approx(-2.5)
