from app.extensions import db

# El invitado solo ve el resumen ejecutivo (y lo descarga en PDF), de las unidades que el admin le asigne.
VISTA_INVITADO = "resumen"

permiso_invitado_unidad = db.Table(
    "permiso_invitado_unidad",
    db.Column("permiso_id", db.Integer, db.ForeignKey("permiso_invitado.id", ondelete="CASCADE"), primary_key=True),
    db.Column("unidad_id", db.Integer, db.ForeignKey("unidad.id", ondelete="CASCADE"), primary_key=True),
)


class PermisoInvitado(db.Model):
    """Qué unidades puede ver un invitado. Por defecto, ninguna."""

    __tablename__ = "permiso_invitado"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    todas_unidades = db.Column(db.Boolean, nullable=False, default=False)

    usuario = db.relationship("Usuario", back_populates="permiso_invitado")
    unidades = db.relationship("Unidad", secondary=permiso_invitado_unidad)
