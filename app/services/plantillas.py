"""Plantillas Word/Excel con marcadores: validación al subir, datos y generación.

- Word: docxtpl con un entorno Jinja *sandbox*. Listas: {% for t in tareas %}…{% endfor %}
  (en tablas, {%tr for t in tareas %} repite la fila).
- Excel: openpyxl. Las celdas con {{ … }} se reemplazan; una fila con marcadores {{ t.xxx }} se
  repite por cada tarea, conservando el formato.
"""
import io
import re
import uuid
import zipfile
from copy import copy
from pathlib import Path

from docx.shared import Mm
from docxtpl import DocxTemplate, InlineImage
from flask import current_app
from jinja2 import ChainableUndefined, TemplateError, nodes
from jinja2.sandbox import SandboxedEnvironment
from openpyxl import load_workbook

from app.extensions import db
from app.models import Plantilla, Usuario
from app.models.plantilla import ALCANCES
from app.services import ErrorNegocio, alertas, auditoria
from app.services import imagenes as imagenes_png
from app.utils.fechas import ahora_utc, formato_fecha, formato_fecha_hora

# ------------------------------------------------------------------ catálogo de marcadores
TODOS = ("tarea", "listado", "informe", "resumen", "agenda", "graficos")

# (título, alcances donde sirve, {marcador: descripción}). La página Admin › Plantillas › Marcadores lo muestra así.
GRUPOS_MARCADORES = [
    ("Generales", TODOS, {
        "unidad.nombre": "Nombre de la unidad (o «Todas las unidades»)",
        "unidad.sigla": "Sigla de la unidad",
        "generado.fecha": "Fecha y hora de generación",
        "generado.por": "Usuario que generó el documento",
        "generado.filtros": "Filtros aplicados (listado, resumen, agenda)",
        "resumen.total": "Total de tareas del documento",
        "resumen.pendientes": "Tareas abiertas",
        "resumen.vencidas": "Abiertas vencidas",
        "resumen.por_vencer": "Abiertas por vencer",
        "resumen.criticas": "Tareas críticas",
        "resumen.concluidas": "Concluidas",
        "resumen.sin_solucion": "Críticas sin línea de solución",
    }),
    ("Una tarea (ficha) · en listas: t.xxx", TODOS, {
        "tarea.codigo": "Código (UAF-001)",
        "tarea.unidad": "Sigla de la unidad de la tarea",
        "tarea.unidad_nombre": "Nombre de la unidad de la tarea",
        "tarea.tipo": "Tipo",
        "tarea.area": "Área funcional",
        "tarea.instancia": "Instancia del MRE",
        "tarea.asunto": "Tarea / asunto",
        "tarea.gestion": "Gestión requerida / acción",
        "tarea.que_habilita": "¿Qué habilita?",
        "tarea.habilita_a": "Código de la tarea que habilita",
        "tarea.riesgo_demora": "Riesgo por demora",
        "tarea.responsable": "Responsable (cargo)",
        "tarea.persona": "Persona designada en el cargo",
        "tarea.hoja_ruta": "Hoja de ruta",
        "tarea.fecha_solicitud": "Fecha de solicitud / inicio (dd/mm/aaaa)",
        "tarea.fecha_limite": "Fecha límite (dd/mm/aaaa)",
        "tarea.fecha_conclusion": "Fecha de conclusión (dd/mm/aaaa)",
        "tarea.estado": "Estado",
        "tarea.prioridad": "Prioridad",
        "tarea.alerta": "Alerta calculada (VENCIDO, CRÍTICO…)",
        "tarea.dias": "Días desde la solicitud",
        "tarea.faltan": "Días que faltan para la fecha límite (negativo = vencida)",
        "tarea.nivel_riesgo": "Nivel de riesgo",
        "tarea.solucion": "Línea de solución",
        "tarea.plazo_solucion": "Plazo de la solución (dd/mm/aaaa)",
        "tarea.resultado": "Resultado obtenido",
        "tarea.medio_verificacion": "Descripción del respaldo",
        "tarea.observaciones": "Observaciones",
        "tarea.actualizado": "Última actualización (dd/mm/aaaa hh:mm)",
        "tarea.subtareas": "Lista de subtareas (usar con for)",
        "subtarea.texto": "Texto del paso",
        "subtarea.fecha": "Fecha del paso",
        "subtarea.hecho": "Sí / No",
        "tareas": "Lista de tareas del documento (usar con for; en Excel, fila con t.xxx)",
    }),
    ("Resumen ejecutivo", ("resumen",), {
        "indicadores.total_mre": "Total de gestiones con el MRE",
        "indicadores.pendientes": "Pendientes",
        "indicadores.vencidas": "Vencidas",
        "indicadores.sin_respuesta": "Sin respuesta del MRE",
        "indicadores.alta_prioridad": "Alta prioridad pendiente",
        "por_unidad": "Gestiones por unidad (usar con for; en Excel, fila con u.xxx)",
        "fila_unidad.sigla": "Sigla de la unidad",
        "fila_unidad.nombre": "Nombre de la unidad",
        "fila_unidad.total": "Total de gestiones",
        "fila_unidad.pendientes": "Pendientes",
        "fila_unidad.vencidas": "Vencidas",
        "fila_unidad.alta": "Alta prioridad pendiente",
        "fila_unidad.sin_respuesta": "Sin respuesta del MRE",
        "fila_unidad.concluidas": "Concluidas",
        "por_instancia": "Pendientes por instancia del MRE (for; en Excel, fila con i.xxx)",
        "fila_instancia.nombre": "Instancia",
        "fila_instancia.pendientes": "Pendientes",
        "por_tipo": "Pendientes por tipo (for; en Excel, fila con p.xxx)",
        "fila_tipo.nombre": "Tipo",
        "fila_tipo.pendientes": "Pendientes",
    }),
    ("Agenda Despacho", ("agenda",), {
        "mes.nombre": "Mes de la agenda (Noviembre 2026)",
        "mes.desde": "Primer día del mes (dd/mm/aaaa)",
        "mes.hasta": "Último día del mes (dd/mm/aaaa)",
        "indicadores.fechas_limite": "Fechas límite del mes",
        "indicadores.vencidas": "Fechas límite vencidas",
        "indicadores.recordatorios_pendientes": "Recordatorios pendientes",
        "indicadores.recordatorios_vencidos": "Recordatorios vencidos",
        "indicadores.bloqueadas": "Tareas bloqueadas (observado / devuelto)",
        "eventos": "Eventos del mes, por fecha (usar con for; en Excel, fila con e.xxx)",
        "evento.fecha": "Fecha (dd/mm/aaaa)",
        "evento.dia": "Día de la semana",
        "evento.tipo": "Fecha límite / Recordatorio",
        "evento.codigo": "Código de la tarea",
        "evento.unidad": "Sigla de la unidad",
        "evento.texto": "Asunto (fecha límite) o texto del recordatorio",
        "evento.asunto": "Asunto de la tarea",
        "evento.responsable": "Responsable (cargo)",
        "evento.persona": "Persona designada",
        "evento.estado": "Estado de la tarea",
        "evento.estado_agenda": "Pendiente / En gestión / Bloqueada / Concluida",
        "evento.alerta": "Alerta",
        "evento.hecho": "Sí / No (recordatorios)",
    }),
    ("Tablero con gráficos", ("graficos",), {
        "indicadores.pendientes": "Pendientes",
        "indicadores.vencidas": "Vencidas",
        "indicadores.por_vencer": "Por vencer",
        "indicadores.sin_respuesta": "Sin respuesta del MRE",
        "indicadores.concluidas_mes": "Concluidas este mes",
        "indicadores.variacion": "% de variación de concluidas contra el mes anterior",
        "cumplimiento.porcentaje": "% de concluidas a tiempo",
        "cumplimiento.base": "Concluidas con fecha límite (base del %)",
        "cumplimiento.meta": "Meta de cumplimiento (%)",
        "por_unidad": "Pendientes por unidad y alerta (for; en Excel, fila con u.xxx)",
        "fila_unidad.sigla": "Sigla de la unidad",
        "fila_unidad.nombre": "Nombre de la unidad",
        "fila_unidad.pendientes": "Pendientes",
        "fila_unidad.vencido": "Vencidas",
        "fila_unidad.critico": "Críticas",
        "fila_unidad.por_vencer": "Por vencer",
        "fila_unidad.seguimiento": "En seguimiento",
        "fila_unidad.en_curso": "En curso",
        "fila_unidad.sin_fecha": "Sin fecha",
        "fila_unidad.cumplimiento": "% concluidas a tiempo de la unidad",
        "mensual": "Creadas y concluidas por mes, 12 meses (for; en Excel, fila con m.xxx)",
        "fila_mes.mes": "Mes (nov 26)",
        "fila_mes.creadas": "Tareas creadas",
        "fila_mes.concluidas": "Tareas concluidas",
        "embudo": "Abiertas por estado (for; en Excel, fila con f.xxx)",
        "fila_estado.estado": "Estado",
        "fila_estado.tareas": "Tareas abiertas en ese estado",
        "por_instancia": "Instancias del MRE con más pendientes (for; en Excel, fila con i.xxx)",
        "fila_instancia.nombre": "Instancia",
        "fila_instancia.pendientes": "Pendientes",
        "imagen.barras": "Imagen: pendientes por unidad (solo Word)",
        "imagen.cumplimiento": "Imagen: velocímetro de cumplimiento (solo Word)",
        "imagen.mensual": "Imagen: creadas contra concluidas (solo Word)",
        "imagen.embudo": "Imagen: embudo de estados (solo Word)",
    }),
]
MARCADORES = {m: d for _, _, grupo in GRUPOS_MARCADORES for m, d in grupo.items()}

