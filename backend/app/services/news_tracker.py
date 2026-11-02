"""Injury news vs Polymarket — does the market lag ESPN injury updates?

The ratings model doesn't beat Polymarket (see services/evaluation.py), so the
remaining hypothesis is a timing edge: when a key player's status changes, the
price takes a while to catch up.  This module collects the evidence:

- poll_injury_news(): every ~2 min, log each new ESPN injury update (with ESPN's
  own timestamp) and players dropping off the report  → table injury_news
- record_market_ticks(): on every pipeline run, log each pre-tip-off market's
  Polymarket price + model probability                → table market_ticks
- injury_lag_report(): for news on players who matter, pull the team's
  minute-level Polymarket history (CLOB) around the news and measure how much
  of the move happened before vs after ESPN posted it, and how much was still
  available to someone acting a poll later.
"""

from __future__ import annotations

import asyncio
import statistics
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.connectors.injuries import InjuryFeedConnector
from app.connectors.polymarket import PolymarketConnector
from app.models.database import async_session_factory
from app.models.tables import InjuryNews, MarketTick

if TYPE_CHECKING:
    from collections.abc import Iterable

BET_VERDICTS = ("BUY", "STRONG BUY")
# Expected direction of the team's moneyline price after the news
SEVERITY = {"AVAILABLE": 0.0, "PROBABLE": 0.1, "QUESTIONABLE": 0.5, "DOUBTFUL": 0.75, "OUT": 1.0}
OFFSETS_MIN = (-30, -10, 0, 5, 10, 30)
POLL_LAG_MIN = 2  # we see ESPN news up to one poll late
MIN_MOVE = 0.01  # price moves under 1c are noise
MAX_HOURS_TO_TIP = 36  # news further from the next game isn't about that game


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


# ─── Injury news polling ─────────────────────────────────────────────


def diff_injury_news(
    feed: list[dict[str, Any]],
    latest: dict[tuple[str, str], dict[str, Any]],
    now: datetime,
) -> list[dict[str, Any]]:
    """Rows to append to injury_news given the current feed and each player's last row.

    ``latest`` maps (player_key, team) → {kind, status, news_at}.  A feed entry is
    news when the player is new, returning to the report, or has a new status or
    ESPN timestamp.  A player on the report last time but not now is "cleared".
    """
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for entry in feed:
        team = entry.get("team") or ""
        name = entry.get("player_name") or ""
        if not team or not name:
            continue
        key = (str(entry.get("player_id") or name), team)
        if key in seen:
            continue
        seen.add(key)
        status = entry.get("status") or "QUESTIONABLE"
        news_at = _parse_ts(entry.get("news_at"))
        prev = latest.get(key)
        if (
            prev is not None
            and prev["kind"] == "update"
            and prev["status"] == status
            and _parse_ts(prev["news_at"]) == news_at
        ):
            continue
        rows.append({
            "player_key": key[0], "player_name": name, "team": team, "kind": "update",
            "status": status, "espn_status": entry.get("espn_status"),
            "comment": entry.get("comment"), "news_at": news_at, "detected_at": now,
        })
    for key, prev in latest.items():
        if prev["kind"] == "update" and key not in seen:
            rows.append({
                "player_key": key[0], "player_name": prev.get("player_name") or key[0],
                "team": key[1], "kind": "cleared", "status": "AVAILABLE", "espn_status": None,
                "comment": None, "news_at": None, "detected_at": now,
            })
    return rows


