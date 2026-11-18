"""Alertas y señales de cada tarea. Se calculan al leer; nunca se guardan."""
from dataclasses import dataclass, field
from datetime import date

from flask import current_app

from app.models import Tarea
from app.models.catalogo import ESTADO_CONCLUIDO, PRIORIDAD_ALTA, TIPO_INTERNA
from app.utils.fechas import a_local, hoy_local

VENCIDO = "VENCIDO"
CRITICO = "CRÍTICO"
POR_VENCER = "POR VENCER"
SIN_FECHA = "SIN FECHA"
SEGUIMIENTO = "SEGUIMIENTO"
EN_CURSO = "EN CURSO"
CONCLUIDO = "CONCLUIDO"

# Orden de severidad (también el de las opciones del filtro)
ALERTAS = (VENCIDO, CRITICO, POR_VENCER, SEGUIMIENTO, SIN_FECHA, EN_CURSO, CONCLUIDO)
ORDEN = {a: i for i, a in enumerate(ALERTAS)}
# Clase CSS de cada alerta (sin tildes ni espacios)
CLASE = {a: a.replace("Í", "I").replace(" ", "-") for a in ALERTAS}


def _umbral(nombre: str, defecto: int) -> int:
    return current_app.config.get(nombre, defecto)


@dataclass
class InfoTarea:
    """Una tarea con sus datos calculados para el tablero."""

    t: Tarea
    alerta: str
    concluida: bool
    mre: bool
    dias: int | None             # días desde la solicitud (≥ 0)
    faltan: int | None           # días hasta la fecha límite (negativo = vencida)
    dias_sin_actualizar: int
    sin_actualizar: bool
    sin_responsable: bool
    sin_fecha_limite: bool
    bloquea: bool                # abierta y habilita otra tarea
    sin_respaldo: bool           # concluida sin medio de verificación ni archivos
    critica: bool
    sin_solucion: bool
    subtareas_vencidas: list = field(default_factory=list)
    bloqueada_por: list = field(default_factory=list)  # códigos de tareas abiertas que la habilitan

    @property
    def clase(self) -> str:
        return CLASE[self.alerta]

    @property
    def clave_orden(self):
        return (ORDEN[self.alerta], 999 if self.faltan is None else self.faltan, -(self.dias or 0), self.t.codigo)


def calcular_alerta(concluida: bool, prioridad_alta: bool, dias: int | None, faltan: int | None) -> str:
    """Primera regla que se cumpla, en el orden de CLAUDE.md."""
    if concluida:
        return CONCLUIDO
    if faltan is not None and faltan < 0:
        return VENCIDO
    if prioridad_alta and dias is not None and dias > _umbral("DIAS_CRITICO", 15):
        return CRITICO
    if faltan is not None and faltan <= _umbral("DIAS_POR_VENCER", 3):
        return POR_VENCER
    if dias is None:
        return SIN_FECHA
    if dias > _umbral("DIAS_SEGUIMIENTO", 7):
        return SEGUIMIENTO
    return EN_CURSO


def info(t: Tarea, hoy: date | None = None, bloqueada_por=None) -> InfoTarea:
    hoy = hoy or hoy_local()
    concluida = bool(t.estado and t.estado.valor == ESTADO_CONCLUIDO)
    prioridad_alta = bool(t.prioridad and t.prioridad.valor == PRIORIDAD_ALTA)
    dias = max(0, (hoy - t.fecha_solicitud).days) if t.fecha_solicitud else None
    faltan = (t.fecha_limite - hoy).days if t.fecha_limite else None
    alerta = calcular_alerta(concluida, prioridad_alta, dias, faltan)

    actualizado = a_local(t.actualizado_en).date() if t.actualizado_en else hoy
    dias_sin_actualizar = max(0, (hoy - actualizado).days)
    critica = not concluida and (
        alerta in (VENCIDO, CRITICO) or t.nivel_riesgo == "Alto" or (prioridad_alta and alerta == POR_VENCER)
    )
    sub_vencidas = [] if concluida else [s for s in t.subtareas if not s.hecho and s.fecha and s.fecha < hoy]
    return InfoTarea(
        t=t,
        alerta=alerta,
        concluida=concluida,
        mre=bool(t.tipo and t.tipo.valor != TIPO_INTERNA),
        dias=dias,
        faltan=faltan,
        dias_sin_actualizar=dias_sin_actualizar,
        sin_actualizar=not concluida and dias_sin_actualizar > _umbral("DIAS_SIN_ACTUALIZAR", 7),
        sin_responsable=not concluida and t.responsable_id is None,
        sin_fecha_limite=not concluida and t.fecha_limite is None,
        bloquea=not concluida and t.habilita_a_id is not None,
        sin_respaldo=concluida and not (t.medio_verificacion or "").strip() and not t.adjuntos,
        critica=critica,
        sin_solucion=critica and not (t.linea_solucion or "").strip(),
        subtareas_vencidas=sub_vencidas,
        bloqueada_por=list(bloqueada_por or []),
    )


def calcular(tareas, hoy: date | None = None) -> list[InfoTarea]:
    """Calcula la información de varias tareas. `bloqueada_por` se arma con las tareas recibidas."""
    hoy = hoy or hoy_local()
    tareas = list(tareas)
    abiertas_que_habilitan: dict[int, list[str]] = {}
    for t in tareas:
        if t.habilita_a_id and not (t.estado and t.estado.valor == ESTADO_CONCLUIDO):
            abiertas_que_habilitan.setdefault(t.habilita_a_id, []).append(t.codigo)
    return [info(t, hoy, abiertas_que_habilitan.get(t.id)) for t in tareas]


def ordenar(infos: list[InfoTarea]) -> list[InfoTarea]:
    return sorted(infos, key=lambda i: i.clave_orden)
