"""Configuración de los usuarios invitados: qué unidades ven en el resumen ejecutivo."""
from app.extensions import db
from app.models import PermisoInvitado, Unidad, Usuario
from app.services import ErrorNegocio, auditoria


def configurar(usuario: Usuario, todas_unidades: bool, unidad_ids: list[int], actor: Usuario) -> None:
    if not actor.es_admin:
        raise ErrorNegocio("Solo Planificación configura a los invitados.")
    if not usuario.es_invitado:
        raise ErrorNegocio("El usuario no es invitado.")
    unidades = [] if todas_unidades else Unidad.query.filter(Unidad.id.in_(unidad_ids or [])).all()
    if not todas_unidades and len(unidades) != len(set(unidad_ids or [])):
        raise ErrorNegocio("Alguna unidad no es válida.")
    permiso = usuario.permiso_invitado or PermisoInvitado()
    usuario.permiso_invitado = permiso
    permiso.todas_unidades = bool(todas_unidades)
    permiso.unidades = unidades
    auditoria.registrar("configurar_invitado", actor, "usuario", usuario.id,
                        {"todas_unidades": permiso.todas_unidades, "unidades": sorted(u.sigla for u in unidades)})
    db.session.commit()
