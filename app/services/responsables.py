"""Responsables: cargos de cada unidad, con una persona designada opcional."""
from sqlalchemy import func

from app.extensions import db
from app.models import Cargo, Catalogo, Tarea, Unidad, Usuario
from app.models.catalogo import ESTADO_CONCLUIDO
from app.services import ErrorNegocio, auditoria, permisos


def _exigir_edicion(usuario: Usuario, unidad_id: int) -> None:
    if not permisos.puede_editar_unidad(usuario, unidad_id):
        raise ErrorNegocio("No puede modificar los cargos de esa unidad.")


def _existe(unidad_id: int, nombre: str, excluir_id: int | None = None) -> bool:
    q = Cargo.query.filter(Cargo.unidad_id == unidad_id, func.lower(Cargo.nombre) == nombre.lower())
    if excluir_id:
        q = q.filter(Cargo.id != excluir_id)
    return db.session.query(q.exists()).scalar()


def crear_cargo(usuario: Usuario, unidad_id: int, nombre: str, persona: str | None) -> Cargo:
    _exigir_edicion(usuario, unidad_id)
    if db.session.get(Unidad, unidad_id) is None:
        raise ErrorNegocio("Unidad no válida.")
    nombre = (nombre or "").strip()[:150]
    if not nombre:
        raise ErrorNegocio("Escriba el cargo del responsable.")
    if _existe(unidad_id, nombre):
        raise ErrorNegocio(f"El cargo «{nombre}» ya existe en esa unidad.")
    cargo = Cargo(unidad_id=unidad_id, nombre=nombre, persona=(persona or "").strip()[:150] or None, activo=True)
    db.session.add(cargo)
    db.session.flush()
    auditoria.registrar("crear_cargo", usuario, "cargo", cargo.id, {"cargo": nombre, "unidad_id": unidad_id})
    db.session.commit()
    return cargo


def poner_persona(usuario: Usuario, cargo: Cargo, persona: str | None) -> None:
    _exigir_edicion(usuario, cargo.unidad_id)
    antes = cargo.persona
    cargo.persona = (persona or "").strip()[:150] or None
    auditoria.registrar("persona_cargo", usuario, "cargo", cargo.id, {"antes": antes, "despues": cargo.persona})
    db.session.commit()


def cambiar_estado(usuario: Usuario, cargo: Cargo, activo: bool) -> None:
    _exigir_edicion(usuario, cargo.unidad_id)
    if cargo.es_apoyo and not activo:
        raise ErrorNegocio("El cargo «Apoyo» no se puede desactivar.")
    cargo.activo = activo
    auditoria.registrar("activar_cargo" if activo else "desactivar_cargo", usuario, "cargo", cargo.id)
    db.session.commit()


def mover_cargo(usuario: Usuario, cargo: Cargo, unidad_destino_id: int) -> None:
    """Solo el admin. Las tareas que tenían este cargo lo conservan."""
    if not usuario.es_admin:
        raise ErrorNegocio("Solo Planificación puede mover cargos entre unidades.")
    if cargo.es_apoyo:
        raise ErrorNegocio("El cargo «Apoyo» no se puede mover.")
    destino = db.session.get(Unidad, unidad_destino_id)
    if destino is None:
        raise ErrorNegocio("Unidad no válida.")
    if destino.id == cargo.unidad_id:
        return
    if _existe(destino.id, cargo.nombre, excluir_id=cargo.id):
        raise ErrorNegocio(f"Ese cargo ya existe en {destino.sigla}.")
    origen = cargo.unidad.sigla
    cargo.unidad_id = destino.id
    auditoria.registrar("mover_cargo", usuario, "cargo", cargo.id, {"de": origen, "a": destino.sigla})
    db.session.commit()


def tareas_abiertas_por_cargo(ids_cargos: list[int]) -> dict[int, int]:
    if not ids_cargos:
        return {}
    concluido = Catalogo.query.filter_by(tipo="estado", valor=ESTADO_CONCLUIDO).first()
    q = (db.session.query(Tarea.responsable_id, func.count(Tarea.id))
         .filter(Tarea.responsable_id.in_(ids_cargos)))
    if concluido:
        q = q.filter(Tarea.estado_id != concluido.id)
    return dict(q.group_by(Tarea.responsable_id).all())


def cargos_asignables(usuario: Usuario, unidad_id: int | None, actual_id: int | None = None):
    """Cargos que el usuario puede poner como responsable. Admin/supervisor: de todas las unidades."""
    q = Cargo.query.join(Unidad).filter(Cargo.activo.is_(True))
    if not usuario.ve_todo:
        q = q.filter(Cargo.unidad_id == unidad_id)
    cargos = q.order_by(Unidad.orden, Unidad.sigla, Cargo.es_apoyo, Cargo.nombre).all()
    if actual_id and all(c.id != actual_id for c in cargos):
        actual = db.session.get(Cargo, actual_id)
        if actual:
            cargos.append(actual)
    return cargos
