"""create daily_predictions table (History moves from JSON files into the DB)

Revision ID: d41a7c9e2b10
Revises: c27ff144fa18
Create Date: 2026-10-23 12:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d41a7c9e2b10"
down_revision: Union[str, None] = "c27ff144fa18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_predictions",
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("games_count", sa.Integer(), nullable=False),
        sa.Column(
            "saved_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("game_date"),
    )


def downgrade() -> None:
    op.drop_table("daily_predictions")