# Qué es cada elemento de una lista recorrida con for
LISTAS = {"tareas": "tarea", "tarea.subtareas": "subtarea", "por_unidad": "fila_unidad",
          "por_instancia": "fila_instancia", "por_tipo": "fila_tipo", "eventos": "evento", "mensual": "fila_mes",
          "embudo": "fila_estado"}
# Excel: una fila con marcadores <letra>.xxx se repite una vez por elemento de la lista
FILAS_EXCEL = {"t": "tareas", "u": "por_unidad", "i": "por_instancia", "p": "por_tipo", "e": "eventos",
               "m": "mensual", "f": "embudo"}
ALIAS_EXCEL = {letra: LISTAS[lista] for letra, lista in FILAS_EXCEL.items()}
CAMPOS_TAREA = [m.split(".", 1)[1] for m in MARCADORES if m.startswith("tarea.")]
ANCHO_IMAGEN_MM = {"barras": 160, "cumplimiento": 80, "mensual": 160, "embudo": 160}

EXTENSIONES = {"docx", "xlsx"}
_FILA_REPETIBLE = re.compile(r"\{\{[^}]*?\b([" + "".join(FILAS_EXCEL) + r"])\.")
_SOLO_MARCADOR = re.compile(r"^\s*\{\{\s*(.+?)\s*\}\}\s*$", re.S)


