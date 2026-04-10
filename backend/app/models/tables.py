"""SQLAlchemy ORM models for all CourtEdge database tables."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(3), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(50))
    conference: Mapped[str] = mapped_column(String(4))  # EAST | WEST
    division: Mapped[str] = mapped_column(String(20))

    players: Mapped[list["Player"]] = relationship(back_populates="team")
    ratings: Mapped[list["TeamRating"]] = relationship(back_populates="team")


class Player(Base):
    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    position: Mapped[str | None] = mapped_column(String(5))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    team: Mapped["Team"] = relationship(back_populates="players")
    on_off_splits: Mapped[list["PlayerOnOff"]] = relationship(back_populates="player")
    injuries: Mapped[list["Injury"]] = relationship(back_populates="player")


class TeamRating(Base):
    __tablename__ = "team_ratings"
    __table_args__ = (UniqueConstraint("team_id", "date", "source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    date: Mapped[date] = mapped_column(Date, nullable=False)
    ortg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    drtg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    nrtg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    pace: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    source: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    team: Mapped["Team"] = relationship(back_populates="ratings")


class PlayerOnOff(Base):
    __tablename__ = "player_on_off"
    __table_args__ = (UniqueConstraint("player_id", "date", "source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"))
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    date: Mapped[date] = mapped_column(Date, nullable=False)
    on_ortg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    off_ortg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    on_drtg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    off_drtg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    on_nrtg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    off_nrtg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    on_minutes: Mapped[int | None] = mapped_column(Integer)
    off_minutes: Mapped[int | None] = mapped_column(Integer)
    minutes_per_game: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    minutes_share: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    source: Mapped[str | None] = mapped_column(String(20))

    player: Mapped["Player"] = relationship(back_populates="on_off_splits")
    team: Mapped["Team"] = relationship()


class Injury(Base):
    __tablename__ = "injuries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"))
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    game_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str | None] = mapped_column(String(15))
    reason: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(20))
    is_manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    player: Mapped["Player"] = relationship(back_populates="injuries")
    team: Mapped["Team"] = relationship()


class Game(Base):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    home_team: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    away_team: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    tipoff_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(15), default="SCHEDULED")
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    home_spread: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    total_line: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))

    home_team_rel: Mapped["Team"] = relationship(foreign_keys=[home_team])
    away_team_rel: Mapped["Team"] = relationship(foreign_keys=[away_team])
    markets: Mapped[list["PolymarketMarket"]] = relationship(back_populates="game")
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="game")


class PolymarketMarket(Base):
    __tablename__ = "polymarket_markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"))
    market_type: Mapped[str | None] = mapped_column(String(15))
    polymarket_slug: Mapped[str | None] = mapped_column(String(100))
    polymarket_condition_id: Mapped[str | None] = mapped_column(String(100))
    yes_price: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    no_price: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    volume: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    liquidity: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    game: Mapped["Game"] = relationship(back_populates="markets")


class MarketSnapshot(Base):
    """Permanent record of every market edge the model finds.

    Written by the pipeline on each run.  Unlike PolymarketMarket (which
    tracks raw exchange data), this stores the FULL analysis output:
    model probability, edge, verdict, Kelly fraction, Polymarket price,
    line, and team labels.

    The simulation system reads from this table — never from Polymarket
    directly — so historical edges are preserved even after markets settle.

    Unique on (game_id, market_type): only the BEST pre-game snapshot is
    kept per market.  If a later pipeline run has a lower edge (prices
    moved), the existing row is preserved.
    """
    __tablename__ = "market_snapshots"
    __table_args__ = (UniqueConstraint("game_id", "market_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    game_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    home_team: Mapped[str] = mapped_column(String(3), nullable=False)
    away_team: Mapped[str] = mapped_column(String(3), nullable=False)
    market_type: Mapped[str] = mapped_column(String(15), nullable=False)  # moneyline | spread | total
    home_label: Mapped[str | None] = mapped_column(String(50))  # Polymarket label for home side
    away_label: Mapped[str | None] = mapped_column(String(50))  # Polymarket label for away side
    line: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))  # spread or total line
    polymarket_home_yes: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))  # home/yes price
    polymarket_home_no: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))   # away/no price
    model_probability: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))  # model prob for home/yes
    best_side: Mapped[str | None] = mapped_column(String(50))   # e.g. "Warriors", "Over", "Under"
    best_edge: Mapped[Decimal | None] = mapped_column(Numeric(5, 3))  # edge magnitude
    verdict: Mapped[str | None] = mapped_column(String(15))  # STRONG BUY | BUY | LEAN | HOLD | FADE
    kelly_fraction: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    yes_ev: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    no_ev: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"))
    market_type: Mapped[str | None] = mapped_column(String(15))
    home_adjusted_ortg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    home_adjusted_drtg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    home_adjusted_nrtg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    away_adjusted_ortg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    away_adjusted_drtg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    away_adjusted_nrtg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    projected_spread: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    projected_total: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    home_win_probability: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    spread_cover_probability: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    over_probability: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    schedule_adjustment: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    confidence: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    game: Mapped["Game"] = relationship(back_populates="predictions")


class Bet(Base):
    """Bet tracking — no FK on game_id since pipeline doesn't persist games to DB."""
    __tablename__ = "bets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(String(50), nullable=False)
    prediction_id: Mapped[int | None] = mapped_column(Integer)
    market_type: Mapped[str | None] = mapped_column(String(15))
    selection: Mapped[str | None] = mapped_column(String(200))
    side: Mapped[str | None] = mapped_column(String(3))  # YES | NO
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    model_probability: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    edge_at_entry: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    amount_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    kelly_fraction: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    notes: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str | None] = mapped_column(String(5))  # WIN | LOSS | PUSH
    pnl: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    system_aligned: Mapped[bool] = mapped_column(Boolean, default=True)  # user agreed with model?
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ValidationLog(Base):
    __tablename__ = "validation_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    check_type: Mapped[str | None] = mapped_column(String(30))
    severity: Mapped[str | None] = mapped_column(String(10))
    field: Mapped[str | None] = mapped_column(String(50))
    expected_range: Mapped[str | None] = mapped_column(String(50))
    actual_value: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str | None] = mapped_column(String(20))
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
