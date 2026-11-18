from app.extensions import db


class Unidad(db.Model):
    __tablename__ = "unidad"

    id = db.Column(db.Integer, primary_key=True)
    sigla = db.Column(db.String(20), nullable=False, unique=True)
    nombre = db.Column(db.String(150), nullable=False)
    # último número usado en el código de tarea (UAF-001…); se lee con bloqueo de fila
    ultimo_correlativo = db.Column(db.Integer, nullable=False, default=0)
    activa = db.Column(db.Boolean, nullable=False, default=True)
    orden = db.Column(db.Integer, nullable=False, default=0)

    cargos = db.relationship("Cargo", back_populates="unidad", order_by="Cargo.nombre")

    def __repr__(self):
        return f"<Unidad {self.sigla}>"


class Cargo(db.Model):
    """Responsable de una tarea: es un cargo, con una persona designada opcional."""

    __tablename__ = "cargo"
    __table_args__ = (db.UniqueConstraint("unidad_id", "nombre", name="uq_cargo_unidad_nombre"),)

    id = db.Column(db.Integer, primary_key=True)
    unidad_id = db.Column(db.Integer, db.ForeignKey("unidad.id"), nullable=False, index=True)
    nombre = db.Column(db.String(150), nullable=False)
    persona = db.Column(db.String(150))
    es_apoyo = db.Column(db.Boolean, nullable=False, default=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    unidad = db.relationship("Unidad", back_populates="cargos")

    def __repr__(self):
        return f"<Cargo {self.nombre}>"