def entorno(autoescape: bool = False) -> SandboxedEnvironment:
    return SandboxedEnvironment(undefined=ChainableUndefined, autoescape=autoescape)


# ------------------------------------------------------------------ validación de marcadores
def _ruta(nodo, alias: dict) -> str | None:
    partes = []
    while isinstance(nodo, (nodes.Getattr, nodes.Getitem)):
        if isinstance(nodo, nodes.Getattr):
            partes.append(nodo.attr)
        elif isinstance(nodo.arg, nodes.Const) and isinstance(nodo.arg.value, str):
            partes.append(nodo.arg.value)
        else:
            return None
        nodo = nodo.node
    if not isinstance(nodo, nodes.Name):
        return None
    return ".".join([alias.get(nodo.name, nodo.name)] + partes[::-1])


def _recorrer(nodo, alias: dict, usados: set) -> None:
    if isinstance(nodo, nodes.For):
        lista = _ruta(nodo.iter, alias)
        if lista:
            usados.add(lista)
        interno = dict(alias)
        if isinstance(nodo.target, nodes.Name) and lista:
            interno[nodo.target.name] = LISTAS.get(lista, lista + "[]")
        for hijo in [*nodo.body, *nodo.else_] + ([nodo.test] if nodo.test else []):
            _recorrer(hijo, interno, usados)
        return
    if isinstance(nodo, nodes.Name) and nodo.ctx != "load":
        return
    if isinstance(nodo, (nodes.Name, nodes.Getattr, nodes.Getitem)):
        ruta = _ruta(nodo, alias)
        if ruta is not None:
            usados.add(ruta)
            return
    for hijo in nodo.iter_child_nodes():
        _recorrer(hijo, alias, usados)


def marcadores_en(texto: str, alias: dict | None = None) -> set[str]:
    """Rutas de marcadores usadas en un texto Jinja. Lanza ErrorNegocio si la sintaxis es inválida."""
    try:
        arbol = entorno().parse(texto)
    except TemplateError as e:
        linea = f" (línea {e.lineno})" if getattr(e, "lineno", None) else ""
        raise ErrorNegocio(f"Error de sintaxis en los marcadores{linea}: {e.message}") from e
    usados: set[str] = set()
    _recorrer(arbol, dict(alias or {}), usados)
    return usados


def es_conocido(ruta: str) -> bool:
    return ruta in MARCADORES or ruta.split(".")[0] == "loop"


def _textos_docx(datos: bytes) -> list[str]:
    try:
        tpl = DocxTemplate(io.BytesIO(datos))
        tpl.init_docx()
        textos = [tpl.patch_xml(tpl.get_xml())]
        for uri in (tpl.HEADER_URI, tpl.FOOTER_URI):
            textos += [tpl.patch_xml(tpl.get_part_xml(p)) for _, p in tpl.get_headers_footers(uri)]
        return textos
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        raise ErrorNegocio("El archivo no es un documento Word (.docx) válido.") from e


def _celdas_xlsx(datos: bytes) -> list[str]:
    try:
        wb = load_workbook(io.BytesIO(datos))
    except Exception as e:  # openpyxl lanza varios tipos según el daño del archivo
        raise ErrorNegocio("El archivo no es un libro de Excel (.xlsx) válido.") from e
    return [c.value for ws in wb.worksheets for fila in ws.iter_rows() for c in fila
            if isinstance(c.value, str) and ("{{" in c.value or "{%" in c.value)]


