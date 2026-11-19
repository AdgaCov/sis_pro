"""Agenda Despacho: fechas límite y recordatorios (subtareas con fecha) en un calendario.

Se arma con los datos de las tareas (la app alimenta la agenda, como en la versión original);
no tiene datos propios ni se conecta con Google Sheets.
"""
import calendar
from datetime import date, timedelta

from app.services import alertas as al
from app.utils.fechas import hoy_local

MESES = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre",
         "Octubre", "Noviembre", "Diciembre")
DIAS_SEMANA = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
ESTADOS_AGENDA = ("Pendiente", "En gestión", "Bloqueada", "Concluida")


def estado_agenda(estado: str) -> str:
    """Mismo criterio que la app original al publicar en la Agenda Despacho."""
    if estado == "Concluido":
        return "Concluida"
    if estado == "Pendiente":
        return "Pendiente"
    if estado == "Observado / Devuelto":
        return "Bloqueada"
    return "En gestión"


ANIO_MIN, ANIO_MAX = 2000, 2100  # fuera de este rango el calendario y la navegación no tienen sentido


def leer_mes(texto: str | None, hoy: date | None = None) -> date:
    """'2026-11' → date(2026, 11, 1). Si no es válido (o el año es absurdo), el mes actual."""
    hoy = hoy or hoy_local()
    try:
        anio, mes = (int(x) for x in (texto or "").split("-"))
        if not ANIO_MIN <= anio <= ANIO_MAX:
            raise ValueError
        return date(anio, mes, 1)
    except ValueError:
        return hoy.replace(day=1)


def nombre_mes(d: date) -> str:
    return f"{MESES[d.month - 1]} {d.year}"


def mes_vecino(d: date, delta: int) -> date:
    indice = d.year * 12 + d.month - 1 + delta
    return date(indice // 12, indice % 12 + 1, 1)


def eventos(infos: list[al.InfoTarea], desde: date, hasta: date, hoy: date | None = None) -> list[dict]:
    """Eventos entre dos fechas (incluidas): fecha límite de tareas abiertas y recordatorios de subtareas."""
    hoy = hoy or hoy_local()
    salida = []
    for i in infos:
        t = i.t
        if i.concluida:
            continue
        ag = estado_agenda(t.estado.valor if t.estado else "")
        if t.fecha_limite and desde <= t.fecha_limite <= hasta:
            salida.append({"fecha": t.fecha_limite, "tipo": "limite", "info": i, "texto": t.asunto,
                           "alerta": i.alerta, "clase": al.CLASE[i.alerta], "estado_agenda": ag, "hecho": False})
        for s in t.subtareas:
            if s.fecha and desde <= s.fecha <= hasta:
                if s.hecho:
                    clase, alerta = "CONCLUIDO", al.CONCLUIDO
                elif s.fecha < hoy:
                    clase, alerta = "VENCIDO", al.VENCIDO
                else:
                    clase, alerta = al.CLASE[i.alerta], i.alerta
                salida.append({"fecha": s.fecha, "tipo": "recordatorio", "info": i, "texto": s.texto,
                               "alerta": alerta, "clase": clase, "estado_agenda": ag, "hecho": s.hecho})
    salida.sort(key=lambda e: (e["fecha"], e["tipo"] != "limite", al.ORDEN[e["alerta"]], e["info"].t.codigo))
    return salida


def _peor(lista: list[dict]) -> str | None:
    pendientes = [e for e in lista if not e["hecho"]]
    if not pendientes:
        return None
    return min(pendientes, key=lambda e: al.ORDEN[e["alerta"]])["clase"]


def calendario(mes: date, evs: list[dict], hoy: date | None = None) -> list[list[dict]]:
    """Semanas (lunes a domingo) del mes, cada día con sus eventos y el color de su peor alerta."""
    hoy = hoy or hoy_local()
    por_dia: dict[date, list] = {}
    for e in evs:
        por_dia.setdefault(e["fecha"], []).append(e)
    semanas = []
    for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(mes.year, mes.month):
        semanas.append([{"fecha": d, "en_mes": d.month == mes.month, "hoy": d == hoy,
                         "eventos": por_dia.get(d, []), "peor": _peor(por_dia.get(d, []))} for d in semana])
    return semanas


def mes_en_pantalla(mes: date, evs: list[dict], hoy: date | None = None, elegido: bool = False) -> dict:
    """Un mes de la vista de tres meses. Los días de otros meses no muestran eventos (ya salen en su mes)."""
    semanas = calendario(mes, [e for e in evs if (e["fecha"].year, e["fecha"].month) == (mes.year, mes.month)], hoy)
    del_mes = sum(1 for e in evs if (e["fecha"].year, e["fecha"].month) == (mes.year, mes.month))
    return {"mes": mes, "clave": f"{mes:%Y-%m}", "titulo": nombre_mes(mes), "semanas": semanas,
            "eventos": del_mes, "elegido": elegido}


def rango_calendario(mes: date) -> tuple[date, date]:
    semanas = calendar.Calendar(firstweekday=0).monthdatescalendar(mes.year, mes.month)
    return semanas[0][0], semanas[-1][-1]


def por_dia(evs: list[dict]) -> list[tuple[date, list[dict]]]:
    dias: dict[date, list] = {}
    for e in evs:
        dias.setdefault(e["fecha"], []).append(e)
    return sorted(dias.items())


def resumen(evs: list[dict], hoy: date | None = None) -> list[tuple]:
    hoy = hoy or hoy_local()
    limites = [e for e in evs if e["tipo"] == "limite"]
    return [
        ("Fechas límite", len(limites), False),
        ("Vencidas", sum(1 for e in limites if e["alerta"] == al.VENCIDO), True),
        ("Recordatorios pendientes", sum(1 for e in evs if e["tipo"] == "recordatorio" and not e["hecho"]), False),
        ("Recordatorios vencidos", sum(1 for e in evs if e["tipo"] == "recordatorio" and not e["hecho"]
                                       and e["fecha"] < hoy), True),
        ("Bloqueadas", len({e["info"].t.id for e in evs if e["estado_agenda"] == "Bloqueada"}), True),
    ]


def proximos(infos: list[al.InfoTarea], dias: int = 14, hoy: date | None = None) -> list[tuple[date, list[dict]]]:
    hoy = hoy or hoy_local()
    return por_dia(eventos(infos, hoy, hoy + timedelta(days=dias), hoy))
