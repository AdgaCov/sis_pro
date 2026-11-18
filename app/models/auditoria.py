from app.extensions import db
from app.utils.fechas import ahora_utc


class Auditoria(db.Model):
    """Registro de acciones. Las tareas eliminadas guardan su copia completa en `detalle` (papelera)."""

    __tablename__ = "auditoria"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, nullable=False, default=ahora_utc, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id", ondelete="SET NULL"), index=True)
    accion = db.Column(db.String(50), nullable=False, index=True)
    entidad = db.Column(db.String(50))
    entidad_id = db.Column(db.String(50))
    detalle = db.Column(db.JSON)

    usuario = db.relationship("Usuario")