def analizar(datos: bytes, formato: str) -> list[str]:
    """Devuelve los marcadores desconocidos (ordenados). Lanza ErrorNegocio si el archivo o la sintaxis fallan."""
    usados: set[str] = set()
    if formato == "docx":
        for texto in _textos_docx(datos):
            usados |= marcadores_en(texto)
    else:
        for texto in _celdas_xlsx(datos):
            usados |= marcadores_en(texto, ALIAS_EXCEL)
    return sorted(r for r in usados if not es_conocido(r))


# ------------------------------------------------------------------ administración
def _directorio() -> Path:
    return current_app.config["STORAGE_DIR"] / "plantillas"


def ruta_archivo(p: Plantilla) -> Path:
    raiz = _directorio().resolve()
    ruta = (raiz / p.archivo).resolve()
    if ruta.parent != raiz:
        raise ErrorNegocio("Ruta de plantilla no válida.")
    return ruta


def _leer_subida(archivo) -> tuple[bytes, str, str]:
    if archivo is None or not getattr(archivo, "filename", ""):
        raise ErrorNegocio("Seleccione un archivo .docx o .xlsx.")
    nombre = Path(archivo.filename.replace("\\", "/")).name.strip()[:255]
    ext = Path(nombre).suffix.lower().lstrip(".")
    if ext not in EXTENSIONES:
        raise ErrorNegocio("Solo se aceptan plantillas Word (.docx) o Excel (.xlsx).")
    max_bytes = current_app.config["MAX_MB_ADJUNTO"] * 1024 * 1024
    datos = archivo.stream.read(max_bytes + 1)
    if not datos:
        raise ErrorNegocio("El archivo está vacío.")
    if len(datos) > max_bytes:
        raise ErrorNegocio(f"El archivo supera {current_app.config['MAX_MB_ADJUNTO']} MB.")
    return datos, ext, nombre


def guardar(actor: Usuario, nombre: str, descripcion: str | None, alcance: str, archivo,
            plantilla: Plantilla | None = None) -> Plantilla:
    """Crea una plantilla o la actualiza (el archivo es opcional al editar)."""
    if not actor.es_admin:
        raise ErrorNegocio("Solo Planificación administra las plantillas.")
    nombre = (nombre or "").strip()[:150]
    if not nombre:
        raise ErrorNegocio("Escriba un nombre para la plantilla.")
    if alcance not in ALCANCES:
        raise ErrorNegocio("Alcance no válido.")
    hay_archivo = archivo is not None and getattr(archivo, "filename", "")
    if plantilla is None and not hay_archivo:
        raise ErrorNegocio("Seleccione un archivo .docx o .xlsx.")

    nuevo_archivo = None
    if hay_archivo:
        datos, ext, nombre_original = _leer_subida(archivo)
        desconocidos = analizar(datos, ext)
        nuevo_archivo = f"{uuid.uuid4().hex}.{ext}"
        _directorio().mkdir(parents=True, exist_ok=True)
        (_directorio() / nuevo_archivo).write_bytes(datos)

    anterior = None
    if plantilla is None:
        plantilla = Plantilla(subido_por_id=actor.id, subido_en=ahora_utc(), activa=True)
        db.session.add(plantilla)
    if nuevo_archivo:
        anterior = plantilla.archivo
        plantilla.archivo = nuevo_archivo
        plantilla.formato = ext
        plantilla.nombre_original = nombre_original
        plantilla.marcadores_desconocidos = desconocidos
        plantilla.subido_por_id = actor.id
    plantilla.nombre = nombre
    plantilla.descripcion = (descripcion or "").strip() or None
    plantilla.alcance = alcance
    plantilla.actualizado_en = ahora_utc()
    db.session.flush()
    auditoria.registrar("guardar_plantilla", actor, "plantilla", plantilla.id,
                        {"nombre": nombre, "alcance": alcance, "archivo": plantilla.nombre_original})
    try:
        db.session.commit()
    except Exception:
        if nuevo_archivo:
            (_directorio() / nuevo_archivo).unlink(missing_ok=True)
        raise
    if anterior:
        (_directorio() / anterior).unlink(missing_ok=True)
    return plantilla


def cambiar_estado(actor: Usuario, p: Plantilla, activa: bool) -> None:
    if not actor.es_admin:
        raise ErrorNegocio("Solo Planificación administra las plantillas.")
    p.activa = activa
    auditoria.registrar("activar_plantilla" if activa else "desactivar_plantilla", actor, "plantilla", p.id)
    db.session.commit()


def eliminar(actor: Usuario, p: Plantilla) -> None:
    if not actor.es_admin:
        raise ErrorNegocio("Solo Planificación administra las plantillas.")
    ruta = ruta_archivo(p)
    auditoria.registrar("eliminar_plantilla", actor, "plantilla", p.id, {"nombre": p.nombre})
    db.session.delete(p)
    db.session.commit()
    ruta.unlink(missing_ok=True)


