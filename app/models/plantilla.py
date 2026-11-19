from app.extensions import db
from app.utils.fechas import ahora_utc

ALCANCES = ("tarea", "listado", "informe", "resumen", "agenda", "graficos")
NOMBRES_ALCANCE = {
    "tarea": "Ficha de una tarea",
    "listado": "Listado (lo que muestra el filtro)",
    "informe": "Informe de tareas críticas",
    "resumen": "Resumen ejecutivo (gestiones con el MRE)",
    "agenda": "Agenda Despacho del mes",
    "graficos": "Tablero con gráficos",
}
FORMATOS = ("docx", "xlsx")


class Plantilla(db.Model):
    """Documento Word o Excel con marcadores {{ … }} que se llena con datos de las tareas."""

    __tablename__ = "plantilla"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text)
    alcance = db.Column(db.Enum(*ALCANCES, name="alcance_plantilla"), nullable=False, index=True)
    formato = db.Column(db.Enum(*FORMATOS, name="formato_plantilla"), nullable=False)
    archivo = db.Column(db.String(255), nullable=False)          # nombre en storage/plantillas/
    nombre_original = db.Column(db.String(255), nullable=False)
    marcadores_desconocidos = db.Column(db.JSON)
    activa = db.Column(db.Boolean, nullable=False, default=True)
    subido_por_id = db.Column(db.Integer, db.ForeignKey("usuario.id", ondelete="SET NULL"))
    subido_en = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=ahora_utc)

    subido_por = db.relationship("Usuario")

    @property
    def nombre_alcance(self) -> str:
        return NOMBRES_ALCANCE.get(self.alcance, self.alcance)

    def __repr__(self):
        return f"<Plantilla {self.nombre}>"
