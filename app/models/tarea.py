from app.extensions import db
from app.utils.fechas import ahora_utc

NIVELES_RIESGO = ("Alto", "Medio", "Bajo")
MAX_SUBTAREAS = 40


class Tarea(db.Model):
    __tablename__ = "tarea"

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), nullable=False, unique=True)
    unidad_id = db.Column(db.Integer, db.ForeignKey("unidad.id"), nullable=False, index=True)

    tipo_id = db.Column(db.Integer, db.ForeignKey("catalogo.id"), nullable=False)
    estado_id = db.Column(db.Integer, db.ForeignKey("catalogo.id"), nullable=False)
    instancia_id = db.Column(db.Integer, db.ForeignKey("catalogo.id"))
    prioridad_id = db.Column(db.Integer, db.ForeignKey("catalogo.id"))
    area_id = db.Column(db.Integer, db.ForeignKey("catalogo.id"))

    asunto = db.Column(db.Text, nullable=False)
    gestion_requerida = db.Column(db.Text)
    que_habilita = db.Column(db.Text)
    habilita_a_id = db.Column(db.Integer, db.ForeignKey("tarea.id", ondelete="SET NULL"), index=True)
    riesgo_demora = db.Column(db.Text)
    responsable_id = db.Column(db.Integer, db.ForeignKey("cargo.id"), index=True)
    hoja_ruta = db.Column(db.String(100))
    fecha_solicitud = db.Column(db.Date)
    fecha_limite = db.Column(db.Date)
    fecha_conclusion = db.Column(db.Date)
    resultado = db.Column(db.Text)
    medio_verificacion = db.Column(db.Text)
    observaciones = db.Column(db.Text)
    nivel_riesgo = db.Column(db.Enum(*NIVELES_RIESGO, name="nivel_riesgo"))
    linea_solucion = db.Column(db.Text)
    plazo_solucion = db.Column(db.Date)
    agenda_id = db.Column(db.String(100))

    creado_en = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuario.id", ondelete="SET NULL"))
    actualizado_en = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    actualizado_por_id = db.Column(db.Integer, db.ForeignKey("usuario.id", ondelete="SET NULL"))

    unidad = db.relationship("Unidad")
    tipo = db.relationship("Catalogo", foreign_keys=[tipo_id])
    estado = db.relationship("Catalogo", foreign_keys=[estado_id])
    instancia = db.relationship("Catalogo", foreign_keys=[instancia_id])
    prioridad = db.relationship("Catalogo", foreign_keys=[prioridad_id])
    area = db.relationship("Catalogo", foreign_keys=[area_id])
    responsable = db.relationship("Cargo")
    habilita_a = db.relationship("Tarea", remote_side=[id])
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])
    actualizado_por = db.relationship("Usuario", foreign_keys=[actualizado_por_id])
    subtareas = db.relationship(
        "Subtarea", back_populates="tarea", order_by="Subtarea.orden", cascade="all, delete-orphan"
    )
    adjuntos = db.relationship("Adjunto", back_populates="tarea", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Tarea {self.codigo}>"


class Subtarea(db.Model):
    __tablename__ = "subtarea"

    id = db.Column(db.Integer, primary_key=True)
    tarea_id = db.Column(db.Integer, db.ForeignKey("tarea.id", ondelete="CASCADE"), nullable=False, index=True)
    texto = db.Column(db.String(300), nullable=False)
    fecha = db.Column(db.Date)
    hecho = db.Column(db.Boolean, nullable=False, default=False)
    orden = db.Column(db.Integer, nullable=False, default=0)

    tarea = db.relationship("Tarea", back_populates="subtareas")


class Adjunto(db.Model):
    __tablename__ = "adjunto"

    id = db.Column(db.Integer, primary_key=True)
    tarea_id = db.Column(db.Integer, db.ForeignKey("tarea.id", ondelete="CASCADE"), nullable=False, index=True)
    nombre_original = db.Column(db.String(255), nullable=False)
    ruta_relativa = db.Column(db.String(500), nullable=False)  # relativa a storage/respaldos/
    tamano = db.Column(db.Integer, nullable=False)
    tipo_mime = db.Column(db.String(150))
    subido_por_id = db.Column(db.Integer, db.ForeignKey("usuario.id", ondelete="SET NULL"))
    subido_en = db.Column(db.DateTime, nullable=False, default=ahora_utc)

    tarea = db.relationship("Tarea", back_populates="adjuntos")
    subido_por = db.relationship("Usuario")