def vigente_para(alcance: str) -> Plantilla | None:
    """La plantilla con la que «Descargar PDF» arma el documento de una vista: la activa editada más
    recientemente. None si el admin todavía no subió ninguna."""
    return (Plantilla.query.filter_by(alcance=alcance, activa=True)
            .order_by(Plantilla.actualizado_en.desc(), Plantilla.id.desc()).first())


# ------------------------------------------------------------------ datos para los marcadores
def _txt(v) -> str:
    return "" if v is None else str(v)


def datos_tarea(i: alertas.InfoTarea) -> dict:
    t = i.t
    return {
        "codigo": t.codigo,
        "unidad": t.unidad.sigla,
        "unidad_nombre": t.unidad.nombre,
        "tipo": t.tipo.valor if t.tipo else "",
        "area": t.area.valor if t.area else "",
        "instancia": t.instancia.valor if t.instancia else "",
        "asunto": t.asunto,
        "gestion": _txt(t.gestion_requerida),
        "que_habilita": _txt(t.que_habilita),
        "habilita_a": t.habilita_a.codigo if t.habilita_a else "",
        "riesgo_demora": _txt(t.riesgo_demora),
        "responsable": t.responsable.nombre if t.responsable else "",
        "persona": _txt(t.responsable.persona) if t.responsable else "",
        "hoja_ruta": _txt(t.hoja_ruta),
        "fecha_solicitud": formato_fecha(t.fecha_solicitud),
        "fecha_limite": formato_fecha(t.fecha_limite),
        "fecha_conclusion": formato_fecha(t.fecha_conclusion),
        "estado": t.estado.valor if t.estado else "",
        "prioridad": t.prioridad.valor if t.prioridad else "",
        "alerta": i.alerta,
        "dias": "" if i.dias is None else i.dias,
        "faltan": "" if i.faltan is None or i.concluida else i.faltan,
        "nivel_riesgo": _txt(t.nivel_riesgo),
        "solucion": _txt(t.linea_solucion),
        "plazo_solucion": formato_fecha(t.plazo_solucion),
        "resultado": _txt(t.resultado),
        "medio_verificacion": _txt(t.medio_verificacion),
        "observaciones": _txt(t.observaciones),
        "actualizado": formato_fecha_hora(t.actualizado_en),
        "subtareas": [{"texto": s.texto, "fecha": formato_fecha(s.fecha), "hecho": "Sí" if s.hecho else "No"}
                      for s in t.subtareas],
    }


def _resumen(infos) -> dict:
    abiertas = [i for i in infos if not i.concluida]
    return {
        "total": len(infos),
        "pendientes": len(abiertas),
        "vencidas": sum(1 for i in abiertas if i.alerta == alertas.VENCIDO),
        "por_vencer": sum(1 for i in abiertas if i.alerta == alertas.POR_VENCER),
        "criticas": sum(1 for i in abiertas if i.critica),
        "sin_solucion": sum(1 for i in abiertas if i.sin_solucion),
        "concluidas": len(infos) - len(abiertas),
    }


def contexto(infos: list, usuario: Usuario, unidad=None, filtros: str = "") -> dict:
    """Datos para cualquier alcance. `tarea` es la primera de la lista (útil en fichas)."""
    tareas = [datos_tarea(i) for i in infos]
    return {
        "unidad": {"nombre": unidad.nombre, "sigla": unidad.sigla} if unidad else
                  {"nombre": "Todas las unidades", "sigla": ""},
        "tarea": tareas[0] if tareas else {},
        "tareas": tareas,
        "resumen": _resumen(infos),
        "generado": {"fecha": formato_fecha_hora(ahora_utc()), "por": usuario.nombre_usuario, "filtros": filtros},
    }


def contexto_ejemplo(usuario: Usuario) -> dict:
    """Datos ficticios para el botón «Probar»."""
    base = {c: f"[{c}]" for c in CAMPOS_TAREA}
    ejemplos = []
    for n, (alerta, fecha) in enumerate([("VENCIDO", "10/11/2026"), ("POR VENCER", "20/11/2026"),
                                         ("EN CURSO", "15/12/2026")], start=1):
        ejemplos.append({**base, "codigo": f"UAF-00{n}", "unidad": "UAF",
                         "unidad_nombre": "UAF - Unidad Administrativa Financiera", "tipo": "Solicitud al MRE",
                         "asunto": f"Tarea de ejemplo {n}", "estado": "En proceso", "prioridad": "Alta",
                         "alerta": alerta, "fecha_solicitud": "01/11/2026", "fecha_limite": fecha, "dias": 17,
                         "faltan": 2, "responsable": "Jefe Administrativo Financiero", "persona": "Nombre Apellido",
                         "subtareas": [{"texto": "Paso de ejemplo", "fecha": "05/11/2026", "hecho": "Sí"},
                                       {"texto": "Otro paso", "fecha": "", "hecho": "No"}]})
    return {
        "unidad": {"nombre": "UAF - Unidad Administrativa Financiera", "sigla": "UAF"},
        "tarea": ejemplos[0],
        "tareas": ejemplos,
        "resumen": {"total": 3, "pendientes": 3, "vencidas": 1, "por_vencer": 1, "criticas": 2, "sin_solucion": 1, "concluidas": 0},
        "generado": {"fecha": formato_fecha_hora(ahora_utc()), "por": usuario.nombre_usuario,
                     "filtros": "Datos de ejemplo"},
        **_ejemplo_tablero(),
    }


