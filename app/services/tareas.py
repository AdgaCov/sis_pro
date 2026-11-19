"""Tareas: alta, edición, reasignación, subtareas y eliminación (papelera).

Los permisos se validan aquí también, aunque el controlador ya los haya revisado.
"""
from datetime import date

from app.extensions import db
from app.models import Adjunto, Auditoria, Cargo, Catalogo, Subtarea, Tarea, Unidad, Usuario
from app.models.catalogo import ESTADO_CONCLUIDO
from app.models.tarea import MAX_SUBTAREAS, NIVELES_RIESGO
from app.services import ErrorNegocio, auditoria, permisos
from app.utils.fechas import ahora_utc, hoy_local

# Campos de texto libre que vienen del formulario (nombre → largo máximo; None = Text)
CAMPOS_TEXTO = {
    "asunto": None, "gestion_requerida": None, "que_habilita": None, "riesgo_demora": None,
    "hoja_ruta": 100, "resultado": None, "medio_verificacion": None, "observaciones": None,
    "linea_solucion": None,
}
CAMPOS_FECHA = ("fecha_solicitud", "fecha_limite", "fecha_conclusion", "plazo_solucion")
CAMPOS_CATALOGO = {"tipo_id": "tipo", "estado_id": "estado", "instancia_id": "instancia",
                   "prioridad_id": "prioridad", "area_id": "area"}


# ------------------------------------------------------------------ utilidades
def _limpiar(valor, largo=None):
    texto = (valor or "").strip() if isinstance(valor, str) else valor
    if not texto:
        return None
    return texto[:largo] if largo else texto


def siguiente_codigo(unidad_id: int) -> str:
    """Reserva el siguiente código de la unidad (bloquea la fila hasta el commit)."""
    unidad = db.session.query(Unidad).filter_by(id=unidad_id).with_for_update().one()
    unidad.ultimo_correlativo = (unidad.ultimo_correlativo or 0) + 1
    while True:
        codigo = f"{unidad.sigla}-{unidad.ultimo_correlativo:03d}"
        if not Tarea.query.filter_by(codigo=codigo).first():
            return codigo
        unidad.ultimo_correlativo += 1


def _catalogo(tipo: str, catalogo_id, actual_id=None, obligatorio=False):
    if not catalogo_id:
        if obligatorio:
            raise ErrorNegocio(f"Seleccione {tipo}.")
        return None
    c = db.session.get(Catalogo, int(catalogo_id))
    if c is None or c.tipo != tipo or (not c.activo and c.id != actual_id):
        raise ErrorNegocio(f"Valor de {tipo} no válido.")
    return c


def _validar_responsable(usuario: Usuario, unidad_id: int, cargo_id, actual_id=None):
    if not cargo_id:
        return None
    cargo = db.session.get(Cargo, int(cargo_id))
    if cargo is None or (not cargo.activo and cargo.id != actual_id):
        raise ErrorNegocio("El responsable seleccionado no es válido.")
    if cargo.unidad_id != unidad_id and not usuario.ve_todo and cargo.id != actual_id:
        raise ErrorNegocio("Solo Planificación o la DGE pueden asignar un cargo de otra unidad.")
    return cargo


def _validar_habilita(usuario: Usuario, tarea: Tarea | None, unidad_id: int, habilita_id):
    if not habilita_id:
        return None
    destino = db.session.get(Tarea, int(habilita_id))
    if destino is None or not permisos.puede_ver_tarea(usuario, destino):
        raise ErrorNegocio("La tarea que habilita ya no existe.")
    if tarea is not None and destino.id == tarea.id:
        raise ErrorNegocio("Una tarea no puede habilitarse a sí misma.")
    if not usuario.ve_todo and destino.unidad_id != unidad_id:
        raise ErrorNegocio("La tarea que habilita debe ser de la misma unidad.")
    return destino


def normalizar_subtareas(filas) -> list[dict]:
    """Recibe dicts {texto, fecha, hecho}; descarta las vacías y valida el máximo."""
    salida = []
    for f in filas or []:
        texto = (f.get("texto") or "").strip()
        if not texto:
            continue
        salida.append({"texto": texto[:300], "fecha": f.get("fecha") or None, "hecho": bool(f.get("hecho"))})
    if len(salida) > MAX_SUBTAREAS:
        raise ErrorNegocio(f"Máximo {MAX_SUBTAREAS} subtareas por tarea.")
    return salida


def _poner_subtareas(tarea: Tarea, filas: list[dict]) -> None:
    tarea.subtareas.clear()
    db.session.flush()
    for i, f in enumerate(filas):
        tarea.subtareas.append(Subtarea(texto=f["texto"], fecha=f["fecha"], hecho=f["hecho"], orden=i))


def _marcar_actualizada(tarea: Tarea, usuario: Usuario) -> None:
    tarea.actualizado_en = ahora_utc()
    tarea.actualizado_por_id = usuario.id


