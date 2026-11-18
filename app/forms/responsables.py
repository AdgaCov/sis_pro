from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional


class NuevoCargoForm(FlaskForm):
    unidad_id = SelectField("Unidad", coerce=int)
    nombre = StringField("Cargo", validators=[DataRequired("Escriba el cargo."), Length(max=150)])
    persona = StringField("Persona designada (opcional)", validators=[Optional(), Length(max=150)])
    enviar = SubmitField("Agregar cargo")


class PersonaForm(FlaskForm):
    persona = StringField("Persona designada", validators=[Optional(), Length(max=150)])


class MoverCargoForm(FlaskForm):
    unidad_id = SelectField("Mover a", coerce=int)