def _ejemplo_tablero() -> dict:
    """Datos ficticios de resumen, agenda y gráficos (para «Probar» cualquier plantilla)."""
    unidades = [("UAF", "UAF - Unidad Administrativa Financiera"), ("UPT", "UPT - Unidad de Promoción Turística")]
    barras = {"etiquetas": [u for u, _ in unidades], "unidades": [1, 2],
              "series": [{"alerta": a, "color": c, "valores": v} for a, c, v in (
                  (alertas.VENCIDO, "#B42318", [2, 1]), (alertas.POR_VENCER, "#D49A2A", [1, 0]),
                  (alertas.EN_CURSO, "#2E4A7D", [3, 2]))]}
    mensual = {"etiquetas": ["sep 26", "oct 26", "nov 26"], "creadas": [4, 6, 3], "concluidas": [2, 5, 4]}
    embudo = [{"id": 1, "estado": "Pendiente", "valor": 3}, {"id": 2, "estado": "En proceso", "valor": 4}]
    graficos_ = {"barras": barras, "mensual": mensual, "embudo": embudo,
                 "cumplimiento": {"pct": 75, "base": 8, "meta": 80}}
    return {
        "indicadores": {"total_mre": 12, "pendientes": 9, "vencidas": 3, "sin_respuesta": 2, "alta_prioridad": 4,
                        "por_vencer": 1, "concluidas_mes": 4, "variacion": 33, "fechas_limite": 5,
                        "recordatorios_pendientes": 6, "recordatorios_vencidos": 1, "bloqueadas": 1},
        "por_unidad": [{"sigla": s, "nombre": n, "total": 6, "pendientes": 4 + k, "vencidas": 2 - k, "alta": 2,
                        "sin_respuesta": 1, "concluidas": 2, "vencido": 2 - k, "critico": 0, "por_vencer": 1 - k,
                        "seguimiento": 0, "en_curso": 3 - k, "sin_fecha": 0, "cumplimiento": 80 - 20 * k}
                       for k, (s, n) in enumerate(unidades)],
        "por_instancia": [{"nombre": "Despacho Ministerial", "pendientes": 4}, {"nombre": "CIAAAT", "pendientes": 2}],
        "por_tipo": [{"nombre": "Solicitud al MRE", "pendientes": 6}, {"nombre": "Autorización del MRE", "pendientes": 3}],
        "mes": {"nombre": "Noviembre 2026", "desde": "01/11/2026", "hasta": "30/11/2026"},
        "eventos": [
            {"fecha": "10/11/2026", "dia": "Martes", "tipo": "Fecha límite", "codigo": "UAF-001", "unidad": "UAF",
             "texto": "Tarea de ejemplo 1", "asunto": "Tarea de ejemplo 1", "responsable": "Jefe Administrativo",
             "persona": "Nombre Apellido", "estado": "En proceso", "estado_agenda": "En gestión",
             "alerta": "VENCIDO", "hecho": "No"},
            {"fecha": "20/11/2026", "dia": "Viernes", "tipo": "Recordatorio", "codigo": "UAF-002", "unidad": "UAF",
             "texto": "Paso de ejemplo", "asunto": "Tarea de ejemplo 2", "responsable": "Técnico", "persona": "",
             "estado": "Pendiente", "estado_agenda": "Pendiente", "alerta": "POR VENCER", "hecho": "Sí"},
        ],
        "cumplimiento": {"porcentaje": 75, "base": 8, "meta": 80},
        "mensual": [{"mes": m, "creadas": c, "concluidas": x}
                    for m, c, x in zip(mensual["etiquetas"], mensual["creadas"], mensual["concluidas"])],
        "embudo": [{"estado": f["estado"], "tareas": f["valor"]} for f in embudo],
        "_graficos": graficos_,
    }


# ------------------------------------------------------------------ resumen, agenda y gráficos
DIAS_SEMANA = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
CLAVE_ALERTA = {alertas.VENCIDO: "vencido", alertas.CRITICO: "critico", alertas.POR_VENCER: "por_vencer",
                alertas.SEGUIMIENTO: "seguimiento", alertas.EN_CURSO: "en_curso", alertas.SIN_FECHA: "sin_fecha"}