# ------------------------------------------------------------------ guardar
def guardar_tarea(usuario: Usuario, datos: dict, tarea: Tarea | None = None) -> Tarea:
    """Crea (tarea=None) o actualiza una tarea. `datos` trae los campos del formulario ya convertidos.

    Si `datos['unidad_id']` difiere de la unidad actual, es una reasignación (solo admin/supervisor).
    """
    nueva = tarea is None
    if usuario.es_invitado:
        raise ErrorNegocio("Un invitado no puede modificar tareas.")

    # Unidad de destino
    if usuario.ve_todo:
        unidad_id = int(datos.get("unidad_id") or (tarea.unidad_id if tarea else 0) or 0)
    else:
        unidad_id = usuario.unidad_id
    unidad = db.session.get(Unidad, unidad_id) if unidad_id else None
    if unidad is None or (not unidad.activa and (nueva or unidad_id != tarea.unidad_id)):
        raise ErrorNegocio("Seleccione una unidad válida.")

    if nueva:
        if not permisos.puede_editar_unidad(usuario, unidad_id):
            raise ErrorNegocio("No puede crear tareas en esa unidad.")
    else:
        if not permisos.puede_editar_tarea(usuario, tarea):
            raise ErrorNegocio("No tiene permiso para editar esta tarea.")
        if unidad_id != tarea.unidad_id and not permisos.puede_reasignar(usuario):
            raise ErrorNegocio("Solo Planificación o la DGE pueden reasignar una tarea a otra unidad.")

    asunto = _limpiar(datos.get("asunto"))
    if not asunto:
        raise ErrorNegocio("La tarea / asunto es obligatoria.")

    actual = lambda campo: getattr(tarea, campo) if tarea else None  # noqa: E731
    cats = {
        campo: _catalogo(tipo, datos.get(campo), actual(campo), obligatorio=campo in ("tipo_id", "estado_id"))
        for campo, tipo in CAMPOS_CATALOGO.items()
    }
    responsable = _validar_responsable(usuario, unidad_id, datos.get("responsable_id"), actual("responsable_id"))
    habilita = _validar_habilita(usuario, tarea, unidad_id, datos.get("habilita_a_id"))
    subtareas = normalizar_subtareas(datos.get("subtareas"))

    nivel = datos.get("nivel_riesgo") or None
    if nivel and nivel not in NIVELES_RIESGO:
        raise ErrorNegocio("Nivel de riesgo no válido.")

    fechas = {c: datos.get(c) or None for c in CAMPOS_FECHA}
    for c, v in fechas.items():
        if v is not None and not isinstance(v, date):
            raise ErrorNegocio("Fecha no válida.")
    if fechas["fecha_solicitud"] and fechas["fecha_limite"] and fechas["fecha_limite"] < fechas["fecha_solicitud"]:
        raise ErrorNegocio("La fecha límite no puede ser anterior a la fecha de solicitud.")
    if cats["estado_id"].valor == ESTADO_CONCLUIDO and not fechas["fecha_conclusion"]:
        fechas["fecha_conclusion"] = hoy_local()

    codigo_anterior = None
    if nueva:
        tarea = Tarea(unidad_id=unidad_id, codigo=siguiente_codigo(unidad_id), creado_por_id=usuario.id,
                      creado_en=ahora_utc())
        db.session.add(tarea)
    elif unidad_id != tarea.unidad_id:
        codigo_anterior = tarea.codigo
        tarea.unidad_id = unidad_id
        tarea.codigo = siguiente_codigo(unidad_id)
        # habilita_a guarda el id, así que las tareas que apuntaban a esta siguen apuntando bien

    for campo, largo in CAMPOS_TEXTO.items():
        setattr(tarea, campo, _limpiar(datos.get(campo), largo))
    tarea.asunto = asunto
    for campo, c in cats.items():
        setattr(tarea, campo, c.id if c else None)
    for campo, v in fechas.items():
        setattr(tarea, campo, v)
    tarea.responsable_id = responsable.id if responsable else None
    tarea.habilita_a_id = habilita.id if habilita else None
    tarea.nivel_riesgo = nivel
    _marcar_actualizada(tarea, usuario)
    db.session.flush()
    _poner_subtareas(tarea, subtareas)

    if nueva:
        auditoria.registrar("crear_tarea", usuario, "tarea", tarea.id, {"codigo": tarea.codigo})
    else:
        auditoria.registrar("editar_tarea", usuario, "tarea", tarea.id, {"codigo": tarea.codigo})
    if codigo_anterior:
        auditoria.registrar("reasignar_tarea", usuario, "tarea", tarea.id,
                            {"de": codigo_anterior, "a": tarea.codigo})
    db.session.commit()
    return tarea


