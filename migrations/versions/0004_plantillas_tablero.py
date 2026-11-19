"""Plantillas también para el resumen ejecutivo, la agenda y el tablero con gráficos.

Revision ID: 0004_plantillas_tablero
Revises: 0003_plantillas
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_plantillas_tablero"
down_revision = "0003_plantillas"
branch_labels = None
depends_on = None

ANTES = ("tarea", "listado", "informe")
DESPUES = ANTES + ("resumen", "agenda", "graficos")


def _cambiar(valores_de, valores_a):
    with op.batch_alter_table("plantilla") as tabla:
        tabla.alter_column("alcance", existing_type=sa.Enum(*valores_de, name="alcance_plantilla"),
                           type_=sa.Enum(*valores_a, name="alcance_plantilla"), existing_nullable=False)


def upgrade():
    _cambiar(ANTES, DESPUES)


def downgrade():
    op.execute(sa.text("DELETE FROM plantilla WHERE alcance IN ('resumen', 'agenda', 'graficos')"))
    _cambiar(DESPUES, ANTES)
