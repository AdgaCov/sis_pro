from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.utils.fechas import ahora_utc

ROL_ADMIN = "admin"
ROL_SUPERVISOR = "supervisor"
ROL_UNIDAD = "unidad"
ROL_INVITADO = "invitado"
ROLES = (ROL_ADMIN, ROL_SUPERVISOR, ROL_UNIDAD, ROL_INVITADO)
NOMBRES_ROL = {
    ROL_ADMIN: "Administrador (Planificación)",
    ROL_SUPERVISOR: "Supervisor (DGE)",
    ROL_UNIDAD: "Unidad",
    ROL_INVITADO: "Invitado (solo lectura)",
}


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuario"

    id = db.Column(db.Integer, primary_key=True)
    nombre_usuario = db.Column(db.String(50), nullable=False, unique=True)  # siempre en minúsculas
    nombre_completo = db.Column(db.String(150), nullable=False)
    rol = db.Column(db.Enum(*ROLES, name="rol_usuario"), nullable=False)
    unidad_id = db.Column(db.Integer, db.ForeignKey("unidad.id"), index=True)
    clave_hash = db.Column(db.String(255), nullable=False)
    debe_cambiar_clave = db.Column(db.Boolean, nullable=False, default=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    intentos_fallidos = db.Column(db.Integer, nullable=False, default=0)
    bloqueado_hasta = db.Column(db.DateTime)
    # sube al restablecer la clave o desactivar: invalida las sesiones abiertas
    version_sesion = db.Column(db.Integer, nullable=False, default=1)
    ultimo_ingreso = db.Column(db.DateTime)
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=ahora_utc, onupdate=ahora_utc)

    unidad = db.relationship("Unidad")
    permiso_invitado = db.relationship(
        "PermisoInvitado", back_populates="usuario", uselist=False, cascade="all, delete-orphan"
    )

    # --- clave ---
    def poner_clave(self, clave: str) -> None:
        self.clave_hash = generate_password_hash(clave)

    def verificar_clave(self, clave: str) -> bool:
        return bool(self.clave_hash) and check_password_hash(self.clave_hash, clave or "")

    # --- Flask-Login ---
    def get_id(self) -> str:
        return f"{self.id}:{self.version_sesion}"

    @property
    def is_active(self) -> bool:
        return bool(self.activo)

    @property
    def esta_bloqueado(self) -> bool:
        return bool(self.bloqueado_hasta and self.bloqueado_hasta > ahora_utc())

    # --- roles ---
    @property
    def es_admin(self) -> bool:
        return self.rol == ROL_ADMIN

    @property
    def es_supervisor(self) -> bool:
        return self.rol == ROL_SUPERVISOR

    @property
    def es_unidad(self) -> bool:
        return self.rol == ROL_UNIDAD

    @property
    def es_invitado(self) -> bool:
        return self.rol == ROL_INVITADO

    @property
    def ve_todo(self) -> bool:
        """Admin y supervisor ven y editan tareas de todas las unidades."""
        return self.rol in (ROL_ADMIN, ROL_SUPERVISOR)

    @property
    def nombre_rol(self) -> str:
        return NOMBRES_ROL.get(self.rol, self.rol)

    def __repr__(self):
        return f"<Usuario {self.nombre_usuario}>"
