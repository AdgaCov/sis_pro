# Layout Blocks Contract

**Feature**: 001-mejora-ui-frontend | **Date**: 2026-11-19

Contrato de los bloques Jinja2 que `base.html` expone y que los templates hijos
pueden (o deben) sobreescribir. Ningún template rompe el layout si no sobreescribe
un bloque marcado como «opcional».

## Bloques de `base.html`

| Bloque | Obligatorio | Default | Descripción |
|---|---|---|---|
| `titulo` | Opcional | `Seguimiento MRE` | `<title>` de la página |
| `ancho_contenido` | Opcional | `ancho-wide` | Clase CSS del wrapper interno de contenido |
| `contenido` | Requerido | — | Contenido principal de la vista |
| `scripts` | Opcional | vacío | Scripts JS al final del `<body>` |

### `{% block ancho_contenido %}`

Default en `base.html`:
```jinja2
{% block ancho_contenido %}ancho-wide{% endblock %}
```

Los templates de formulario/detalle sobreescriben:
```jinja2
{% block ancho_contenido %}ancho-form{% endblock %}
```

### `{% block contenido %}`

Sin default. Todos los templates DEBEN implementarlo.

### Ejemplo — template de listado (sin cambio de ancho)

```jinja2
{% extends "base.html" %}
{% block titulo %}Tareas{% endblock %}
{# ancho_contenido omitido → usa 'ancho-wide' por default #}
{% block contenido %}
  ...
{% endblock %}
```

### Ejemplo — template de formulario

```jinja2
{% extends "base.html" %}
{% block titulo %}Nueva tarea{% endblock %}
{% block ancho_contenido %}ancho-form{% endblock %}
{% block contenido %}
  ...
{% endblock %}
```

## Templates y su variante de contenedor

| Template | Variante | Acción requerida |
|---|---|---|
| `inicio.html` | `ancho-wide` | Eliminar `{% block contenedor %}` actual; usar default |
| `tareas/lista.html` | `ancho-wide` | Sin cambio (ya usa container-fluid) |
| `tareas/detalle.html` | `ancho-form` | Añadir `{% block ancho_contenido %}ancho-form{% endblock %}` |
| `tareas/form.html` | `ancho-form` | Añadir `{% block ancho_contenido %}ancho-form{% endblock %}` |
| `tareas/papelera.html` | `ancho-wide` | Sin cambio |
| `tablero/resumen.html` | `ancho-wide` | Sin cambio |
| `tablero/alertas.html` | `ancho-wide` | Sin cambio |
| `tablero/informe.html` | `ancho-wide` | Sin cambio |
| `tablero/cronograma.html` | `ancho-wide` | Sin cambio |
| `tablero/graficos.html` | `ancho-wide` | Sin cambio |
| `agenda/mes.html` | `ancho-wide` | Sin cambio |
| `responsables/lista.html` | `ancho-wide` | Sin cambio |
| `admin/usuarios/lista.html` | `ancho-wide` | Sin cambio |
| `admin/usuarios/form.html` | `ancho-form` | Añadir bloque |
| `admin/invitados/lista.html` | `ancho-wide` | Sin cambio |
| `admin/invitados/form.html` | `ancho-form` | Añadir bloque |
| `admin/plantillas/lista.html` | `ancho-wide` | Sin cambio |
| `admin/plantillas/form.html` | `ancho-form` | Añadir bloque |
| `admin/plantillas/marcadores.html` | `ancho-wide` | Sin cambio |
| `admin/catalogos/lista.html` | `ancho-wide` | Sin cambio |
| `auth/login.html` | centrado propio | No extiende base.html (layout de auth) |
| `auth/cambiar_clave.html` | `ancho-form` | Añadir bloque |
| `errores/error.html` | `ancho-form` | Sin cambio (no tiene sidebar) |

## Bloque eliminado

El bloque `{% block contenedor %}` del `base.html` actual (que definía la clase del
`<main>`) se elimina. Su función queda absorbida por:
- el `<main class="app-contenido">` fijo, y
- el nuevo `{% block ancho_contenido %}` para el wrapper interno.

Los templates que hoy sobreescriben `contenedor` deben migrarse al nuevo bloque.