async def poll_injury_news(now: datetime | None = None) -> int:
    """Log new ESPN injury updates. Returns the number of rows written."""
    now = now or datetime.now(UTC)
    feed_conn = InjuryFeedConnector()
    try:
        feed = await feed_conn.get_injury_report()
    finally:
        await feed_conn.close()
    # Only ESPN entries carry timestamps and stable ids; on an ESPN failure the
    # connector falls back to another source — never diff against that (it would
    # mark the whole league "cleared").
    feed = [e for e in feed if e.get("source") == "ESPN"]
    if not feed:
        logger.warning("Injury news poll: no ESPN data, skipping")
        return 0

    async with async_session_factory() as session, session.begin():
        result = await session.execute(
            select(InjuryNews)
            .ext(distinct_on(InjuryNews.player_key, InjuryNews.team))
            .order_by(InjuryNews.player_key, InjuryNews.team,
                      InjuryNews.detected_at.desc(), InjuryNews.id.desc())
        )
        latest = {
            (r.player_key, r.team): {
                "kind": r.kind, "status": r.status, "news_at": r.news_at,
                "player_name": r.player_name,
            }
            for r in result.scalars()
        }
        rows = diff_injury_news(feed, latest, now)
        if rows:
            await session.execute(pg_insert(InjuryNews).values(rows).on_conflict_do_nothing())
    if rows:
        logger.info(f"📰 Injury news: {len(rows)} new updates")
    return len(rows)


# ─── Market ticks ────────────────────────────────────────────────────


def ticks_from_analysis(analysis: Any, now: datetime) -> list[dict[str, Any]]:
    """Price/model rows for every live (not settled) market of games not yet started."""
    rows: list[dict[str, Any]] = []
    for game in analysis.games:
        if game.live is not None and game.live.game_status != 1:
            continue
        if game.tipoff is not None and _parse_ts(game.tipoff) <= now:
            continue
        for mtype, mkt in game.markets.items():
            price = mkt.polymarket_home_yes
            if price is None or mkt.edge.verdict == "SETTLED":
                continue
            side = None
            if mkt.edge.verdict in BET_VERDICTS:
                side = mkt.edge.best_side in (mkt.home_label, "YES", "Over")
            rows.append({
                "captured_at": now, "game_date": analysis.date, "game_id": game.game_id,
                "tipoff": game.tipoff, "market_type": mtype, "line": mkt.line,
                "price_home_yes": price, "model_prob": mkt.model_probability,
                "verdict": mkt.edge.verdict, "bet_side_yes": side,
            })
    return rows


async def record_market_ticks(analysis: Any, now: datetime | None = None) -> int:
    rows = ticks_from_analysis(analysis, now or datetime.now(UTC))
    if rows:
        async with async_session_factory() as session, session.begin():
            await session.execute(pg_insert(MarketTick).values(rows))
    return len(rows)


# ─── Reaction measurement ────────────────────────────────────────────


def price_at(points: list[tuple[datetime, float]], t: datetime) -> float | None:
    """Last traded price at or before t (None if the history starts after t)."""
    price = None
    for ts, p in points:
        if ts > t:
            break
        price = p
    return price


def measure_reaction(
    points: list[tuple[datetime, float]],
    event_time: datetime,
    tipoff: datetime | None,
    direction: int,
) -> dict[str, Any] | None:
    """How the team's price moved around a news time (direction: +1 up expected, −1 down).

    Moves are signed so positive = toward what the news implies.  Offsets past
    tip-off are dropped (in-game prices react to the game, not the news).
    """
    if not points:
        return None
    cap = tipoff - timedelta(minutes=1) if tipoff else None
    if cap is not None and cap <= event_time:
        return None

    def at(minutes: int) -> float | None:
        t = event_time + timedelta(minutes=minutes)
        if cap is not None and t > cap:
            t = cap
        return price_at(points, t)

    p_before, p0, p_seen, p_after = at(-30), at(0), at(POLL_LAG_MIN), at(30)
    if None in (p_before, p0, p_after):
        return None
    moved_before = (p0 - p_before) * direction
    moved_after = (p_after - p0) * direction
    total = moved_before + moved_after
    return {
        "prices": {str(m): at(m) for m in OFFSETS_MIN},
        "moved_before": round(moved_before, 4),
        "moved_after": round(moved_after, 4),
        # Still available to someone buying one poll after ESPN posted it
        "tradable_move": round((p_after - (p_seen if p_seen is not None else p0)) * direction, 4),
        "share_after": round(moved_after / total, 3) if total >= MIN_MOVE else None,
    }


