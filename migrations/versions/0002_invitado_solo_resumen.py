"""El invitado solo ve el resumen ejecutivo: se quitan las opciones de vistas y adjuntos.

Revision ID: 0002_invitado_solo_resumen
Revises: 26a0b94e239d
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_invitado_solo_resumen"
down_revision = "26a0b94e239d"
branch_labels = None
depends_on = None

COLUMNAS = ("ver_resumen", "ver_alertas", "ver_informe", "ver_cronograma", "ver_tareas", "ver_adjuntos")


def upgrade():
    with op.batch_alter_table("permiso_invitado") as tabla:
        for col in COLUMNAS:
            tabla.drop_column(col)


def downgrade():
    with op.batch_alter_table("permiso_invitado") as tabla:
        for col in COLUMNAS:
            tabla.add_column(sa.Column(col, sa.Boolean(), nullable=False, server_default=sa.false()))
