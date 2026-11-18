"""Autenticación, claves y administración de usuarios."""
import re
import secrets
from datetime import timedelta

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import PermisoInvitado, Unidad, Usuario
from app.models.usuario import ROL_ADMIN, ROL_INVITADO, ROL_UNIDAD, ROLES
from app.services import ErrorNegocio
from app.services import auditoria
from app.utils.fechas import ahora_utc

MENSAJE_CREDENCIALES = "Usuario o contraseña incorrectos."
_PATRON_USUARIO = re.compile(r"^[a-z0-9._-]{3,50}$")
# hash para igualar el tiempo de respuesta cuando el usuario no existe
_HASH_FICTICIO = generate_password_hash("clave-ficticia-1")


# ------------------------------------------------------------------ utilidades
def normalizar_usuario(nombre: str) -> str:
    return (nombre or "").strip().lower()


def validar_clave(clave: str) -> None:
    clave = clave or ""
    if len(clave) < 8 or not re.search(r"[A-Za-z]", clave) or not re.search(r"\d", clave):
        raise ErrorNegocio("La contraseña debe tener al menos 8 caracteres, con letras y números.")


def generar_clave_temporal() -> str:
    letras = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz"
    numeros = "23456789"
    partes = [secrets.choice(letras) for _ in range(7)] + [secrets.choice(numeros) for _ in range(3)]
    secrets.SystemRandom().shuffle(partes)
    return "".join(partes)


def admins_activos(excluir_id: int | None = None) -> int:
    q = Usuario.query.filter_by(rol=ROL_ADMIN, activo=True)
    if excluir_id is not None:
        q = q.filter(Usuario.id != excluir_id)
    return q.count()


def _invalidar_sesiones(usuario: Usuario) -> None:
    usuario.version_sesion = (usuario.version_sesion or 0) + 1


# ------------------------------------------------------------------ ingreso
def autenticar(nombre_usuario: str, clave: str) -> Usuario:
    """Devuelve el usuario si las credenciales son válidas. Aplica el bloqueo por intentos."""
    cfg = current_app.config
    nombre = normalizar_usuario(nombre_usuario)
    usuario = Usuario.query.filter_by(nombre_usuario=nombre).first() if nombre else None
    ahora = ahora_utc()

    if usuario is None:
        check_password_hash(_HASH_FICTICIO, clave or "")
        auditoria.registrar("login_fallido", detalle={"usuario": nombre[:50]})
        db.session.commit()
        raise ErrorNegocio(MENSAJE_CREDENCIALES)

    if usuario.bloqueado_hasta and usuario.bloqueado_hasta > ahora:
        raise ErrorNegocio(
            f"Usuario bloqueado temporalmente por intentos fallidos. Intente en {cfg['MINUTOS_BLOQUEO']} minutos."
        )

    if not usuario.verificar_clave(clave) or not usuario.activo:
        usuario.intentos_fallidos = (usuario.intentos_fallidos or 0) + 1
        if usuario.intentos_fallidos >= cfg["MAX_INTENTOS"]:
            usuario.bloqueado_hasta = ahora + timedelta(minutes=cfg["MINUTOS_BLOQUEO"])
            usuario.intentos_fallidos = 0
            auditoria.registrar("usuario_bloqueado", usuario, "usuario", usuario.id)
        auditoria.registrar("login_fallido", usuario, "usuario", usuario.id)
        db.session.commit()
        raise ErrorNegocio(MENSAJE_CREDENCIALES)

    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.ultimo_ingreso = ahora
    auditoria.registrar("login", usuario, "usuario", usuario.id)
    db.session.commit()
    return usuario


def cambiar_clave_propia(usuario: Usuario, actual: str, nueva: str) -> None:
    if not usuario.verificar_clave(actual):
        raise ErrorNegocio("La contraseña actual no es correcta.")
    validar_clave(nueva)
    if actual == nueva:
        raise ErrorNegocio("La contraseña nueva debe ser distinta de la actual.")
    usuario.poner_clave(nueva)
    usuario.debe_cambiar_clave = False
    _invalidar_sesiones(usuario)  # cierra otras sesiones; quien llama vuelve a iniciar la actual
    auditoria.registrar("cambiar_clave", usuario, "usuario", usuario.id)
    db.session.commit()


# ------------------------------------------------------------------ administración
def _validar_rol_unidad(rol: str, unidad_id: int | None) -> Unidad | None:
    if rol not in ROLES:
        raise ErrorNegocio("Rol no válido.")
    unidad = db.session.get(Unidad, unidad_id) if unidad_id else None
    if unidad_id and unidad is None:
        raise ErrorNegocio("Unidad no válida.")
    if rol == ROL_UNIDAD and unidad is None:
        raise ErrorNegocio("Un usuario de unidad debe tener una unidad asignada.")
    return unidad