class InjuryNewsEvent(BaseModel):
    player_name: str
    team: str
    kind: str
    status: str
    prev_status: str | None  # None = first time we saw this player (status change unknown)
    comment: str | None
    event_time: datetime
    timestamp_source: str  # espn | detected
    impact_nrtg: float | None  # model's NRtg cost of a full absence
    game_id: str | None = None
    tipoff: datetime | None = None
    reaction: dict[str, Any] | None = None
    note: str | None = None


class InjuryLagSummary(BaseModel):
    events: int  # status changes on key players with a measurable price
    median_share_after: float | None  # share of the move that came after ESPN posted
    mean_tradable_move: float | None  # price move still available after one poll
    tradable_2c: int  # events with ≥2c still available


class InjuryLagReport(BaseModel):
    since: datetime
    min_impact: float
    summary: InjuryLagSummary
    events: list[InjuryNewsEvent]


def summarize(events: Iterable[InjuryNewsEvent]) -> InjuryLagSummary:
    """Only real status changes (known previous status) count toward the summary."""
    measured = [
        e for e in events
        if e.reaction is not None and e.prev_status is not None and e.prev_status != e.status
    ]
    shares = [e.reaction["share_after"] for e in measured if e.reaction["share_after"] is not None]
    tradable = [e.reaction["tradable_move"] for e in measured]
    return InjuryLagSummary(
        events=len(measured),
        median_share_after=round(statistics.median(shares), 3) if shares else None,
        mean_tradable_move=round(statistics.fmean(tradable), 4) if tradable else None,
        tradable_2c=sum(1 for t in tradable if t >= 0.02),
    )


async def _player_impacts(names: set[str]) -> dict[str, float]:
    """|NRtg| cost of each player missing a game, via the model's own absence maths."""
    from app.services.pipeline import _build_player_absences, _fetch_player_metrics

    metrics = await _fetch_player_metrics([])
    out: dict[str, float] = {}
    for name in names:
        absences = _build_player_absences([{"player_name": name, "status": "OUT"}], metrics)
        out[name] = abs(absences[0].nrtg_impact) if absences else 0.0
    return out