def _valores(kpis, claves) -> dict:
    return dict(zip(claves, (v for _, v, _ in kpis)))


def contexto_resumen(datos: dict, detalle: list, usuario: Usuario, unidad=None, filtros: str = "") -> dict:
    """`datos` de services.resumen.resumen_ejecutivo; `tareas` es el detalle filtrado (solo gestiones con el MRE)."""
    ctx = contexto(detalle, usuario, unidad, filtros)
    ctx["indicadores"] = _valores(datos["kpis"], ("total_mre", "pendientes", "vencidas", "sin_respuesta",
                                                  "alta_prioridad"))
    ctx["por_unidad"] = [{"sigla": r["unidad"].sigla, "nombre": r["unidad"].nombre,
                          **{k: r[k] for k in ("total", "pendientes", "vencidas", "alta", "sin_respuesta",
                                               "concluidas")}} for r in datos["por_unidad"]]
    ctx["por_instancia"] = [{"nombre": n, "pendientes": c} for n, c in datos["por_instancia"]]
    ctx["por_tipo"] = [{"nombre": n, "pendientes": c} for n, c in datos["por_tipo"]]
    return ctx


def _evento(e: dict) -> dict:
    t = e["info"].t
    return {
        "fecha": formato_fecha(e["fecha"]), "dia": DIAS_SEMANA[e["fecha"].weekday()],
        "tipo": "Fecha límite" if e["tipo"] == "limite" else "Recordatorio",
        "codigo": t.codigo, "unidad": t.unidad.sigla, "texto": e["texto"], "asunto": t.asunto,
        "responsable": t.responsable.nombre if t.responsable else "",
        "persona": _txt(t.responsable.persona) if t.responsable else "",
        "estado": t.estado.valor if t.estado else "", "estado_agenda": e["estado_agenda"],
        "alerta": e["alerta"], "hecho": "Sí" if e["hecho"] else "No",
    }


def contexto_agenda(mes, evs: list, kpis: list, usuario: Usuario, unidad=None, filtros: str = "") -> dict:
    """`evs`: eventos del mes (services.agenda.eventos); `tareas`: las tareas que tienen algún evento."""
    import calendar

    vistas, infos = set(), []
    for e in evs:
        if e["info"].t.id not in vistas:
            vistas.add(e["info"].t.id)
            infos.append(e["info"])
    ctx = contexto(alertas.ordenar(infos), usuario, unidad, filtros)
    ultimo = mes.replace(day=calendar.monthrange(mes.year, mes.month)[1])
    from app.services.agenda import nombre_mes
    ctx["mes"] = {"nombre": nombre_mes(mes), "desde": formato_fecha(mes), "hasta": formato_fecha(ultimo)}
    ctx["indicadores"] = _valores(kpis, ("fechas_limite", "vencidas", "recordatorios_pendientes",
                                         "recordatorios_vencidos", "bloqueadas"))
    ctx["eventos"] = [_evento(e) for e in evs]
    return ctx


def contexto_graficos(datos: dict, infos: list, unidades, usuario: Usuario, unidad=None) -> dict:
    """`datos` de services.graficos.datos (lo mismo que dibuja la vista). Las imágenes se arman solo para Word."""
    from app.services.graficos import cumplimiento_de

    ctx = contexto(alertas.ordenar([i for i in infos if not i.concluida]), usuario, unidad)
    tarjetas = {k["clave"]: k for k in datos["tarjetas"]}
    ctx["indicadores"] = {c: tarjetas[c]["valor"] for c in ("pendientes", "vencidas", "por_vencer", "sin_respuesta",
                                                             "concluidas_mes")}
    variacion = tarjetas["concluidas_mes"].get("variacion")
    ctx["indicadores"]["variacion"] = "" if variacion is None else variacion
    c = datos["cumplimiento"]
    ctx["cumplimiento"] = {"porcentaje": "" if c["pct"] is None else c["pct"], "base": c["base"], "meta": c["meta"]}
    filas = []
    for k, u in enumerate(unidades):
        fila = {"sigla": u.sigla, "nombre": u.nombre}
        for s in datos["barras"]["series"]:
            fila[CLAVE_ALERTA[s["alerta"]]] = s["valores"][k]
        fila["pendientes"] = sum(s["valores"][k] for s in datos["barras"]["series"])
        pct, _ = cumplimiento_de([i for i in infos if i.t.unidad_id == u.id])
        fila["cumplimiento"] = "" if pct is None else pct
        filas.append(fila)
    ctx["por_unidad"] = filas
    m = datos["mensual"]
    ctx["mensual"] = [{"mes": e, "creadas": a, "concluidas": b}
                      for e, a, b in zip(m["etiquetas"], m["creadas"], m["concluidas"])]
    ctx["embudo"] = [{"estado": f["estado"], "tareas": f["valor"]} for f in datos["embudo"]]
    ctx["por_instancia"] = [{"nombre": x["nombre"], "pendientes": x["valor"]} for x in datos["instancias"]]
    ctx["_graficos"] = datos
    return ctx