def marcar_subtarea(usuario: Usuario, tarea: Tarea, subtarea_id: int, hecho: bool) -> None:
    if not permisos.puede_editar_tarea(usuario, tarea):
        raise ErrorNegocio("No tiene permiso para editar esta tarea.")
    sub = next((s for s in tarea.subtareas if s.id == subtarea_id), None)
    if sub is None:
        raise ErrorNegocio("La subtarea no existe.")
    sub.hecho = hecho
    _marcar_actualizada(tarea, usuario)
    auditoria.registrar("marcar_subtarea", usuario, "tarea", tarea.id,
                        {"codigo": tarea.codigo, "subtarea": sub.texto[:100], "hecho": hecho})
    db.session.commit()


# ------------------------------------------------------------------ eliminar
def _iso(v):
    return v.isoformat() if v else None


def copia_para_papelera(t: Tarea) -> dict:
    return {
        "codigo": t.codigo,
        "unidad": t.unidad.sigla,
        "tipo": t.tipo.valor if t.tipo else None,
        "estado": t.estado.valor if t.estado else None,
        "instancia": t.instancia.valor if t.instancia else None,
        "prioridad": t.prioridad.valor if t.prioridad else None,
        "area": t.area.valor if t.area else None,
        "responsable": t.responsable.nombre if t.responsable else None,
        "persona": t.responsable.persona if t.responsable else None,
        "habilita_a": t.habilita_a.codigo if t.habilita_a else None,
        **{c: getattr(t, c) for c in CAMPOS_TEXTO},
        **{c: _iso(getattr(t, c)) for c in CAMPOS_FECHA},
        "nivel_riesgo": t.nivel_riesgo,
        "agenda_id": t.agenda_id,
        "creado_en": _iso(t.creado_en),
        "actualizado_en": _iso(t.actualizado_en),
        "subtareas": [{"texto": s.texto, "fecha": _iso(s.fecha), "hecho": s.hecho} for s in t.subtareas],
        "adjuntos": [{"nombre": a.nombre_original, "ruta": a.ruta_relativa, "tamano": a.tamano}
                     for a in t.adjuntos],
    }


def eliminar_tarea(usuario: Usuario, tarea: Tarea) -> None:
    """Copia la tarea a la papelera (auditoría), limpia las referencias y la borra.

    Los archivos adjuntos quedan en disco; su ruta se guarda en la copia de la papelera.
    """
    if not permisos.puede_editar_tarea(usuario, tarea):
        raise ErrorNegocio("No tiene permiso para eliminar esta tarea.")
    copia = copia_para_papelera(tarea)
    Tarea.query.filter_by(habilita_a_id=tarea.id).update({"habilita_a_id": None})
    auditoria.registrar("eliminar_tarea", usuario, "tarea", tarea.id, copia)
    db.session.delete(tarea)
    db.session.commit()


def papelera(limite: int = 200):
    return (Auditoria.query.filter_by(accion="eliminar_tarea")
            .order_by(Auditoria.fecha.desc()).limit(limite).all())


# ------------------------------------------------------------------ consultas
def adjunto_de(tarea: Tarea, adjunto_id: int) -> Adjunto | None:
    return next((a for a in tarea.adjuntos if a.id == adjunto_id), None)


def catalogos_para_formulario(tarea: Tarea | None = None) -> dict:
    """Valores activos de cada catálogo, más el que ya tiene la tarea aunque esté inactivo."""
    salida = {}
    for campo, tipo in CAMPOS_CATALOGO.items():
        actual = getattr(tarea, campo) if tarea else None
        q = Catalogo.query.filter(Catalogo.tipo == tipo)
        q = q.filter(db.or_(Catalogo.activo.is_(True), Catalogo.id == actual)) if actual else q.filter(
            Catalogo.activo.is_(True))
        salida[tipo] = q.order_by(Catalogo.orden, Catalogo.valor).all()
    return salida


def tareas_habilitables(usuario: Usuario, tarea: Tarea | None, unidad_id: int | None):
    """Tareas a las que puede apuntar `habilita_a`: abiertas (más la actual), de la misma unidad salvo admin/DGE."""
    q = permisos.consulta_tareas(usuario)
    if not usuario.ve_todo:
        q = q.filter(Tarea.unidad_id == unidad_id)
    if tarea is not None:
        q = q.filter(Tarea.id != tarea.id)
    concluido = Catalogo.query.filter_by(tipo="estado", valor=ESTADO_CONCLUIDO).first()
    if concluido:
        actual = tarea.habilita_a_id if tarea else None
        q = q.filter(db.or_(Tarea.estado_id != concluido.id, Tarea.id == actual))
    return q.order_by(Tarea.codigo).all()


def estado_por_nombre(valor: str) -> Catalogo | None:
    return Catalogo.query.filter_by(tipo="estado", valor=valor).first()
