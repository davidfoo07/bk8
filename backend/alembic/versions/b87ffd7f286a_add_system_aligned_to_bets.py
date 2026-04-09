"""add system_aligned to bets

Revision ID: b87ffd7f286a
Revises: 8ed6dd1951d5
Create Date: 2026-04-10 01:48:33.097609

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'b87ffd7f286a'
down_revision: Union[str, None] = '8ed6dd1951d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if column already exists (local dev may have added it manually)
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("bets")]

    if "system_aligned" not in columns:
        op.add_column("bets", sa.Column("system_aligned", sa.Boolean(), server_default=sa.text("true"), nullable=False))
        # Backfill existing rows
        op.execute("UPDATE bets SET system_aligned = TRUE WHERE system_aligned IS NULL")
    else:
        # Column exists but may be nullable — ensure NOT NULL
        op.alter_column("bets", "system_aligned",
                         existing_type=sa.BOOLEAN(),
                         nullable=False,
                         existing_server_default=sa.text("true"))


def downgrade() -> None:
    op.drop_column("bets", "system_aligned")
