"""initial schema

Revision ID: 57c94bd6b379
Revises:
Create Date: 2026-03-11 14:07:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "57c94bd6b379"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- uploads ---
    op.create_table(
        "uploads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("semestre_label", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_uploads_id"), "uploads", ["id"], unique=False)

    # --- grupos ---
    op.create_table(
        "grupos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("upload_id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("horario", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_grupos_id"), "grupos", ["id"], unique=False)

    # --- alumnos ---
    op.create_table(
        "alumnos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("grupo_id", sa.Integer(), nullable=False),
        sa.Column("folio", sa.String(length=50), nullable=True),
        sa.Column("nombre", sa.String(length=255), nullable=True),
        sa.Column("matricula", sa.String(length=50), nullable=True),
        sa.Column("semestre", sa.String(length=50), nullable=True),
        sa.Column("carrera", sa.String(length=255), nullable=True),
        sa.Column("total_asistencia", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("nutricion", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("fisio", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("limpieza", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("coae", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("taller", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("total", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.ForeignKeyConstraint(["grupo_id"], ["grupos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_alumnos_id"), "alumnos", ["id"], unique=False)

    # --- asistencias ---
    op.create_table(
        "asistencias",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alumno_id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("valor", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["alumno_id"], ["alumnos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_asistencias_id"), "asistencias", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_asistencias_id"), table_name="asistencias")
    op.drop_table("asistencias")
    op.drop_index(op.f("ix_alumnos_id"), table_name="alumnos")
    op.drop_table("alumnos")
    op.drop_index(op.f("ix_grupos_id"), table_name="grupos")
    op.drop_table("grupos")
    op.drop_index(op.f("ix_uploads_id"), table_name="uploads")
    op.drop_table("uploads")
