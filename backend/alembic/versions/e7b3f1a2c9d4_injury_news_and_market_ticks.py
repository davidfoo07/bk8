"""injury_news and market_ticks (Polymarket reaction to injury news, CLV)

Revision ID: e7b3f1a2c9d4
Revises: d41a7c9e2b10
Create Date: 2026-11-02 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7b3f1a2c9d4"
down_revision: Union[str, None] = "d41a7c9e2b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "injury_news",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_key", sa.String(length=64), nullable=False),
        sa.Column("player_name", sa.String(length=100), nullable=False),
        sa.Column("team", sa.String(length=3), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=15), nullable=False),
        sa.Column("espn_status", sa.String(length=30), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("news_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_key", "team", "kind", "status", "news_at", name="uq_injury_news"),
    )
    op.create_index("ix_injury_news_player", "injury_news", ["player_key", "team", "detected_at"])
    op.create_table(
        "market_ticks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column("game_id", sa.String(length=50), nullable=False),
        sa.Column("tipoff", sa.DateTime(timezone=True), nullable=True),
        sa.Column("market_type", sa.String(length=15), nullable=False),
        sa.Column("line", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("price_home_yes", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("model_prob", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("verdict", sa.String(length=15), nullable=True),
        sa.Column("bet_side_yes", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_ticks_game", "market_ticks", ["game_id", "market_type", "captured_at"])


def downgrade() -> None:
    op.drop_index("ix_market_ticks_game", table_name="market_ticks")
    op.drop_table("market_ticks")
    op.drop_index("ix_injury_news_player", table_name="injury_news")
    op.drop_table("injury_news")
