"""add_max_asistencia_to_grupos

Revision ID: c5e8a1f3b2d7
Revises: b4f9c2d8e1a3
Create Date: 2026-03-18 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5e8a1f3b2d7"
down_revision: Union[str, None] = "b4f9c2d8e1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "grupos",
        sa.Column("max_asistencia", sa.Numeric(precision=6, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("grupos", "max_asistencia")