# ------------------------------------------------------------------ generación
def _render_docx(ruta: Path, ctx: dict) -> bytes:
    tpl = DocxTemplate(str(ruta))
    imagenes = imagenes_png.todas(ctx["_graficos"]) if ctx.get("_graficos") else {}
    if imagenes:  # PNG de los gráficos → imágenes del Word ({{ imagen.barras }}…)
        ctx = {**ctx, "imagen": {k: InlineImage(tpl, io.BytesIO(v), width=Mm(ANCHO_IMAGEN_MM.get(k, 160)))
                                 for k, v in imagenes.items()}}
    tpl.render(ctx, jinja_env=entorno(), autoescape=True)
    buf = io.BytesIO()
    tpl.save(buf)
    return buf.getvalue()


def _valor_celda(env, texto: str, ctx: dict):
    m = _SOLO_MARCADOR.match(texto)
    if m and "{{" not in m.group(1):
        valor = env.compile_expression(m.group(1), undefined_to_none=True)(**ctx)
        if valor is None or isinstance(valor, (dict, list)):
            return ""
        return valor
    return env.from_string(texto).render(ctx)


def _repetir_fila(ws, fila: int, letra: str, elementos: list, env, ctx: dict) -> None:
    """Repite la fila una vez por elemento; cada copia ve el elemento como `letra` (t, u, e…)."""
    modelo = [(c.column, c.value, copy(c._style)) for c in ws[fila]]
    alto = ws.row_dimensions[fila].height
    if not elementos:
        for col, _, _ in modelo:
            ws.cell(fila, col).value = None
        return
    extra = len(elementos) - 1
    if extra:
        ws.insert_rows(fila + 1, extra)
        for rango in ws.merged_cells.ranges:
            if rango.min_row > fila:
                rango.shift(0, extra)
    for k, elemento in enumerate(elementos):
        sub = {**ctx, letra: elemento}
        for col, valor, estilo in modelo:
            celda = ws.cell(fila + k, col)
            celda._style = copy(estilo)
            celda.value = _valor_celda(env, valor, sub) if isinstance(valor, str) and "{" in valor else valor
        if alto:
            ws.row_dimensions[fila + k].height = alto


def _render_xlsx(ruta: Path, ctx: dict) -> bytes:
    wb = load_workbook(ruta)
    env = entorno()
    for ws in wb.worksheets:
        filas = []
        for r in range(1, ws.max_row + 1):
            letra = next((m.group(1) for c in ws[r] if isinstance(c.value, str)
                          for m in [_FILA_REPETIBLE.search(c.value)] if m), None)
            if letra:
                filas.append((r, letra))
        for r, letra in reversed(filas):
            _repetir_fila(ws, r, letra, ctx.get(FILAS_EXCEL[letra]) or [], env, ctx)
        for fila in ws.iter_rows():
            for c in fila:
                if isinstance(c.value, str) and ("{{" in c.value or "{%" in c.value):
                    c.value = _valor_celda(env, c.value, ctx)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generar(p: Plantilla, ctx: dict) -> bytes:
    """Llena la plantilla. Errores de marcadores o del sandbox se devuelven como ErrorNegocio."""
    ruta = ruta_archivo(p)
    if not ruta.is_file():
        raise ErrorNegocio("No se encuentra el archivo de la plantilla. Vuelva a subirlo.")
    try:
        return _render_docx(ruta, ctx) if p.formato == "docx" else _render_xlsx(ruta, ctx)
    except TemplateError as e:  # incluye SecurityError del sandbox
        raise ErrorNegocio(f"No se pudo llenar la plantilla «{p.nombre}»: {e}") from e
    except Exception as e:  # p. ej. {{ tarea.codigo + 1 }} (TypeError) o un archivo dañado
        current_app.logger.exception("Fallo al llenar la plantilla %s", p.id)
        raise ErrorNegocio(f"No se pudo llenar la plantilla «{p.nombre}»: revise sus marcadores "
                           f"({type(e).__name__}).") from e


MIMES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def documento(p: Plantilla, ctx: dict, formato: str) -> tuple[bytes, str]:
    """Genera el documento en el formato pedido: 'original' o 'pdf'. Devuelve (bytes, extensión)."""
    from app.services import pdf  # reportlab se carga solo al generar un PDF

    datos = generar(p, ctx)
    if formato == "pdf":
        return pdf.convertir_a_pdf(datos, p.formato), "pdf"
    return datos, p.formato


def nombre_descarga(p: Plantilla, sufijo: str, extension: str) -> str:
    base = re.sub(r"[^\w\-]+", "_", f"{p.nombre}_{sufijo}", flags=re.UNICODE).strip("_")[:120]
    return f"{base or 'documento'}.{extension}"
