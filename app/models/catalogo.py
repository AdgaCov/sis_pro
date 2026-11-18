from app.extensions import db

TIPOS_CATALOGO = ("tipo", "instancia", "estado", "prioridad", "area")

# Valores que la lógica usa por nombre: no se pueden borrar ni renombrar.
TIPO_INTERNA = "Tarea interna"
ESTADO_CONCLUIDO = "Concluido"
PRIORIDAD_ALTA = "Alta"


class Catalogo(db.Model):
    __tablename__ = "catalogo"
    __table_args__ = (db.UniqueConstraint("tipo", "valor", name="uq_catalogo_tipo_valor"),)

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.Enum(*TIPOS_CATALOGO, name="tipo_catalogo"), nullable=False, index=True)
    valor = db.Column(db.String(200), nullable=False)
    orden = db.Column(db.Integer, nullable=False, default=0)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    protegido = db.Column(db.Boolean, nullable=False, default=False)

    def __repr__(self):
        return f"<Catalogo {self.tipo}: {self.valor}>"
