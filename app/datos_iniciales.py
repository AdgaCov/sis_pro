"""Datos iniciales, tomados de referencias/Codigoseguim.gs."""
from app.models.catalogo import ESTADO_CONCLUIDO, PRIORIDAD_ALTA, TIPO_INTERNA

UNIDADES = [
    ("DGE-STAF", "DGE - STAF"),
    ("UAF", "UAF - Unidad Administrativa Financiera"),
    ("UPT", "UPT - Unidad de Promoción Turística"),
    ("UDTP", "UDTP - Unidad de Desarrollo Turístico y Proyectos"),
    ("UEP", "UEP - Unidad Ejecutora del Programa BID 4643/BL-BO"),
    ("SISTEMAS", "Área de Sistemas"),
]

CARGO_APOYO = "Apoyo"

CARGOS_INICIALES = {
    "DGE-STAF": ["Técnico en Planificación", "Técnico Administrativo Director General Ejecutivo", "Secretaria"],
    "UAF": ["Jefe Administrativo Financiero", "Profesional en Presupuesto, Contabilidad y Tesorería",
            "Profesional en Contrataciones", "Técnico en Recursos Humanos", "Mensajero"],
    "SISTEMAS": ["Técnico en Sistemas"],
    "UPT": ["Técnico en Diseño Gráfico", "Técnico en Fotografía"],
    "UDTP": ["Jefe de Desarrollo Turístico y Proyectos", "Profesional en Turismo",
             "Profesional en Preparación y Evaluación de Proyectos", "Profesional en Ingeniería de Proyectos",
             "Profesional en Infraestructura", "Profesional en Arquitectura II", "Profesional en Medio Ambiente"],
    "UEP": ["Coordinador del Programa", "Especialista Administrativo Financiero",
            "Especialista en Planificación y Monitoreo", "Especialista en Infraestructura",
            "Especialista en Adquisiciones", "Especialista Legal", "Profesional Ambiental",
            "Profesional Arquitecto", "Ingeniero Civil II", "Ingeniero Civil I",
            "Técnico en Gestión Documental y Organización de Archivo"],
}

CATALOGOS = {
    "tipo": [TIPO_INTERNA, "Solicitud al MRE", "Autorización del MRE", "Gestión con el MRE (habilita otra tarea)"],
    "instancia": [
        "Dirección General de Asuntos Administrativos",
        "Dirección General de Asuntos Jurídicos",
        "Dirección General de Planificación",
        "Despacho Ministerial",
        "Viceministerio de Comercio Exterior, Inversiones Extranjeras e Integración",
        "Viceministerio de Turismo Sostenible y Culturas",
        "Viceministerio de Relaciones Exteriores",
        "Viceministerio de Gestión Consular e Institucional",
        "Unidad de Comunicación",
        "ADECINE",
        "Orquesta Sinfónica Nacional",
        "CIAAAT",
        "Otras",
    ],
    "estado": ["Pendiente", "En proceso", "Remitido a DGE", "Con V.º B.º de DGE", "Ingresado por Ventanilla Única",
               "Remitido a instancia del MRE", "En instancia del MRE – Sin respuesta", "Observado / Devuelto",
               "Respuesta recibida del MRE", "Autorizado", ESTADO_CONCLUIDO, "Otro"],
    "prioridad": [PRIORIDAD_ALTA, "Media", "Baja"],
    "area": [
        "Gestión institucional / Planificación",
        "Administración y finanzas",
        "Asuntos jurídicos y convenios",
        "Promoción turística (ferias, campañas, Marca País)",
        "Desarrollo turístico y proyectos de inversión",
        "Diplomacia cultural e imagen país",
        "Cooperación y financiamiento externo",
        "Comunicación y contenidos digitales",
        "Capacitación y asistencia técnica",
        "Tecnología y sistemas",
    ],
}

PROTEGIDOS = {("tipo", TIPO_INTERNA), ("estado", ESTADO_CONCLUIDO), ("prioridad", PRIORIDAD_ALTA)}
