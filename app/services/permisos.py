"""Única puerta para consultar tareas según quién pregunta.

Ningún controlador debe hacer `Tarea.query` directamente: siempre `consulta_tareas(usuario)`.
"""
from sqlalchemy import false

from app.models import Tarea, Unidad, Usuario


def ids_unidades_visibles(usuario: Usuario) -> list[int] | None:
    """None = todas las unidades; lista (quizá vacía) = solo esas."""
    if not usuario or not usuario.is_authenticated or not usuario.activo:
        return []
    if usuario.ve_todo:
        return None
    if usuario.es_unidad:
        return [usuario.unidad_id] if usuario.unidad_id else []
    if usuario.es_invitado:
        p = usuario.permiso_invitado
        if p is None:
            return []
        if p.todas_unidades:
            return None
        return [u.id for u in p.unidades]
    return []


def consulta_tareas(usuario: Usuario):
    q = Tarea.query
    ids = ids_unidades_visibles(usuario)
    if ids is None:
        return q
    if not ids:
        return q.filter(false())
    return q.filter(Tarea.unidad_id.in_(ids))


def unidades_visibles(usuario: Usuario):
    q = Unidad.query.filter_by(activa=True).order_by(Unidad.orden, Unidad.sigla)
    ids = ids_unidades_visibles(usuario)
    if ids is None:
        return q.all()
    if not ids:
        return []
    return q.filter(Unidad.id.in_(ids)).all()


def puede_ver_unidad(usuario: Usuario, unidad_id: int) -> bool:
    ids = ids_unidades_visibles(usuario)
    return ids is None or unidad_id in ids


def puede_ver_tarea(usuario: Usuario, tarea: Tarea) -> bool:
    return tarea is not None and puede_ver_unidad(usuario, tarea.unidad_id)


def puede_editar_unidad(usuario: Usuario, unidad_id: int) -> bool:
    if not usuario or not usuario.is_authenticated or not usuario.activo or usuario.es_invitado:
        return False
    if usuario.ve_todo:
        return True
    return usuario.es_unidad and usuario.unidad_id == unidad_id


def puede_editar_tarea(usuario: Usuario, tarea: Tarea) -> bool:
    return tarea is not None and puede_editar_unidad(usuario, tarea.unidad_id)


def puede_reasignar(usuario: Usuario) -> bool:
    return bool(usuario and usuario.is_authenticated and usuario.activo and usuario.ve_todo)


def puede_ver_vista(usuario: Usuario, vista: str) -> bool:
    if not usuario or not usuario.is_authenticated or not usuario.activo:
        return False
    if usuario.es_invitado:
        return usuario.permiso_invitado is not None and usuario.permiso_invitado.permite_vista(vista)
    return True


def puede_ver_adjuntos(usuario: Usuario, tarea: Tarea) -> bool:
    if not puede_ver_tarea(usuario, tarea):
        return False
    if usuario.es_invitado:
        return bool(usuario.permiso_invitado and usuario.permiso_invitado.ver_adjuntos)
    return True
