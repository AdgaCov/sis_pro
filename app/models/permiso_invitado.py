from app.extensions import db

VISTAS_INVITADO = ("resumen", "alertas", "informe", "cronograma", "tareas")

permiso_invitado_unidad = db.Table(
    "permiso_invitado_unidad",
    db.Column("permiso_id", db.Integer, db.ForeignKey("permiso_invitado.id", ondelete="CASCADE"), primary_key=True),
    db.Column("unidad_id", db.Integer, db.ForeignKey("unidad.id", ondelete="CASCADE"), primary_key=True),
)


class PermisoInvitado(db.Model):
    """Qué puede ver un invitado. Por defecto, nada."""

    __tablename__ = "permiso_invitado"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    ver_resumen = db.Column(db.Boolean, nullable=False, default=False)
    ver_alertas = db.Column(db.Boolean, nullable=False, default=False)
    ver_informe = db.Column(db.Boolean, nullable=False, default=False)
    ver_cronograma = db.Column(db.Boolean, nullable=False, default=False)
    ver_tareas = db.Column(db.Boolean, nullable=False, default=False)
    todas_unidades = db.Column(db.Boolean, nullable=False, default=False)
    ver_adjuntos = db.Column(db.Boolean, nullable=False, default=False)

    usuario = db.relationship("Usuario", back_populates="permiso_invitado")
    unidades = db.relationship("Unidad", secondary=permiso_invitado_unidad)

    def permite_vista(self, vista: str) -> bool:
        return vista in VISTAS_INVITADO and bool(getattr(self, f"ver_{vista}"))
