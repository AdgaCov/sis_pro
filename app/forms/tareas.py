from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import (BooleanField, DateField, FieldList, Form, FormField, SelectField, StringField, SubmitField,
                     TextAreaField)
from wtforms.validators import DataRequired, Length, Optional

from app.models.tarea import MAX_SUBTAREAS, NIVELES_RIESGO

OBLIGATORIO = "Campo obligatorio."
NINGUNO = (0, "—")


def _entero(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class SubtareaForm(Form):
    texto = StringField("Paso", validators=[Optional(), Length(max=300)])
    fecha = DateField("Fecha", validators=[Optional()])
    hecho = BooleanField("Hecho")


class TareaForm(FlaskForm):
    unidad_id = SelectField("Unidad", coerce=_entero, validate_choice=False)
    tipo_id = SelectField("Tipo *", coerce=_entero, validate_choice=False)
    area_id = SelectField("Área funcional", coerce=_entero, validate_choice=False)
    instancia_id = SelectField("Instancia del MRE", coerce=_entero, validate_choice=False)
    asunto = TextAreaField("Tarea / asunto *", validators=[DataRequired(OBLIGATORIO)])
    gestion_requerida = TextAreaField("Gestión requerida / acción")
    que_habilita = TextAreaField("¿Qué habilita?")
    habilita_a_id = SelectField("Habilita la tarea", coerce=_entero, validate_choice=False)
    riesgo_demora = StringField("Riesgo por demora")
    responsable_id = SelectField("Responsable (cargo)", coerce=_entero, validate_choice=False)
    hoja_ruta = StringField("Hoja de ruta", validators=[Length(max=100)])
    fecha_solicitud = DateField("Fecha solicitud / inicio", validators=[Optional()])
    fecha_limite = DateField("Fecha límite", validators=[Optional()])
    estado_id = SelectField("Estado *", coerce=_entero, validate_choice=False)
    prioridad_id = SelectField("Prioridad", coerce=_entero, validate_choice=False)
    nivel_riesgo = SelectField("Nivel de riesgo", validate_choice=False, choices=[("", "—")] + [(n, n) for n in NIVELES_RIESGO])
    plazo_solucion = DateField("Plazo de la solución", validators=[Optional()])
    linea_solucion = TextAreaField("Línea de solución")
    resultado = TextAreaField("Resultado obtenido")
    fecha_conclusion = DateField("Fecha de conclusión", validators=[Optional()])
    medio_verificacion = TextAreaField("Descripción del respaldo")
    observaciones = TextAreaField("Observaciones")
    subtareas = FieldList(FormField(SubtareaForm), min_entries=0, max_entries=MAX_SUBTAREAS)
    enviar = SubmitField("Guardar")

    def cargar_opciones(self, unidades, catalogos: dict, cargos, tareas_habilitables, ve_todo: bool) -> None:
        """catalogos: {'tipo': [Catalogo…], 'estado': […], …} ya filtrados (activos + el actual)."""
        self.unidad_id.choices = [(u.id, u.nombre) for u in unidades]
        for campo, tipo in (("tipo_id", "tipo"), ("estado_id", "estado"), ("area_id", "area"),
                            ("instancia_id", "instancia"), ("prioridad_id", "prioridad")):
            opciones = [(c.id, c.valor) for c in catalogos[tipo]]
            if campo not in ("tipo_id", "estado_id"):
                opciones = [NINGUNO] + opciones
            getattr(self, campo).choices = opciones
        self.responsable_id.choices = [NINGUNO] + [
            (c.id, (f"{c.unidad.sigla} · " if ve_todo else "") + c.nombre + (f" — {c.persona}" if c.persona else "")
             + ("" if c.activo else " (inactivo)"))
            for c in cargos
        ]
        self.habilita_a_id.choices = [NINGUNO] + [
            (t.id, f"{t.codigo} · {t.asunto[:80]}") for t in tareas_habilitables
        ]

    def datos(self) -> dict:
        """Valores para services.tareas.guardar_tarea."""
        d = {k: v for k, v in self.data.items() if k not in ("csrf_token", "enviar", "subtareas")}
        d["subtareas"] = [s for s in self.subtareas.data]
        return d


class AdjuntoForm(FlaskForm):
    archivo = FileField("Archivo de respaldo")
    enviar = SubmitField("Subir")


class FiltroTareasForm(Form):
    """Filtros del listado (GET, sin CSRF)."""
    texto = StringField("Buscar")
    unidad_id = SelectField("Unidad", coerce=_entero, validate_choice=False)
    tipo_id = SelectField("Tipo", coerce=_entero, validate_choice=False)
    estado_id = SelectField("Estado", coerce=_entero, validate_choice=False)
    prioridad_id = SelectField("Prioridad", coerce=_entero, validate_choice=False)
    responsable_id = SelectField("Responsable", coerce=_entero, validate_choice=False)
    ver_concluidas = BooleanField("Ver concluidas")

    def cargar_opciones(self, unidades, catalogos: dict, cargos, ve_todo: bool) -> None:
        todos = (0, "Todos")
        self.unidad_id.choices = [(0, "Todas")] + [(u.id, u.sigla) for u in unidades]
        self.tipo_id.choices = [todos] + [(c.id, c.valor) for c in catalogos["tipo"]]
        self.estado_id.choices = [todos] + [(c.id, c.valor) for c in catalogos["estado"]]
        self.prioridad_id.choices = [(0, "Todas")] + [(c.id, c.valor) for c in catalogos["prioridad"]]
        self.responsable_id.choices = [todos] + [
            (c.id, (f"{c.unidad.sigla} · " if ve_todo else "") + c.nombre) for c in cargos
        ]
