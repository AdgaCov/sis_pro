"""Datos del tablero gráfico. Un gráfico por pregunta; todo sale de las tareas visibles para el usuario."""
from datetime import date

from app.models import Catalogo
from app.models.catalogo import ESTADO_CONCLUIDO
from app.services import alertas as al
from app.utils.fechas import a_local, hoy_local

MESES_CORTOS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")

# Series de «Pendientes por unidad»: una por alerta abierta, con 4 familias de color
# (rojo = vencido/crítico, ámbar = por vencer/seguimiento, azul = en curso, gris = sin fecha).
SERIES_ALERTA = (
    (al.VENCIDO, "#B42318"), (al.CRITICO, "#E06C66"), (al.POR_VENCER, "#D49A2A"),
    (al.SEGUIMIENTO, "#EBC77E"), (al.EN_CURSO, "#2E4A7D"), (al.SIN_FECHA, "#8A93A6"),
)


def _mes(d: date, delta: int = 0) -> date:
    i = d.year * 12 + d.month - 1 + delta
    return date(i // 12, i % 12 + 1, 1)


def _en_mes(d: date | None, mes: date) -> bool:
    return d is not None and d.year == mes.year and d.month == mes.month


def _cumplimiento(infos) -> tuple[int | None, int]:
    """% de concluidas con fecha límite que se cerraron a tiempo. (None si no hay base)."""
    base = [i for i in infos if i.concluida and i.t.fecha_limite and i.t.fecha_conclusion]
    if not base:
        return None, 0
    a_tiempo = sum(1 for i in base if i.t.fecha_conclusion <= i.t.fecha_limite)
    return round(a_tiempo * 100 / len(base)), len(base)


def _sin_respuesta(i) -> bool:
    return "sin respuesta" in (i.t.estado.valor if i.t.estado else "").lower()


def datos(infos: list[al.InfoTarea], unidades, por_unidad: bool, meta: int, hoy: date | None = None) -> dict:
    """Todo lo que dibuja la vista Gráficos (y su PDF). Solo tipos simples: se envía como JSON."""
    hoy = hoy or hoy_local()
    abiertas = [i for i in infos if not i.concluida]
    mes, mes_ant = _mes(hoy), _mes(hoy, -1)
    concl_mes = sum(1 for i in infos if i.concluida and _en_mes(i.t.fecha_conclusion, mes))
    concl_ant = sum(1 for i in infos if i.concluida and _en_mes(i.t.fecha_conclusion, mes_ant))
    variacion = round((concl_mes - concl_ant) * 100 / concl_ant) if concl_ant else None

    tarjetas = [
        {"clave": "pendientes", "titulo": "Pendientes", "valor": len(abiertas), "alerta": False},
        {"clave": "vencidas", "titulo": "Vencidas", "valor": sum(1 for i in abiertas if i.alerta == al.VENCIDO),
         "alerta": True, "filtro": {"alerta": al.VENCIDO}},
        {"clave": "por_vencer", "titulo": "Por vencer",
         "valor": sum(1 for i in abiertas if i.alerta == al.POR_VENCER), "alerta": True,
         "filtro": {"alerta": al.POR_VENCER}},
        {"clave": "sin_respuesta", "titulo": "Sin respuesta del MRE",
         "valor": sum(1 for i in abiertas if _sin_respuesta(i)), "alerta": True},
        {"clave": "concluidas_mes", "titulo": "Concluidas este mes", "valor": concl_mes, "alerta": False,
         "variacion": variacion},
    ]

    # Pendientes por unidad, divididas por alerta
    barras = {"etiquetas": [u.sigla for u in unidades], "unidades": [u.id for u in unidades], "series": []}
    for alerta, color in SERIES_ALERTA:
        barras["series"].append({
            "alerta": alerta, "color": color,
            "valores": [sum(1 for i in abiertas if i.t.unidad_id == u.id and i.alerta == alerta) for u in unidades],
        })

    # Creadas contra concluidas, últimos 12 meses
    meses = [_mes(hoy, -k) for k in range(11, -1, -1)]
    creadas = [sum(1 for i in infos if i.t.creado_en and _en_mes(a_local(i.t.creado_en).date(), m)) for m in meses]
    concluidas = [sum(1 for i in infos if i.concluida and _en_mes(i.t.fecha_conclusion, m)) for m in meses]

    # Embudo de estados abiertos, en el orden del catálogo
    estados = Catalogo.query.filter(Catalogo.tipo == "estado", Catalogo.valor != ESTADO_CONCLUIDO) \
        .order_by(Catalogo.orden, Catalogo.valor).all()
    embudo = [{"id": e.id, "estado": e.valor, "valor": sum(1 for i in abiertas if i.t.estado_id == e.id)}
              for e in estados]
    embudo = [x for x in embudo if x["valor"]]

    # Instancias del MRE con más gestiones pendientes
    por_instancia: dict[int, dict] = {}
    for i in abiertas:
        if i.mre and i.t.instancia:
            x = por_instancia.setdefault(i.t.instancia_id, {"id": i.t.instancia_id, "nombre": i.t.instancia.valor,
                                                            "valor": 0})
            x["valor"] += 1
    instancias = sorted(por_instancia.values(), key=lambda x: (-x["valor"], x["nombre"]))[:8]

    pct, base = _cumplimiento(infos)
    anillos = []
    if por_unidad:
        for u in unidades:
            p, n = _cumplimiento([i for i in infos if i.t.unidad_id == u.id])
            anillos.append({"sigla": u.sigla, "unidad_id": u.id, "pct": p, "base": n})

    return {
        "tarjetas": tarjetas,
        "barras": barras,
        "cumplimiento": {"pct": pct, "base": base, "meta": meta},
        "mensual": {"etiquetas": [f"{MESES_CORTOS[m.month - 1]} {str(m.year)[2:]}" for m in meses],
                    "creadas": creadas, "concluidas": concluidas},
        "embudo": embudo,
        "instancias": instancias,
        "anillos": anillos,
    }


def proximos_vencimientos(infos: list[al.InfoTarea], limite: int = 10):
    """Para la unidad: sus tareas abiertas con fecha límite, de la más urgente (o vencida) a la más lejana."""
    lista = [i for i in infos if not i.concluida and i.t.fecha_limite]
    return sorted(lista, key=lambda i: (i.t.fecha_limite, i.t.codigo))[:limite]