async def injury_lag_report(
    days: int = 14, min_impact: float = 1.0, now: datetime | None = None,
) -> InjuryLagReport:
    """Injury news on key players and how the team's Polymarket price reacted."""
    from app.services.pipeline import _get_team_nickname, fetch_schedule

    now = now or datetime.now(UTC)
    since = now - timedelta(days=days)
    async with async_session_factory() as session:
        rows = (await session.execute(
            select(InjuryNews)
            .where(
                func.coalesce(InjuryNews.news_at, InjuryNews.detected_at)
                >= since - timedelta(days=30)
            )
            .order_by(InjuryNews.player_key, InjuryNews.team, InjuryNews.detected_at, InjuryNews.id)
        )).scalars().all()

    # Pair each row with the player's previous row to know what changed
    candidates: list[tuple[InjuryNews, str | None]] = []
    prev_by_key: dict[tuple[str, str], InjuryNews] = {}
    for r in rows:
        key = (r.player_key, r.team)
        prev = prev_by_key.get(key)
        prev_by_key[key] = r
        event_time = r.news_at or r.detected_at
        if event_time < since:
            continue
        prev_status = prev.status if prev is not None else None
        if prev is not None and prev.status == r.status:
            continue  # same status, refreshed blurb — not news
        candidates.append((r, prev_status))

    impacts = await _player_impacts({r.player_name for r, _ in candidates})
    candidates = [(r, p) for r, p in candidates if impacts.get(r.player_name, 0.0) >= min_impact]

    schedules: dict[date, list[dict[str, Any]]] = {}
    events_cache: dict[str, dict[str, Any] | None] = {}
    history_cache: dict[tuple[str, int, int], list[tuple[datetime, float]]] = {}
    poly = PolymarketConnector()
    limit = asyncio.Semaphore(4)

    async def next_game(team: str, t: datetime) -> dict[str, Any] | None:
        from app.services.pipeline import _ET

        start = t.astimezone(_ET).date() - timedelta(days=1)
        for d in (start + timedelta(days=i) for i in range(3)):
            if d not in schedules:
                try:
                    schedules[d] = await fetch_schedule(d)
                except Exception as e:
                    logger.warning(f"Injury lag: schedule {d} failed: {e}")
                    schedules[d] = []
            for g in schedules[d]:
                tip = _parse_ts(g.get("tipoff"))
                if team in (g["home_team"], g["away_team"]) and tip and tip > t \
                        and tip - t <= timedelta(hours=MAX_HOURS_TO_TIP):
                    return g
        return None

    async def build(r: InjuryNews, prev_status: str | None) -> InjuryNewsEvent:
        event_time = r.news_at or r.detected_at
        sev_new = SEVERITY.get(r.status, 0.5)
        sev_old = SEVERITY.get(prev_status or "AVAILABLE", 0.0)
        direction = -1 if sev_new > sev_old else 1
        ev = InjuryNewsEvent(
            player_name=r.player_name, team=r.team, kind=r.kind, status=r.status,
            prev_status=prev_status, comment=r.comment, event_time=event_time,
            timestamp_source="espn" if r.news_at else "detected",
            impact_nrtg=round(impacts.get(r.player_name, 0.0), 2),
        )
        async with limit:
            game = await next_game(r.team, event_time)
            if game is None:
                ev.note = f"no game within {MAX_HOURS_TO_TIP}h"
                return ev
            ev.game_id, ev.tipoff = game["game_id"], _parse_ts(game.get("tipoff"))
            gkey = game["game_id"]
            if gkey not in events_cache:
                gdate = date.fromisoformat(gkey[:10])
                events_cache[gkey] = await poly.get_game_event(
                    game["away_team"], game["home_team"], gdate
                )
            event = events_cache[gkey]
            token = PolymarketConnector.moneyline_token(event or {}, _get_team_nickname(r.team))
            if token is None:
                ev.note = "no Polymarket moneyline"
                return ev
            start = event_time - timedelta(minutes=35)
            end = min(event_time + timedelta(minutes=35), ev.tipoff or event_time)
            hkey = (token, int(start.timestamp()), int(end.timestamp()))
            if hkey not in history_cache:
                try:
                    history_cache[hkey] = await poly.get_price_history(token, start, end)
                except Exception as e:
                    logger.warning(f"Injury lag: price history failed for {r.player_name}: {e}")
                    history_cache[hkey] = []
            ev.reaction = measure_reaction(history_cache[hkey], event_time, ev.tipoff, direction)
            if ev.reaction is None:
                ev.note = "no price history around the news"
        return ev

    try:
        events = await asyncio.gather(*(build(r, p) for r, p in candidates))
    finally:
        await poly.close()
    events.sort(key=lambda e: e.event_time, reverse=True)
    return InjuryLagReport(
        since=since, min_impact=min_impact, summary=summarize(events), events=list(events),
    )


# ─── Closing-line value ──────────────────────────────────────────────


def clv_from_ticks(ticks: Iterable[Any]) -> list[float]:
    """CLV per (game, market): closing − entry price on the side of the first BUY+ verdict.

    Entry = first tick with a BUY/STRONG BUY verdict; close = last tick before
    tip-off.  Only counted when the line didn't change in between.
    """
    by_market: dict[tuple[str, str], list[Any]] = {}
    for t in ticks:
        by_market.setdefault((t.game_id, t.market_type), []).append(t)
    out: list[float] = []
    for series in by_market.values():
        series.sort(key=lambda t: t.captured_at)
        entry = next((t for t in series if t.bet_side_yes is not None), None)
        if entry is None:
            continue
        close = series[-1]
        if close is entry or close.line != entry.line:
            continue
        sign = 1 if entry.bet_side_yes else -1
        out.append(round(float(close.price_home_yes - entry.price_home_yes) * sign, 4))
    return out


async def load_clv(before: datetime | None = None) -> list[float]:
    """CLV values for every game whose ticks are complete (tipped off before ``before``)."""
    before = before or datetime.now(UTC)
    async with async_session_factory() as session:
        ticks = (await session.execute(
            select(MarketTick).where(MarketTick.tipoff < before)
        )).scalars().all()
    return clv_from_ticks(ticks)
