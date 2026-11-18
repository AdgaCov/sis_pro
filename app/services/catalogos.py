"""Administración de catálogos (tipos, instancias, estados, prioridades, áreas).

Las tareas guardan el id del valor, así que renombrar un valor se refleja en todas sus tareas.
Los valores protegidos (Tarea interna, Concluido, Alta) los usa la lógica por nombre: no se renombran,
desactivan ni borran.
"""
from sqlalchemy import func

from app.extensions import db
from app.models import Catalogo, Tarea, Usuario
from app.models.catalogo import TIPOS_CATALOGO
from app.services import ErrorNegocio, auditoria

NOMBRES_TIPO = {
    "tipo": "Tipos de tarea",
    "estado": "Estados",
    "instancia": "Instancias del MRE",
    "prioridad": "Prioridades",
    "area": "Áreas funcionales",
}
COLUMNA = {"tipo": Tarea.tipo_id, "estado": Tarea.estado_id, "instancia": Tarea.instancia_id,
           "prioridad": Tarea.prioridad_id, "area": Tarea.area_id}


def _exigir_admin(actor: Usuario) -> None:
    if not actor.es_admin:
        raise ErrorNegocio("Solo Planificación administra los catálogos.")


def _validar_tipo(tipo: str) -> None:
    if tipo not in TIPOS_CATALOGO:
        raise ErrorNegocio("Catálogo no válido.")


def _limpiar(valor: str) -> str:
    valor = " ".join((valor or "").split())[:200]
    if not valor:
        raise ErrorNegocio("Escriba el valor.")
    return valor


def _duplicado(tipo: str, valor: str, excluir_id: int | None = None) -> bool:
    q = Catalogo.query.filter(Catalogo.tipo == tipo, func.lower(Catalogo.valor) == valor.lower())
    if excluir_id:
        q = q.filter(Catalogo.id != excluir_id)
    return db.session.query(q.exists()).scalar()


def valores(tipo: str) -> list[Catalogo]:
    _validar_tipo(tipo)
    return Catalogo.query.filter_by(tipo=tipo).order_by(Catalogo.orden, Catalogo.valor).all()


def usos(tipo: str) -> dict[int, int]:
    """Cuántas tareas usan cada valor del catálogo."""
    col = COLUMNA[tipo]
    return dict(db.session.query(col, func.count(Tarea.id)).filter(col.isnot(None)).group_by(col).all())


def agregar(actor: Usuario, tipo: str, valor: str) -> Catalogo:
    _exigir_admin(actor)
    _validar_tipo(tipo)
    valor = _limpiar(valor)
    if _duplicado(tipo, valor):
        raise ErrorNegocio(f"«{valor}» ya existe en {NOMBRES_TIPO[tipo].lower()}.")
    ultimo = db.session.query(func.max(Catalogo.orden)).filter(Catalogo.tipo == tipo).scalar() or 0
    c = Catalogo(tipo=tipo, valor=valor, orden=ultimo + 1, activo=True, protegido=False)
    db.session.add(c)
    db.session.flush()
    auditoria.registrar("agregar_catalogo", actor, "catalogo", c.id, {"tipo": tipo, "valor": valor})
    db.session.commit()
    return c


def renombrar(actor: Usuario, c: Catalogo, valor: str) -> None:
    _exigir_admin(actor)
    if c.protegido:
        raise ErrorNegocio(f"«{c.valor}» es un valor protegido: no se puede renombrar.")
    valor = _limpiar(valor)
    if valor == c.valor:
        return
    if _duplicado(c.tipo, valor, excluir_id=c.id):
        raise ErrorNegocio(f"«{valor}» ya existe en {NOMBRES_TIPO[c.tipo].lower()}.")
    auditoria.registrar("renombrar_catalogo", actor, "catalogo", c.id, {"antes": c.valor, "despues": valor})
    c.valor = valor
    db.session.commit()


def cambiar_estado(actor: Usuario, c: Catalogo, activo: bool) -> None:
    """Un valor inactivo deja de ofrecerse en los formularios; las tareas que lo tienen lo conservan."""
    _exigir_admin(actor)
    if c.protegido and not activo:
        raise ErrorNegocio(f"«{c.valor}» es un valor protegido: no se puede desactivar.")
    if not activo:
        restantes = Catalogo.query.filter(Catalogo.tipo == c.tipo, Catalogo.activo.is_(True),
                                          Catalogo.id != c.id).count()
        if restantes == 0 and c.tipo in ("tipo", "estado"):
            raise ErrorNegocio("Debe quedar al menos un valor activo en este catálogo.")
    c.activo = activo
    auditoria.registrar("activar_catalogo" if activo else "desactivar_catalogo", actor, "catalogo", c.id,
                        {"tipo": c.tipo, "valor": c.valor})
    db.session.commit()


def mover(actor: Usuario, c: Catalogo, direccion: int) -> None:
    """Sube (-1) o baja (+1) un valor en el orden de las listas."""
    _exigir_admin(actor)
    lista = valores(c.tipo)
    i = next(k for k, x in enumerate(lista) if x.id == c.id)
    j = i + (1 if direccion > 0 else -1)
    if not 0 <= j < len(lista):
        return
    lista[i], lista[j] = lista[j], lista[i]
    for orden, x in enumerate(lista, start=1):  # renumera para corregir órdenes repetidos
        x.orden = orden
    db.session.commit()


def eliminar(actor: Usuario, c: Catalogo) -> None:
    _exigir_admin(actor)
    if c.protegido:
        raise ErrorNegocio(f"«{c.valor}» es un valor protegido: no se puede eliminar.")
    en_uso = Tarea.query.filter(COLUMNA[c.tipo] == c.id).count()
    if en_uso:
        raise ErrorNegocio(f"«{c.valor}» lo usan {en_uso} tarea(s): desactívelo en lugar de eliminarlo.")
    auditoria.registrar("eliminar_catalogo", actor, "catalogo", c.id, {"tipo": c.tipo, "valor": c.valor})
    db.session.delete(c)
    db.session.commit()
