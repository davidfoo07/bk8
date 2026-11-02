"""Tests for injury-news logging, price reaction measurement, ticks and CLV."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select

from app.models.database import async_session_factory
from app.models.tables import InjuryNews, MarketTick
from app.services import news_tracker
from app.services.news_tracker import (
    InjuryNewsEvent,
    clv_from_ticks,
    diff_injury_news,
    measure_reaction,
    summarize,
    ticks_from_analysis,
)

NOW = datetime(2026, 11, 2, 22, 0, tzinfo=UTC)


def _entry(name="Anthony Edwards", team="MIN", status="OUT", news_at="2026-11-02T21:00Z", pid="1"):
    return {
        "player_name": name,
        "player_id": pid,
        "team": team,
        "status": status,
        "news_at": news_at,
        "espn_status": status.title(),
        "comment": "x",
        "source": "ESPN",
    }


def _latest(status="OUT", news_at="2026-11-02T21:00Z", kind="update"):
    return {
        ("1", "MIN"): {
            "kind": kind,
            "status": status,
            "news_at": news_at,
            "player_name": "Anthony Edwards",
        }
    }


class TestDiffInjuryNews:
    def test_new_player_is_news(self):
        rows = diff_injury_news([_entry()], {}, NOW)
        assert [(r["kind"], r["status"]) for r in rows] == [("update", "OUT")]
        assert rows[0]["news_at"] == datetime(2026, 11, 2, 21, 0, tzinfo=UTC)

    def test_unchanged_entry_is_not_news(self):
        assert diff_injury_news([_entry()], _latest(), NOW) == []

    def test_status_change_is_news(self):
        rows = diff_injury_news([_entry(status="OUT")], _latest(status="QUESTIONABLE"), NOW)
        assert [r["status"] for r in rows] == ["OUT"]

    def test_new_espn_timestamp_is_news(self):
        rows = diff_injury_news([_entry(news_at="2026-11-02T21:30Z")], _latest(), NOW)
        assert len(rows) == 1

    def test_dropping_off_the_report_is_cleared(self):
        rows = diff_injury_news([_entry(name="Other", pid="2")], _latest(), NOW)
        cleared = [r for r in rows if r["kind"] == "cleared"]
        assert cleared and cleared[0]["status"] == "AVAILABLE" and cleared[0]["team"] == "MIN"

    def test_returning_to_report_after_clear_is_news(self):
        rows = diff_injury_news([_entry()], _latest(kind="cleared", status="AVAILABLE"), NOW)
        assert [r["kind"] for r in rows] == ["update"]


def _series(prices: dict[int, float], t0: datetime) -> list[tuple[datetime, float]]:
    return sorted((t0 + timedelta(minutes=m), p) for m, p in prices.items())


class TestMeasureReaction:
    T0 = datetime(2026, 11, 2, 20, 0, tzinfo=UTC)

    def test_market_moves_after_news(self):
        pts = _series({-40: 0.60, -30: 0.60, 0: 0.59, 2: 0.58, 10: 0.50, 30: 0.48}, self.T0)
        r = measure_reaction(pts, self.T0, self.T0 + timedelta(hours=2), direction=-1)
        assert r["moved_before"] == 0.01 and r["moved_after"] == 0.11
        assert r["tradable_move"] == 0.10  # from 0.58 at +2 min to 0.48
        assert r["share_after"] == round(0.11 / 0.12, 3)

    def test_market_already_moved(self):
        pts = _series({-30: 0.60, -5: 0.48, 0: 0.48, 30: 0.48}, self.T0)
        r = measure_reaction(pts, self.T0, None, direction=-1)
        assert r["share_after"] == 0.0 and r["tradable_move"] == 0.0

    def test_offsets_capped_at_tipoff(self):
        pts = _series({-30: 0.6, 0: 0.6, 5: 0.55, 20: 0.2}, self.T0)  # 20 = in-game swing
        r = measure_reaction(pts, self.T0, self.T0 + timedelta(minutes=10), direction=-1)
        assert r["prices"]["30"] == 0.55  # read at tip-off − 1 min, not in-game

    def test_news_after_tipoff_is_ignored(self):
        pts = _series({-30: 0.6, 0: 0.6}, self.T0)
        assert measure_reaction(pts, self.T0, self.T0 - timedelta(minutes=5), direction=-1) is None


def _event(prev, reaction):
    return InjuryNewsEvent(
        player_name="x",
        team="MIN",
        kind="update",
        status="OUT",
        prev_status=prev,
        comment=None,
        event_time=NOW,
        timestamp_source="espn",
        impact_nrtg=2.0,
        reaction=reaction,
    )


def test_summary_counts_only_known_status_changes():
    r = {"share_after": 0.5, "tradable_move": 0.03}
    s = summarize(
        [_event("QUESTIONABLE", r), _event(None, r), _event("OUT", r), _event("AVAILABLE", None)]
    )
    assert s.events == 1 and s.tradable_2c == 1 and s.median_share_after == 0.5


def _analysis():
    edge = lambda verdict, side: SimpleNamespace(verdict=verdict, best_side=side)  # noqa: E731
    mkt = lambda v, side, price=0.55: SimpleNamespace(  # noqa: E731
        polymarket_home_yes=price,
        edge=edge(v, side),
        home_label="Thunder",
        line=None,
        model_probability=0.6,
    )
    pre = SimpleNamespace(
        game_id="g1",
        tipoff=NOW + timedelta(hours=1),
        live=SimpleNamespace(game_status=1),
        markets={
            "moneyline": mkt("BUY", "Thunder"),
            "total": mkt("LEAN", "Under"),
            "spread": mkt("SETTLED", "SETTLED"),
        },
    )
    live = SimpleNamespace(
        game_id="g2",
        tipoff=NOW - timedelta(hours=1),
        live=SimpleNamespace(game_status=2),
        markets={"moneyline": mkt("BUY", "x")},
    )
    return SimpleNamespace(date=date(2026, 11, 2), games=[pre, live])


def test_ticks_only_for_pre_tipoff_live_markets():
    rows = ticks_from_analysis(_analysis(), NOW)
    assert {(r["game_id"], r["market_type"], r["bet_side_yes"]) for r in rows} == {
        ("g1", "moneyline", True),
        ("g1", "total", None),
    }


def _tick(minute, price, side=None, line=None, game="g1", mtype="spread"):
    return SimpleNamespace(
        game_id=game,
        market_type=mtype,
        captured_at=NOW + timedelta(minutes=minute),
        price_home_yes=Decimal(str(price)),
        bet_side_yes=side,
        line=line,
    )


class TestClv:
    def test_price_moves_toward_flagged_side(self):
        ticks = [_tick(0, 0.50), _tick(5, 0.52, side=True), _tick(10, 0.56, side=True)]
        assert clv_from_ticks(ticks) == [0.04]

    def test_away_side_sign(self):
        assert clv_from_ticks([_tick(0, 0.50, side=False), _tick(5, 0.46)]) == [0.04]

    def test_line_change_or_no_flag_skipped(self):
        moved = [
            _tick(0, 0.5, side=True, line=Decimal("-2.5")),
            _tick(5, 0.6, line=Decimal("-3.5")),
        ]
        never = [_tick(0, 0.5, game="g2"), _tick(5, 0.6, game="g2")]
        assert clv_from_ticks(moved + never) == []


class TestDatabase:
    async def test_poll_logs_updates_once_and_clears(self, monkeypatch):
        feeds = [
            [_entry(), _entry(name="LeBron James", team="PHI", pid="2", status="QUESTIONABLE")],
            [_entry(), _entry(name="LeBron James", team="PHI", pid="2", status="QUESTIONABLE")],
            [
                _entry(
                    name="LeBron James",
                    team="PHI",
                    pid="2",
                    status="OUT",
                    news_at="2026-11-02T22:30Z",
                )
            ],
        ]

        class FakeFeed:
            async def get_injury_report(self):
                return feeds.pop(0)

            async def close(self):
                pass

        monkeypatch.setattr(news_tracker, "InjuryFeedConnector", FakeFeed)
        assert await news_tracker.poll_injury_news(NOW) == 2
        assert await news_tracker.poll_injury_news(NOW + timedelta(minutes=2)) == 0
        assert await news_tracker.poll_injury_news(NOW + timedelta(minutes=4)) == 2
        async with async_session_factory() as s:
            rows = (await s.execute(select(InjuryNews).order_by(InjuryNews.id))).scalars().all()
        assert [(r.player_name, r.kind, r.status) for r in rows[2:]] == [
            ("LeBron James", "update", "OUT"),
            ("Anthony Edwards", "cleared", "AVAILABLE"),
        ]

    async def test_failed_feed_never_clears_everyone(self, monkeypatch):
        class Fallback:
            async def get_injury_report(self):
                return [{**_entry(), "source": "NBA CDN"}]

            async def close(self):
                pass

        monkeypatch.setattr(news_tracker, "InjuryFeedConnector", Fallback)
        assert await news_tracker.poll_injury_news(NOW) == 0

    async def test_ticks_round_trip_to_clv(self):
        g = _analysis().games[0]
        a = SimpleNamespace(date=date(2026, 11, 2), games=[g])
        await news_tracker.record_market_ticks(a, NOW - timedelta(hours=2))
        g.markets["moneyline"].polymarket_home_yes = 0.60
        await news_tracker.record_market_ticks(a, NOW - timedelta(hours=1, minutes=30))
        async with async_session_factory() as s:
            assert len((await s.execute(select(MarketTick))).scalars().all()) == 4
        assert await news_tracker.load_clv(before=NOW + timedelta(hours=2)) == [0.05]
