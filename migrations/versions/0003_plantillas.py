"""Plantillas Word/Excel con marcadores.

Revision ID: 0003_plantillas
Revises: 0002_invitado_solo_resumen
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_plantillas"
down_revision = "0002_invitado_solo_resumen"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "plantilla",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("alcance", sa.Enum("tarea", "listado", "informe", name="alcance_plantilla"), nullable=False),
        sa.Column("formato", sa.Enum("docx", "xlsx", name="formato_plantilla"), nullable=False),
        sa.Column("archivo", sa.String(length=255), nullable=False),
        sa.Column("nombre_original", sa.String(length=255), nullable=False),
        sa.Column("marcadores_desconocidos", sa.JSON(), nullable=True),
        sa.Column("activa", sa.Boolean(), nullable=False),
        sa.Column("subido_por_id", sa.Integer(), nullable=True),
        sa.Column("subido_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["subido_por_id"], ["usuario.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plantilla_alcance", "plantilla", ["alcance"])


def downgrade():
    op.drop_index("ix_plantilla_alcance", table_name="plantilla")
    op.drop_table("plantilla")