def _sincronizar_permiso_invitado(usuario: Usuario) -> None:
    if usuario.rol == ROL_INVITADO and usuario.permiso_invitado is None:
        usuario.permiso_invitado = PermisoInvitado()
    elif usuario.rol != ROL_INVITADO and usuario.permiso_invitado is not None:
        usuario.permiso_invitado = None


def crear_usuario(
    nombre_usuario: str, nombre_completo: str, rol: str, unidad_id: int | None, actor: Usuario | None,
    clave: str | None = None, debe_cambiar: bool = True,
) -> tuple[Usuario, str]:
    """Crea un usuario. Si no se da clave, genera una temporal. Devuelve (usuario, clave)."""
    nombre = normalizar_usuario(nombre_usuario)
    if not _PATRON_USUARIO.match(nombre):
        raise ErrorNegocio("El usuario debe tener de 3 a 50 caracteres: letras, números, punto, guion o guion bajo.")
    if Usuario.query.filter_by(nombre_usuario=nombre).first():
        raise ErrorNegocio(f"Ya existe el usuario «{nombre}».")
    nombre_completo = (nombre_completo or "").strip()
    if not nombre_completo:
        raise ErrorNegocio("Escriba el nombre completo.")
    _validar_rol_unidad(rol, unidad_id)
    clave = clave or generar_clave_temporal()
    validar_clave(clave)

    usuario = Usuario(
        nombre_usuario=nombre,
        nombre_completo=nombre_completo[:150],
        rol=rol,
        unidad_id=unidad_id or None,
        debe_cambiar_clave=debe_cambiar,
        activo=True,
        intentos_fallidos=0,
        version_sesion=1,
    )
    usuario.poner_clave(clave)
    _sincronizar_permiso_invitado(usuario)
    db.session.add(usuario)
    db.session.flush()
    auditoria.registrar("crear_usuario", actor, "usuario", usuario.id, {"usuario": nombre, "rol": rol})
    db.session.commit()
    return usuario, clave


def actualizar_usuario(usuario: Usuario, nombre_completo: str, rol: str, unidad_id: int | None, actor: Usuario) -> None:
    nombre_completo = (nombre_completo or "").strip()
    if not nombre_completo:
        raise ErrorNegocio("Escriba el nombre completo.")
    _validar_rol_unidad(rol, unidad_id)
    if usuario.es_admin and rol != ROL_ADMIN and usuario.activo and admins_activos(excluir_id=usuario.id) == 0:
        raise ErrorNegocio("Debe existir al menos un administrador activo.")
    cambio_acceso = usuario.rol != rol or (usuario.unidad_id or None) != (unidad_id or None)
    antes = {"rol": usuario.rol, "unidad_id": usuario.unidad_id}
    usuario.nombre_completo = nombre_completo[:150]
    usuario.rol = rol
    usuario.unidad_id = unidad_id or None
    _sincronizar_permiso_invitado(usuario)
    if cambio_acceso:
        _invalidar_sesiones(usuario)
    auditoria.registrar(
        "editar_usuario", actor, "usuario", usuario.id, {"antes": antes, "despues": {"rol": rol, "unidad_id": unidad_id}}
    )
    db.session.commit()


def restablecer_clave(usuario: Usuario, actor: Usuario) -> str:
    """Pone una clave temporal, obliga a cambiarla, desbloquea y cierra sus sesiones."""
    if usuario.id == actor.id:
        raise ErrorNegocio("Para cambiar su propia contraseña use «Cambiar contraseña».")
    clave = generar_clave_temporal()
    usuario.poner_clave(clave)
    usuario.debe_cambiar_clave = True
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    _invalidar_sesiones(usuario)
    auditoria.registrar("restablecer_clave", actor, "usuario", usuario.id)
    db.session.commit()
    return clave


def cambiar_estado(usuario: Usuario, activo: bool, actor: Usuario) -> None:
    if not activo:
        if usuario.id == actor.id:
            raise ErrorNegocio("No puede desactivar su propio usuario.")
        if usuario.es_admin and admins_activos(excluir_id=usuario.id) == 0:
            raise ErrorNegocio("Debe existir al menos un administrador activo.")
        _invalidar_sesiones(usuario)
    else:
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
    usuario.activo = activo
    auditoria.registrar("activar_usuario" if activo else "desactivar_usuario", actor, "usuario", usuario.id)
    db.session.commit()
