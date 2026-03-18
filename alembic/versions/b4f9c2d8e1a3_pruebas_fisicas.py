"""pruebas_fisicas

Revision ID: b4f9c2d8e1a3
Revises: 57c94bd6b379
Create Date: 2026-03-18 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4f9c2d8e1a3"
down_revision: Union[str, None] = "57c94bd6b379"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- seguimientos ---
    op.create_table(
        "seguimientos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("aplica_a_todos", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_seguimientos_id"), "seguimientos", ["id"], unique=False)

    # --- seguimiento_grupos ---
    op.create_table(
        "seguimiento_grupos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("seguimiento_id", sa.Integer(), nullable=False),
        sa.Column("nombre_grupo", sa.String(length=255), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["seguimiento_id"], ["seguimientos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_seguimiento_grupos_id"), "seguimiento_grupos", ["id"], unique=False)

    # --- pruebas_fisicas ---
    op.create_table(
        "pruebas_fisicas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("seguimiento_id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("unidad", sa.String(length=50), nullable=True),
        sa.Column("mayor_es_mejor", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["seguimiento_id"], ["seguimientos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pruebas_fisicas_id"), "pruebas_fisicas", ["id"], unique=False)

    # --- periodos_seguimiento ---
    op.create_table(
        "periodos_seguimiento",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("seguimiento_id", sa.Integer(), nullable=False),
        sa.Column("semestre_label", sa.String(length=100), nullable=False),
        sa.Column("nombre_periodo", sa.String(length=100), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["seguimiento_id"], ["seguimientos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_periodos_seguimiento_id"), "periodos_seguimiento", ["id"], unique=False)

    # --- resultados_prueba ---
    op.create_table(
        "resultados_prueba",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("periodo_id", sa.Integer(), nullable=False),
        sa.Column("prueba_id", sa.Integer(), nullable=False),
        sa.Column("grupo_id", sa.Integer(), nullable=True),
        sa.Column("matricula", sa.String(length=50), nullable=False),
        sa.Column("nombre_alumno", sa.String(length=255), nullable=True),
        sa.Column("genero", sa.String(length=50), nullable=True),
        sa.Column("edad", sa.Integer(), nullable=True),
        sa.Column("valor", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.ForeignKeyConstraint(["periodo_id"], ["periodos_seguimiento.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prueba_id"], ["pruebas_fisicas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["grupo_id"], ["seguimiento_grupos.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_resultados_prueba_id"), "resultados_prueba", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_resultados_prueba_id"), table_name="resultados_prueba")
    op.drop_table("resultados_prueba")
    op.drop_index(op.f("ix_periodos_seguimiento_id"), table_name="periodos_seguimiento")
    op.drop_table("periodos_seguimiento")
    op.drop_index(op.f("ix_pruebas_fisicas_id"), table_name="pruebas_fisicas")
    op.drop_table("pruebas_fisicas")
    op.drop_index(op.f("ix_seguimiento_grupos_id"), table_name="seguimiento_grupos")
    op.drop_table("seguimiento_grupos")
    op.drop_index(op.f("ix_seguimientos_id"), table_name="seguimientos")
    op.drop_table("seguimientos")
