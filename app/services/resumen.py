"""Datos del tablero: resumen ejecutivo, alertas, informe crítico y cronograma.

Todo parte de `cargar(usuario)`, que solo trae las tareas que el usuario puede ver.
"""
import unicodedata
from datetime import date, timedelta

from sqlalchemy.orm import selectinload

from app.models import Cargo, Tarea, Usuario
from app.services import alertas as al
from app.services import permisos
from app.utils.fechas import formato_fecha, hoy_local

MESES = ("ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC")


# ------------------------------------------------------------------ carga y filtros
def cargar(usuario: Usuario, hoy: date | None = None) -> list[al.InfoTarea]:
    q = permisos.consulta_tareas(usuario).options(
        selectinload(Tarea.unidad), selectinload(Tarea.tipo), selectinload(Tarea.estado),
        selectinload(Tarea.instancia), selectinload(Tarea.prioridad), selectinload(Tarea.area),
        selectinload(Tarea.responsable).selectinload(Cargo.unidad), selectinload(Tarea.habilita_a),
        selectinload(Tarea.subtareas), selectinload(Tarea.adjuntos),
    )
    return al.calcular(q.all(), hoy)


def _normal(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return sin_tildes.casefold()


def _coincide(i: al.InfoTarea, texto: str) -> bool:
    t = i.t
    campos = [t.codigo, t.asunto, t.hoja_ruta, t.resultado, t.gestion_requerida, t.observaciones, t.linea_solucion]
    if t.responsable:
        campos += [t.responsable.nombre, t.responsable.persona]
    return texto in _normal(" ".join(c for c in campos if c))


def filtrar(infos: list[al.InfoTarea], f: dict, solo_mre: bool = False) -> list[al.InfoTarea]:
    """Filtros: unidad_id, tipo_id, estado_id, instancia_id, area_id, prioridad_id, responsable_id,
    alerta, texto, ver_concluidas. Los valores vacíos o 0 no filtran."""
    texto = _normal((f.get("texto") or "").strip())
    salida = []
    for i in infos:
        t = i.t
        if solo_mre and not i.mre:
            continue
        if not f.get("ver_concluidas") and i.concluida and f.get("alerta") != al.CONCLUIDO:
            continue
        if any(f.get(c) and getattr(t, c) != f[c] for c in
               ("unidad_id", "tipo_id", "estado_id", "instancia_id", "area_id", "prioridad_id", "responsable_id")):
            continue
        if f.get("alerta") and i.alerta != f["alerta"]:
            continue
        if texto and not _coincide(i, texto):
            continue
        salida.append(i)
    return al.ordenar(salida)


def _contar(infos, cond) -> int:
    return sum(1 for i in infos if cond(i))


def _sin_respuesta(i: al.InfoTarea) -> bool:
    return "sin respuesta" in (i.t.estado.valor if i.t.estado else "").lower()


# ------------------------------------------------------------------ resumen ejecutivo
def resumen_ejecutivo(infos: list[al.InfoTarea], unidades) -> dict:
    """Solo gestiones con el MRE (todo menos «Tarea interna")."""
    mre = [i for i in infos if i.mre]
    abiertas = [i for i in mre if not i.concluida]
    por_unidad = []
    for u in unidades:
        todas = [i for i in mre if i.t.unidad_id == u.id]
        ab = [i for i in todas if not i.concluida]
        por_unidad.append({
            "unidad": u, "total": len(todas), "pendientes": len(ab),
            "vencidas": _contar(ab, lambda i: i.alerta == al.VENCIDO),
            "alta": _contar(ab, lambda i: i.t.prioridad and i.t.prioridad.valor == "Alta"),
            "sin_respuesta": _contar(ab, _sin_respuesta),
            "concluidas": len(todas) - len(ab),
        })
    por_instancia: dict[str, int] = {}
    por_tipo: dict[str, int] = {}
    for i in abiertas:
        clave = i.t.instancia.valor if i.t.instancia else "Sin instancia"
        por_instancia[clave] = por_instancia.get(clave, 0) + 1
        por_tipo[i.t.tipo.valor] = por_tipo.get(i.t.tipo.valor, 0) + 1
    return {
        "kpis": [
            ("Total gestiones MRE", len(mre), False),
            ("Pendientes", len(abiertas), False),
            ("Vencidas", _contar(abiertas, lambda i: i.alerta == al.VENCIDO), True),
            ("Sin respuesta del MRE", _contar(abiertas, _sin_respuesta), True),
            ("Alta prioridad pendiente", _contar(abiertas, lambda i: i.t.prioridad and i.t.prioridad.valor == "Alta"), True),
        ],
        "por_unidad": por_unidad,
        "por_instancia": sorted(por_instancia.items(), key=lambda x: (-x[1], x[0])),
        "por_tipo": sorted(por_tipo.items(), key=lambda x: (-x[1], x[0])),
    }


def kpis_generales(infos: list[al.InfoTarea]) -> list[tuple]:
    abiertas = [i for i in infos if not i.concluida]
    return [
        ("Tareas abiertas", len(abiertas), False),
        ("Vencidas", _contar(abiertas, lambda i: i.alerta == al.VENCIDO), True),
        ("Por vencer", _contar(abiertas, lambda i: i.alerta == al.POR_VENCER), True),
        ("Críticas", _contar(abiertas, lambda i: i.critica), True),
        ("Sin responsable", _contar(abiertas, lambda i: i.sin_responsable), True),
        ("Concluidas", len(infos) - len(abiertas), False),
    ]


# ------------------------------------------------------------------ alertas
def _hace(n: int) -> str:
    return "hoy" if n == 0 else ("hace 1 día" if n == 1 else f"hace {n} días")


def _en(n: int) -> str:
    return "hoy" if n == 0 else ("en 1 día" if n == 1 else f"en {n} días")


def grupos_alertas(infos: list[al.InfoTarea], cfg: dict) -> list[dict]:
    """Grupos de la vista Alertas. Cada item: (info, detalle). Una tarea puede salir en varios grupos."""
    ab = [i for i in infos if not i.concluida]
    tipo = lambda i: i.t.tipo.valor if i.t.tipo else ""  # noqa: E731
    definicion = [
        ("r", "Vencidas", "La fecha límite ya pasó",
         [i for i in ab if i.alerta == al.VENCIDO],
         lambda i: f"Venció el {formato_fecha(i.t.fecha_limite)} ({_hace(-i.faltan)})"),
        ("a", "Por vencer", f"Faltan {cfg['DIAS_POR_VENCER']} días o menos",
         [i for i in ab if i.alerta == al.POR_VENCER],
         lambda i: f"Vence {_en(i.faltan)} · {formato_fecha(i.t.fecha_limite)}"),
        ("r", "Críticas", f"Prioridad alta con más de {cfg['DIAS_CRITICO']} días desde la solicitud",
         [i for i in ab if i.alerta == al.CRITICO],
         lambda i: f"{i.dias} días desde la solicitud · {i.t.estado.valor}"),
        ("g", "Sin actualizar", f"Nadie las actualizó en más de {cfg['DIAS_SIN_ACTUALIZAR']} días",
         [i for i in ab if i.sin_actualizar],
         lambda i: f"Última actualización {_hace(i.dias_sin_actualizar)}"),
        ("r", "Subtareas vencidas", "Pasos con fecha pasada que no se marcaron como hechos",
         [i for i in ab if i.subtareas_vencidas],
         lambda i: " · ".join(f"{formato_fecha(s.fecha)} {s.texto}" for s in i.subtareas_vencidas)),
        ("c", "Bloquean otra tarea", "Gestiones pendientes de las que depende otra tarea",
         [i for i in ab if i.bloquea],
         lambda i: f"Habilita la tarea {i.t.habilita_a.codigo}" if i.t.habilita_a else ""),
        ("g", "Sin responsable", "Asigne un responsable de la gestión",
         [i for i in ab if i.sin_responsable], tipo),
        ("g", "Sin fecha límite", "Defina un plazo para que entren al cronograma",
         [i for i in ab if i.sin_fecha_limite],
         lambda i: tipo(i) + (f" · {i.dias} días desde el inicio" if i.dias is not None else "")),
        ("r", "Críticas sin línea de solución", "Defina la acción para destrabarlas",
         [i for i in ab if i.sin_solucion],
         lambda i: ("Riesgo alto · " if i.t.nivel_riesgo == "Alto" else "") + i.alerta),
        ("a", "Concluidas sin medio de verificación", "Registre el respaldo: nota, HR, acta o archivo",
         [i for i in infos if i.sin_respaldo],
         lambda i: f"Concluida el {formato_fecha(i.t.fecha_conclusion)} · {tipo(i)}"),
    ]
    return [
        {"color": color, "titulo": titulo, "descripcion": desc,
         "items": [(i, detalle(i)) for i in al.ordenar(lista)]}
        for color, titulo, desc, lista, detalle in definicion
    ]


# ------------------------------------------------------------------ informe crítico
def informe_critico(infos: list[al.InfoTarea], unidades) -> dict:
    criticas = al.ordenar([i for i in infos if i.critica])
    sin_solucion = [i for i in criticas if i.sin_solucion]
    grupos = []
    for u in unidades:
        lista = [i for i in criticas if i.t.unidad_id == u.id]
        if lista:
            grupos.append({"unidad": u, "items": lista})
    return {
        "kpis": [
            ("Tareas críticas", len(criticas), True),
            ("Vencidas", _contar(criticas, lambda i: i.alerta == al.VENCIDO), True),
            ("Riesgo alto", _contar(criticas, lambda i: i.t.nivel_riesgo == "Alto"), True),
            ("Sin línea de solución", len(sin_solucion), True),
            ("Gestiones con el MRE", _contar(criticas, lambda i: i.mre), False),
        ],
        "grupos": grupos,
        "sin_solucion": sin_solucion,
        "total": len(criticas),
    }


# ------------------------------------------------------------------ cronograma
def _primero_mes_siguiente(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def cronograma(infos: list[al.InfoTarea], unidades, agrupar: bool, hoy: date | None = None) -> dict:
    """Barras de un diagrama de Gantt, con posiciones en % para dibujarlas solo con CSS."""
    hoy = hoy or hoy_local()
    barras, sin_fechas = [], []
    for i in infos:
        t = i.t
        pasos = [s.fecha for s in t.subtareas if s.fecha]
        if not t.fecha_solicitud and not t.fecha_limite:
            if not pasos:
                sin_fechas.append(i)
                continue
            barras.append({"i": i, "ini": min(pasos), "fin": max(pasos), "abierta": not i.concluida, "por_pasos": True})
            continue
        ini = t.fecha_solicitud or t.fecha_limite
        if i.concluida:
            fin = t.fecha_conclusion or t.fecha_limite or ini
        elif t.fecha_limite:
            fin = max(t.fecha_limite, hoy) if i.alerta == al.VENCIDO else t.fecha_limite
        else:
            fin = hoy
        barras.append({"i": i, "ini": ini, "fin": max(fin, ini),
                       "abierta": not t.fecha_limite and not i.concluida, "por_pasos": False})

    minimo, maximo = hoy - timedelta(days=14), hoy + timedelta(days=30)
    for b in barras:
        minimo = min(minimo, b["ini"])
        maximo = max(maximo, b["fin"], b["i"].t.fecha_limite or b["fin"])
        for s in b["i"].t.subtareas:
            if s.fecha:
                minimo, maximo = min(minimo, s.fecha), max(maximo, s.fecha)
    if (maximo - minimo).days > 270:
        minimo = maximo - timedelta(days=270)
    minimo -= timedelta(days=2)
    maximo += timedelta(days=3)
    total = (maximo - minimo).days

    def pct(d: date) -> float:
        return round(max(0.0, min(100.0, (d - minimo).days / total * 100)), 2)

    meses = []
    m = _primero_mes_siguiente(minimo)
    while m < maximo:
        meses.append({"pct": pct(m), "texto": f"{MESES[m.month - 1]} {str(m.year)[2:]}"})
        m = _primero_mes_siguiente(m)

    filas = []
    for b in sorted(barras, key=lambda x: (x["ini"], x["i"].t.codigo)):
        i, t = b["i"], b["i"].t
        izq = pct(b["ini"])
        filas.append({
            "i": i, "izq": izq, "ancho": max(round(pct(b["fin"]) - izq, 2), 0.5),
            "abierta": b["abierta"], "por_pasos": b["por_pasos"],
            "hito": pct(t.fecha_limite) if t.fecha_limite and not i.concluida else None,
            "pasos": [{"pct": pct(s.fecha), "clase": "ok" if s.hecho else ("venc" if s.fecha < hoy else ""),
                       "titulo": f"{formato_fecha(s.fecha)} · {s.texto}" + (" (hecho)" if s.hecho else "")}
                      for s in t.subtareas if s.fecha],
        })

    if agrupar:
        grupos = [{"unidad": u, "filas": [f for f in filas if f["i"].t.unidad_id == u.id]} for u in unidades]
    else:
        grupos = [{"unidad": None, "filas": filas}]
    return {"meses": meses, "grupos": grupos, "hoy": pct(hoy), "sin_fechas": al.ordenar(sin_fechas),
            "hay_barras": bool(filas)}
