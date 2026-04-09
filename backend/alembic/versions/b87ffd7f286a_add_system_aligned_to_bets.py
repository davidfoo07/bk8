"""add missing bets columns (notes, system_aligned) and widen selection

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
    conn = op.get_bind()
    insp = inspect(conn)
    columns = {c["name"] for c in insp.get_columns("bets")}

    # 1. Add 'notes' column (Text, nullable)
    if "notes" not in columns:
        op.add_column("bets", sa.Column("notes", sa.Text(), nullable=True))

    # 2. Add 'system_aligned' column (Boolean, default True)
    if "system_aligned" not in columns:
        op.add_column(
            "bets",
            sa.Column("system_aligned", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        )
        op.execute("UPDATE bets SET system_aligned = TRUE WHERE system_aligned IS NULL")
    else:
        op.alter_column(
            "bets", "system_aligned",
            existing_type=sa.BOOLEAN(),
            nullable=False,
            existing_server_default=sa.text("true"),
        )

    # 3. Widen 'selection' from VARCHAR(100) to VARCHAR(200)
    op.alter_column(
        "bets", "selection",
        existing_type=sa.String(length=100),
        type_=sa.String(length=200),
        existing_nullable=True,
    )

    # 4. Drop foreign keys that the ORM no longer declares
    #    Check if they exist first to avoid transaction-killing errors
    fks = {fk["name"] for fk in insp.get_foreign_keys("bets") if fk.get("name")}
    if "bets_game_id_fkey" in fks:
        op.drop_constraint("bets_game_id_fkey", "bets", type_="foreignkey")
    if "bets_prediction_id_fkey" in fks:
        op.drop_constraint("bets_prediction_id_fkey", "bets", type_="foreignkey")


def downgrade() -> None:
    op.drop_column("bets", "system_aligned")
    op.drop_column("bets", "notes")
    op.alter_column(
        "bets", "selection",
        existing_type=sa.String(length=200),
        type_=sa.String(length=100),
        existing_nullable=True,
    )
