# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
cp .env.example .env          # fill in SECRET_KEY and DATABASE_URL
pip install -r requirements.txt
flask db upgrade
flask crear-admin             # first admin (interactive)
flask cargar-catalogos        # loads units, roles, catalog values (safe to re-run)

# Run
flask run --debug

# Tests (use SQLite in-memory by default; no DB required)
pytest
pytest tests/test_auth.py                        # single file
pytest tests/test_tareas.py -k test_crear_tarea  # single test
pytest -x                                        # stop on first failure

# DB checks
flask db check                # verify models match migrations
```

`TEST_DATABASE_URL` env var overrides the in-memory SQLite for tests (e.g. a local MariaDB).

## Architecture patterns

**Permission gateway** — controllers never query `Tarea` directly. All task queries go through `services/permisos.py:consulta_tareas(usuario)`, which applies unit-visibility filtering. `unidades_visibles()` and `puede_ver_tarea/puede_editar_tarea` follow the same pattern. Break this and guest isolation breaks silently.

**ErrorNegocio flow** — services raise `ErrorNegocio("message")` (defined in `services/__init__.py`). Controllers catch it, call `db.session.rollback()`, then `flash(str(e), "danger")`. Models never raise `ErrorNegocio`; models never import services.

**Alert computation** — alerts (`services/alertas.py`) are computed in Python at read time, never persisted. This means you cannot filter or sort by alert in SQL. Alert-filtered lists are paginated in memory via `utils/paginacion.py`. The seven-level priority order is fixed in code; changing thresholds is done in `config.py`.

**Session identity** — `login_manager.user_loader` receives `"{uid}:{version_sesion}"`. Incrementing `version_sesion` on a user record (password reset, role change, deactivation) invalidates all existing sessions for that user without touching the session store.

**`guardas_globales`** (`utils/decoradores.py`) runs as `before_request` on every request: enforces session expiry (absolute 8 h), blocks all guest writes globally (not per-view), and redirects on `debe_cambiar_clave`. The `@solo_lectura` decorator is a belt-and-suspenders guard on individual views, not the primary enforcement.

**Catalog references** — `Tarea` stores foreign keys to `Catalogo` rows for tipo, estado, instancia, prioridad, area. Protected values (`Tarea interna`, `Concluido`, `Alta`) are matched by name in service code — do not rename them in the database. Deactivating a catalog value removes it from forms but leaves existing tasks intact.

---

# Seguimiento MRE · Bolivia en el Mundo

App web para que las unidades de Bolivia en el Mundo registren sus tareas y trámites con el MRE,
y para que Planificación y la DGE vean todo con alertas, cronograma, informes y descargas.
Es la migración de una app en Google Apps Script (ver `referencias/`) a Python.

## Stack
- Python 3.11+, Flask (application factory + blueprints)
- Flask-SQLAlchemy, Flask-Migrate (Alembic), PyMySQL → MariaDB 10.6+
- Flask-Login (sesiones), Flask-WTF (formularios + CSRF), python-dotenv
- Jinja2 + Bootstrap 5 (sin frameworks JS; JS mínimo en `static/js/`)
- Todos los PDF salen de las plantillas que sube el admin (no hay PDF propio del sistema). La conversión Word/Excel → PDF
  es Python puro (`services/pdf.py`: python-docx/openpyxl leen, `reportlab` dibuja); **no se usa LibreOffice ni Word**
- Chart.js 4.4.1 (CDN) solo en la vista Gráficos: única excepción a «sin frameworks JS»
- Plantillas: `docxtpl` (Word) y `openpyxl` (Excel); su PDF con `services/pdf.py` (reportlab)
- Tests: pytest (SQLite en memoria; `TEST_DATABASE_URL` para usar otra base)

## Idioma y estilo
- Interfaz, mensajes, nombres de tablas, modelos, rutas y variables **en español** (sin tildes en identificadores).
- Fechas en pantalla: dd/mm/aaaa. Zona horaria: America/La_Paz. En la base se guarda UTC (`utils/fechas.py`).
- Controladores cortos: la lógica va en `app/services/`. Los modelos no importan servicios.
- Los servicios lanzan `ErrorNegocio` con un mensaje apto para el usuario; el controlador hace `rollback` y lo muestra con `flash`.
- Nunca confiar en la interfaz para permisos: todo se valida en el servidor (también dentro de los servicios).
- Lo que el usuario no puede ver responde **404** (no revela que existe); lo que ve pero no puede hacer, **403**.
- Toda acción que modifica datos registra una fila en `auditoria`.

## Estructura
```
seg_pro/
├── run.py · config.py · .env.example · requirements.txt
├── migrations/versions/   # 0001 esquema inicial · 0002 invitado solo resumen · 0003 plantillas · 0004 plantillas del tablero
├── referencias/           # código Apps Script original (solo lectura, no se ejecuta)
├── storage/               # fuera de static/, no se sirve directo
│   ├── respaldos/<SIGLA>/<id_tarea>/   # adjuntos
│   ├── plantillas/                     # plantillas subidas (<uuid>.docx|xlsx)
├── tests/
└── app/
    ├── __init__.py        # create_app(), blueprints, filtros |fecha y |fecha_hora, errores
    ├── cli.py             # crear-admin, cargar-catalogos
    ├── datos_iniciales.py # unidades, cargos y catálogos iniciales
    ├── extensions.py      # db, migrate, login_manager, csrf
    ├── models/            # usuario, unidad (+cargo), tarea (+subtarea, adjunto), catalogo,
    │                      # permiso_invitado, plantilla, auditoria
    ├── controllers/       # auth, inicio, tareas, responsables, tablero, agenda, documentos,
    │                      # admin/{usuarios, invitados, plantillas, catalogos}
    ├── services/          # permisos, usuarios, tareas, responsables, archivos, alertas, resumen,
    │                      # invitados, plantillas, pdf, imagenes, catalogos, agenda, graficos, auditoria
    ├── forms/             # auth, usuarios, tareas, responsables, invitados, plantillas
    ├── utils/             # decoradores (@rol_requerido, @solo_lectura), fechas, paginacion
    ├── templates/         # base.html, _macros.html, auth/, tareas/, tablero/, agenda/, responsables/, admin/
    └── static/            # css/app.css · js/{confirmar, subtareas, imprimir, invitados, graficos}.js
```

## Rutas principales
| Ruta | Quién | Qué |
|---|---|---|
| `/` | todos menos invitado | Inicio con indicadores (el invitado va al resumen) |
| `/tareas` · `/tareas/nueva` · `/tareas/<id>` | admin, supervisor, unidad | Listado con filtros, alta, detalle, edición, subtareas, adjuntos |
| `/tareas/papelera` | admin | Copias de tareas eliminadas |
| `/responsables` | admin, supervisor, unidad | Cargos y persona designada |
| `/tablero/resumen` · `/tablero/resumen.pdf` | todos | Resumen ejecutivo y su PDF |
| `/agenda` · `/agenda/agenda.pdf` | todos | Agenda Despacho del mes (`?mes=AAAA-MM`) y su PDF |
| `/tablero/graficos` · `/tablero/graficos.pdf` | todos | Tablero con gráficos y su PDF |
| `/tablero/alertas` · `/informe` · `/informe.pdf` · `/cronograma` | admin, supervisor, unidad | Vistas del tablero (el informe crítico, con su PDF) |
| `/documentos/<plantilla>/{tarea/<id>, listado, informe, resumen, agenda, graficos}` | admin, supervisor, unidad | Llena la plantilla (`?formato=original\|pdf`); la interfaz siempre pide PDF |
| `/admin/{usuarios, invitados, plantillas, catalogos}` | admin | Administración |

## Roles y permisos
Cada persona tiene su propio usuario y contraseña, ligado a una unidad (salvo admin/supervisor/invitado, que pueden no tener).

| Rol | Ve | Puede |
|---|---|---|
| `admin` (Planificación) | Todo | Todo: tareas de cualquier unidad, reasignar tareas, mover cargos, usuarios, invitados, plantillas, catálogos, papelera |
| `supervisor` (DGE) | Todo | Editar tareas de cualquier unidad, reasignarlas y gestionar cargos (sin moverlos). No administra usuarios, invitados, plantillas ni catálogos |
| `unidad` | Solo su unidad | Crear/editar/eliminar sus tareas, adjuntos, subtareas y cargos de su unidad; generar documentos |
| `invitado` | Resumen ejecutivo, Agenda y Gráficos, solo gestiones con el MRE de las unidades que el admin configure | Leerlos y descargarlos en PDF. Nunca modifica nada |

- **Contraseñas:** hash con `werkzeug.security`. Mínimo 8 caracteres con letras y números.
- **Crear usuario:** el admin escribe la contraseña inicial (con confirmación). Opcionalmente marca «pedir cambio al primer ingreso» (`debe_cambiar_clave`); por defecto no. Al crear un invitado se pasa a configurar sus unidades.
- **Restablecer:** solo el admin, desde Usuarios. Pone una clave temporal → `debe_cambiar_clave = True` → al entrar se obliga a cambiarla. No hay recuperación por correo.
- **Bloqueo:** 5 intentos fallidos → 15 minutos bloqueado. Sesión de 8 horas (absoluta, no se renueva).
- Al restablecer la clave, cambiar rol/unidad o desactivar a un usuario, se invalidan sus sesiones abiertas (`version_sesion`).
- Siempre debe existir al menos un admin activo.

### Invitado
Solo ve tres vistas (`VISTAS_INVITADO` en `models/permiso_invitado.py`), cada una con su PDF (la plantilla del admin):
**resumen ejecutivo**, **agenda** y **gráficos**. En las tres ve solo gestiones con el MRE (nunca tareas internas;
`permisos.solo_gestiones_mre`) y sin enlaces al detalle de las tareas.
No ve tareas, alertas, informe, cronograma, responsables ni adjuntos; de las plantillas solo descarga las de sus tres vistas,
llenadas con los mismos datos filtrados que ve en pantalla.
Tabla `permiso_invitado` por usuario invitado: unidades permitidas (`todas_unidades` o una lista). Sin unidades no ve datos.
Se configura en Admin › Invitados. Cada descarga de PDF (de cualquier usuario) queda en la auditoría (`descargar_pdf`).

`@solo_lectura` y la guarda global rechazan con 403 cualquier POST/PUT/PATCH/DELETE de un invitado (excepto logout y cambiar su propia clave).
`services/permisos.py` filtra las consultas: ningún controlador consulta tareas sin pasar por ahí
(`consulta_tareas`, `unidades_visibles`, `puede_ver_vista`, `puede_editar_tarea`, `puede_ver_adjuntos`…).

## Reglas de negocio (vienen de la app original)
- **Unidades:** DGE-STAF, UAF, UPT, UDTP, UEP, SISTEMAS.
- **Código de tarea:** `<SIGLA>-<NNN>` correlativo por unidad (UAF-001), reservado con bloqueo de fila; no se reutiliza tras eliminar. Al reasignar a otra unidad (solo admin/supervisor) recibe código nuevo de destino; `habilita_a` guarda el id, así que las referencias siguen válidas.
- **Tipos:** `Tarea interna` (no entra al resumen ejecutivo), `Solicitud al MRE`, `Autorización del MRE`, `Gestión con el MRE (habilita otra tarea)`.
- **Estados:** Pendiente, En proceso, Remitido a DGE, Con V.º B.º de DGE, Ingresado por Ventanilla Única, Remitido a instancia del MRE, En instancia del MRE – Sin respuesta, Observado / Devuelto, Respuesta recibida del MRE, Autorizado, Concluido, Otro.
- Al pasar a **Concluido** sin fecha de conclusión, se pone la de hoy. La fecha límite no puede ser anterior a la de solicitud.
- **Responsable = cargo**, no persona. Cada cargo tiene una persona designada (opcional). Cada unidad tiene un cargo `Apoyo` para asignaciones provisionales (no se desactiva ni se mueve). Admin/supervisor pueden asignar un cargo de otra unidad. Solo el admin mueve cargos entre unidades.
- **Dependencias:** `habilita_a` apunta a otra tarea. Una unidad solo puede apuntar a tareas de su propia unidad. Una tarea no puede habilitarse a sí misma.
- **Subtareas:** texto (≤300), fecha opcional, hecho sí/no. Máximo 40 por tarea.
- **Adjuntos:** máx. 10 MB por archivo, extensiones de `EXTENSIONES_ADJUNTO` en `config.py`, en `storage/respaldos/<SIGLA>/<id>/`; descarga solo con permiso sobre la tarea (nunca el invitado).
- **Eliminar tarea:** se copia a la papelera (auditoría, acción `eliminar_tarea`) y se limpian las referencias `habilita_a`. Los archivos adjuntos quedan en disco y su ruta se guarda en la copia.
- Registrar `actualizado_en` y `actualizado_por` en cada cambio.

### Catálogos (Admin › Catálogos)
Tipos, estados, instancias, prioridades y áreas. Las tareas guardan el id del valor: renombrar se refleja en todas.
- Valores **protegidos** (`Tarea interna`, `Concluido`, `Alta`): no se renombran, desactivan ni eliminan (la lógica los usa por nombre).
- Desactivar un valor lo quita de los formularios; las tareas que lo tienen lo conservan.
- Solo se elimina un valor que ninguna tarea usa. Tipos y estados conservan al menos un valor activo.

### Alertas (se calculan al leer, NO se guardan — `services/alertas.py`)
Primera que se cumpla, en este orden:
1. `CONCLUIDO` — estado = Concluido
2. `VENCIDO` — fecha límite < hoy
3. `CRÍTICO` — prioridad Alta y > 15 días desde la solicitud
4. `POR VENCER` — faltan ≤ 3 días para la fecha límite
5. `SIN FECHA` — sin fecha de solicitud
6. `SEGUIMIENTO` — > 7 días desde la solicitud
7. `EN CURSO` — el resto

Señales adicionales: sin actualizar > 7 días, subtareas vencidas, bloquea otra tarea, sin responsable, sin fecha límite, crítica sin línea de solución, concluida sin medio de verificación.
**Tarea crítica** (informe): abierta y (VENCIDO o CRÍTICO o riesgo Alto o (prioridad Alta y POR VENCER)).
Los umbrales van en `config.py`: `DIAS_POR_VENCER`, `DIAS_SEGUIMIENTO`, `DIAS_SIN_ACTUALIZAR`, `DIAS_CRITICO`.
Los listados se ordenan por severidad; como la alerta se calcula en Python, se filtra y pagina en memoria (`utils/paginacion.py`).

### Tablero (`services/resumen.py`)
- **Resumen ejecutivo:** solo gestiones con el MRE. Indicadores y cuadros (por unidad, instancia, tipo) muestran todo lo visible; los filtros aplican al detalle y al PDF.
- **Alertas:** 10 grupos (una tarea puede salir en varios). Filtros: unidad y responsable.
- **Informe crítico:** tareas críticas por unidad, con línea de solución; botón Imprimir.
- **Cronograma:** barras calculadas en el servidor (posiciones en %), dibujadas solo con CSS.

### Agenda Despacho (`services/agenda.py`) — Etapa 6
Sección propia de la app (ya no se conecta con Google Sheets). Se arma con los datos de las tareas, sin datos propios:
- Eventos: **fecha límite** de cada tarea abierta (◆) y **recordatorios** = subtareas con fecha (•; las hechas, tachadas).
- En pantalla, tres calendarios (lunes a domingo): mes anterior, el elegido (al centro, con los indicadores) y el siguiente;
  cada día coloreado con su peor alerta y el código de cada evento (detalle en el tooltip); navegación por mes; «Próximos 14 días».
- Estado de agenda (como la app original): Concluido → Concluida, Pendiente → Pendiente, Observado / Devuelto → Bloqueada, el resto → En gestión.
- Filtros: unidad y responsable. PDF del mes: la plantilla de alcance `agenda`.

### Gráficos (`services/graficos.py`, `static/js/graficos.js`)
Un gráfico por pregunta. Los datos los arma el servidor (ya filtrados por permisos) y se pasan como JSON en la página:
| Bloque | Pregunta |
|---|---|
| Tarjetas: pendientes, vencidas, por vencer, sin respuesta del MRE, concluidas del mes (± % vs. mes anterior) | ¿Cómo estamos hoy? |
| Barras apiladas por unidad y alerta (solo si ve varias unidades) / «Próximos vencimientos» (unidad) | ¿Qué unidad está más atrasada? |
| Velocímetro: % concluidas a tiempo, con marca de meta `META_CUMPLIMIENTO` | ¿Cumplimos los plazos? |
| Línea: creadas contra concluidas, 12 meses | ¿Entra más trabajo del que cerramos? |
| Embudo: tareas abiertas por estado (orden del catálogo) | ¿Dónde se traban los trámites? |
| Mini calendario del mes (enlaza a la Agenda) | ¿Qué vence este mes? |
| Instancias del MRE con más pendientes | ¿A quién hay que insistir? |
| Anillos de cumplimiento por unidad (solo si ve varias unidades) | Comparación entre unidades |

- Colores de alerta en 4 familias: rojo (vencido/crítico), ámbar (por vencer/seguimiento), azul (en curso), gris (sin fecha); verde = concluido/cumple.
- Al pulsar un gráfico se abre la lista de tareas ya filtrada (solo si el usuario puede ver tareas; el invitado no).
- PDF: la plantilla de alcance `graficos` (en Word, los gráficos van como imagen con `{{ imagen.* }}`).
- «Cuántas vencidas había cada día» no se puede graficar porque las alertas no se guardan; si se necesita, haría falta una tabla `foto_diaria` y un comando nocturno.

## Plantillas con marcadores (Admin › Plantillas)
El admin sube `.docx` o `.xlsx` (máx. 10 MB) a `storage/plantillas/` e indica su **alcance**: `tarea` (ficha), `listado` (lo que muestra el filtro),
`informe` (solo tareas críticas), `resumen` (resumen ejecutivo), `agenda` (Agenda Despacho del mes) o `graficos` (tablero; también desde el Inicio).
**Solo se descargan las plantillas que sube el admin**, siempre en PDF. Cada vista tiene un solo botón «Descargar PDF»
(no hay menú «Generar documento» ni PDF propio del sistema), y aparece solo si hay una plantilla activa de ese alcance
(la editada más recientemente, `plantillas.vigente_para`). Las rutas `*.pdf` (`documentos.descargar_pdf`) redirigen a
`/documentos/...?formato=pdf`; sin plantilla vuelven a la vista con un aviso.
La ficha también tiene botón por fila en Tareas. El invitado descarga las de sus tres vistas (los permisos de cada ruta lo validan).
- Word: `docxtpl` con `jinja2.sandbox.SandboxedEnvironment` y autoescape. Listas con `{% for t in tareas %}…{% endfor %}`; en tablas, `{%tr for t in tareas %}` repite la fila.
- Excel: `openpyxl`, reemplaza `{{ marcador }}` en celdas; una fila con marcadores `{{ t.xxx }}` se repite por cada tarea conservando el formato.
  Otras listas con su letra (`FILAS_EXCEL`): `u.` por_unidad, `i.` por_instancia, `p.` por_tipo, `e.` eventos, `m.` mensual, `f.` embudo.
  Una celda con un solo marcador numérico queda como número. Las fórmulas debajo de la fila repetida no se ajustan.
- Gráficos en Word: `{{ imagen.barras }}`, `{{ imagen.cumplimiento }}`, `{{ imagen.mensual }}`, `{{ imagen.embudo }}` → PNG dibujados con Pillow (`services/imagenes.py`, fuente Vera de reportlab).
- Al subir: se validan los marcadores contra `MARCADORES` (en `services/plantillas.py`, visible en Admin › Plantillas › Marcadores) y se listan los desconocidos (quedan vacíos al generar). Una sintaxis inválida rechaza el archivo. Botón «Probar» con datos de ejemplo.
- Se descargan con «Descargar PDF»: ficha (detalle de tarea), listado (Tareas, con los filtros), informe (Informe crítico),
  resumen, agenda (mes elegido) y gráficos (Gráficos e Inicio), con los permisos y filtros de cada vista. El invitado solo resumen, agenda y gráficos.
- Los marcadores están agrupados por documento en `GRUPOS_MARCADORES` (Admin › Plantillas › Marcadores).
- Salida: PDF dibujado en Python (`pdf.convertir_a_pdf`); `?formato=original` (Word/Excel) queda solo para pruebas.
  Word: fuentes, negrita/cursiva/subrayado, colores, tamaños, alineación, sangrías, espaciado, «conservar con el siguiente»,
  viñetas y numeración, tablas (anchos, celdas combinadas, fondos, bordes, filas de encabezado), imágenes, saltos de página,
  encabezado y pie (tabuladores a la derecha/centro y nº de página «Página X de Y»).
  Excel: cada hoja visible en su página, anchos/altos, combinadas, fondos, bordes, fuente, alineación, formatos de número;
  se ajusta al ancho (horizontal si conviene). Fórmulas: solo sencillas (FILA, SUMA, CONTAR, PROMEDIO, MIN, MAX, REDONDEAR,
  + − × ÷ con celdas); las demás quedan vacías.
  **No se dibujan:** gráficos e imágenes de Excel, formas y cuadros de texto de Word, imágenes EMF/WMF. Para gráficos use
  Word con `{{ imagen.* }}`. Fuentes: las del sistema (Calibri, Arial…; en Linux Carlito/Liberation) o Vera de reportlab.

La lista completa está en `MARCADORES` (`services/plantillas.py`); abajo, la guía de cada documento.

### Guía: cómo armar cada documento

#### Pasos (para cualquier documento)
1. Abra Word o Excel y diseñe el documento como quiera (logo, títulos, colores, tablas). Donde va un dato, escriba el
   marcador entre llaves dobles, por ejemplo `{{ unidad.nombre }}`. Escríbalo de una sola vez (si lo corrige letra por
   letra, Word puede partirlo por dentro y deja de reconocerlo).
2. Admin › Plantillas › Nueva: nombre, alcance (el documento que es) y el archivo `.docx` o `.xlsx`.
3. Si aparece «Marcadores desconocidos», hay un nombre mal escrito: quedará vacío. Corríjalo y vuelva a subir el archivo
   (Editar). Una sintaxis inválida (`{{` sin cerrar, `{% for %}` sin `endfor`) rechaza el archivo.
4. «Probar» lo llena con datos de ejemplo. Luego se descarga en PDF desde la vista con «Descargar PDF».
   El archivo se llama `<nombre de la plantilla>_<código, AAAAMMDD o AAAA_MM>.docx|xlsx|pdf`.

#### Reglas comunes

| Quiero… | Word (.docx) | Excel (.xlsx) |
|---|---|---|
| Un dato | `{{ unidad.nombre }}` en cualquier párrafo, celda, encabezado o pie | `{{ unidad.nombre }}` en una celda (puede ir con texto: `Unidad: {{ unidad.sigla }}`) |
| Repetir filas de tabla | 3 filas: 1.ª `{%tr for t in tareas %}`, 2.ª las celdas con `{{ t.codigo }}`, `{{ t.asunto }}`…, 3.ª `{%tr endfor %}` (la 1.ª y la 3.ª desaparecen) | Una fila con `{{ t.codigo }}`, `{{ t.asunto }}`…: se repite sola, una por tarea, con el mismo formato. Sin `for` |
| Repetir párrafos | Párrafo solo con `{%p for t in tareas %}`, los párrafos a repetir, párrafo solo con `{%p endfor %}` | — |
| Lista dentro de un texto | `{% for s in tarea.subtareas %}{{ s.texto }}; {% endfor %}` en un mismo párrafo | Igual, en una celda |
| Numerar | `{{ loop.index }}` dentro del `for` | `loop.index` no funciona: use una fórmula, p. ej. `=FILA()-4` |
| Mostrar si se cumple | `{% if t.alerta == 'VENCIDO' %}¡Vencida!{% endif %}` · `{% if tarea.solucion %}…{% else %}Sin definir{% endif %}` | Igual, dentro de la celda |
| Mayúsculas / recortar | `{{ t.asunto\|upper }}` · `{{ t.asunto\|truncate(80) }}` · `{{ t.persona or '—' }}` | Igual |

- **En los ejemplos de abajo, `|` separa celdas (una columna por dato) y `/` separa filas de la tabla**: no se escriben en la plantilla.
- **Letra de cada lista en Excel** (la fila se repite por la lista de su letra): `t.` tareas · `u.` por_unidad ·
  `i.` por_instancia · `p.` por_tipo · `e.` eventos · `m.` mensual · `f.` embudo. **Una sola lista por fila**: si una
  fila mezcla `u.` y `e.`, solo se repite la primera y la otra queda vacía.
- Una celda de Excel que tiene **solo** un marcador numérico (`{{ resumen.total }}`, `{{ u.pendientes }}`) queda como
  número (sirve para sumas y gráficos de Excel); con texto alrededor queda como texto.
- Las fórmulas de Excel **debajo** de una fila que se repite no ajustan su rango: póngalas arriba o use `resumen.*`.
- En Word la variable del `for` puede tener cualquier nombre (`t`, `x`, `fila`); en Excel debe ser la letra de la tabla.
- Fechas ya vienen como `dd/mm/aaaa`; textos vacíos salen vacíos (no «None»).

#### Marcadores generales (sirven en los seis documentos)

| Marcador | Qué trae |
|---|---|
| `unidad.nombre` · `unidad.sigla` | Ficha: la unidad de la tarea. Resto: la unidad filtrada; sin filtro, la del usuario si ve una sola; si ve varias, «Todas las unidades» (sigla vacía) |
| `generado.fecha` · `generado.por` | Fecha y hora de la descarga · usuario que la hizo |
| `generado.filtros` | Filtros aplicados en la vista (listado, resumen, agenda). Vacío en ficha, informe y gráficos |
| `resumen.total` · `.pendientes` · `.vencidas` · `.por_vencer` · `.criticas` · `.sin_solucion` · `.concluidas` | Conteos sobre la lista `tareas` **de ese documento** (no sobre todo el sistema) |
| `tareas` | Lista de tareas del documento (qué contiene depende del documento, ver cada uno) |

**Campos de cada tarea** — `tarea.xxx` en la ficha; `t.xxx` (o la variable del `for`) en las listas:
`codigo` (UAF-001) · `unidad` (sigla) · `unidad_nombre` · `tipo` · `area` · `instancia` · `asunto` · `gestion`
(gestión requerida) · `que_habilita` · `habilita_a` (código de la tarea que habilita) · `riesgo_demora` · `responsable`
(cargo) · `persona` (designada en el cargo) · `hoja_ruta` · `fecha_solicitud` · `fecha_limite` · `fecha_conclusion` ·
`estado` · `prioridad` · `alerta` (VENCIDO, CRÍTICO, POR VENCER, SEGUIMIENTO, SIN FECHA, EN CURSO, CONCLUIDO) · `dias`
(desde la solicitud, número) · `faltan` (hasta la fecha límite; negativo = vencida; vacío si está concluida) ·
`nivel_riesgo` (Alto/Medio/Bajo) · `solucion` (línea de solución) · `plazo_solucion` · `resultado` ·
`medio_verificacion` · `observaciones` · `actualizado` (dd/mm/aaaa hh:mm) · `subtareas` (lista: `s.texto`, `s.fecha`,
`s.hecho` = Sí/No).

#### 1. Ficha de una tarea — alcance `tarea`
- **Se descarga en:** detalle de la tarea › Descargar PDF (o el botón PDF de cada fila de Tareas). **Trae:** esa tarea (`tareas` tiene solo esa).
- **Use:** `tarea.xxx` (todos los campos de arriba), `tarea.subtareas`, `unidad.*`, `generado.*`.
- **Word:** título `Ficha {{ tarea.codigo }}`; tabla de 2 columnas con etiqueta y dato (`Asunto | {{ tarea.asunto }}`,
  `Responsable | {{ tarea.responsable }} ({{ tarea.persona }})`, `Fecha límite | {{ tarea.fecha_limite }}`,
  `Alerta | {{ tarea.alerta }}`…); tabla de pasos: `{%tr for s in tarea.subtareas %}` / `{{ s.texto }} | {{ s.fecha }} | {{ s.hecho }}` / `{%tr endfor %}`.
- **Excel:** etiquetas en la columna A y `{{ tarea.xxx }}` en la B. Las subtareas no se repiten por filas: póngalas en
  una celda con `{% for s in tarea.subtareas %}{{ s.texto }} ({{ s.hecho }}); {% endfor %}`.

#### 2. Listado — alcance `listado`
- **Se descarga en:** Tareas › Descargar PDF. **Trae:** exactamente lo que muestra el filtro (todas las páginas),
  de la más grave a la menos grave; sin «Ver concluidas», solo abiertas.
- **Use:** `tareas` con `t.xxx`, `resumen.*` (conteos del listado), `unidad.*`, `generado.filtros` (p. ej.
  «Unidad: UAF · Alerta: VENCIDO · solo abiertas»).
- **Word:** encabezado `Listado de {{ unidad.nombre }} — {{ generado.fecha }}` y `Filtros: {{ generado.filtros }}`;
  tabla `{%tr for t in tareas %}` / `{{ loop.index }} | {{ t.codigo }} | {{ t.asunto }} | {{ t.responsable }} | {{ t.fecha_limite }} | {{ t.alerta }}` / `{%tr endfor %}`;
  al final `Total: {{ resumen.total }} · vencidas: {{ resumen.vencidas }}`.
- **Excel:** fila 1 título; fila 3 encabezados; fila 4 `{{ t.codigo }} | {{ t.asunto }} | {{ t.estado }} | {{ t.fecha_limite }} | {{ t.faltan }} | {{ t.alerta }}`
  (se repite); totales arriba con `{{ resumen.total }}`.
- No use `tarea.xxx` aquí: es solo la primera de la lista.

#### 3. Informe crítico — alcance `informe`
- **Se descarga en:** Informe crítico › Descargar PDF. **Trae:** solo tareas
  críticas abiertas (vencidas, críticas, riesgo alto o alta prioridad por vencer), filtradas por unidad.
- **Use:** `tareas` con `t.xxx` — sobre todo `t.alerta`, `t.nivel_riesgo`, `t.riesgo_demora`, `t.solucion`,
  `t.plazo_solucion`, `t.responsable`, `t.persona`, `t.faltan` —, `resumen.criticas`, `resumen.sin_solucion`, `unidad.*`.
- **Word:** `Informe de tareas críticas — {{ unidad.nombre }}`; `{{ resumen.criticas }} críticas, {{ resumen.sin_solucion }} sin línea de solución`;
  tabla `{%tr for t in tareas %}` / `{{ t.codigo }} | {{ t.asunto }} | {{ t.alerta }} | {% if t.solucion %}{{ t.solucion }}{% else %}SIN DEFINIR{% endif %} | {{ t.plazo_solucion }}` / `{%tr endfor %}`.
- **Excel:** fila repetida `{{ t.codigo }} | {{ t.unidad }} | {{ t.asunto }} | {{ t.alerta }} | {{ t.riesgo_demora }} | {{ t.solucion }} | {{ t.plazo_solucion }}`.

#### 4. Resumen ejecutivo — alcance `resumen`
- **Se descarga en:** Resumen › Descargar PDF. **Trae:** solo gestiones con el MRE (nunca tareas internas).
  Como en la pantalla, los indicadores y cuadros cuentan **todo lo visible**; los filtros solo cambian `tareas` (el detalle).

| Marcador | Qué trae |
|---|---|
| `indicadores.total_mre` · `.pendientes` · `.vencidas` · `.sin_respuesta` · `.alta_prioridad` | Las tarjetas de arriba de la vista |
| `por_unidad` → `u.sigla` · `u.nombre` · `u.total` · `u.pendientes` · `u.vencidas` · `u.alta` · `u.sin_respuesta` · `u.concluidas` | Cuadro «Gestiones por unidad» (todas las unidades visibles, aunque tengan 0) |
| `por_instancia` → `i.nombre` · `i.pendientes` | Pendientes por instancia del MRE, de más a menos («Sin instancia» incluida) |
| `por_tipo` → `p.nombre` · `p.pendientes` | Pendientes por tipo |
| `tareas` → `t.xxx` | Detalle consolidado, con los filtros de la vista |

- **Word:** párrafo `Total {{ indicadores.total_mre }} · pendientes {{ indicadores.pendientes }} · vencidas {{ indicadores.vencidas }}`;
  tabla por unidad `{%tr for u in por_unidad %}` / `{{ u.nombre }} | {{ u.total }} | {{ u.pendientes }} | {{ u.vencidas }} | {{ u.concluidas }}` / `{%tr endfor %}`;
  otra para instancias (`i`), otra para tipos (`p`) y la del detalle (`t`).
- **Excel:** una hoja o bloque por cuadro: fila `{{ u.sigla }} | {{ u.total }} | {{ u.pendientes }} | {{ u.vencidas }}`;
  más abajo fila `{{ i.nombre }} | {{ i.pendientes }}`; más abajo fila `{{ t.codigo }} | {{ t.asunto }} | {{ t.estado }}`.
  Cada fila repetida empuja hacia abajo lo que está debajo. Para un gráfico de Excel, apúntelo a la columna de `u.pendientes`.

#### 5. Agenda Despacho — alcance `agenda`
- **Se descarga en:** Agenda › Descargar PDF del mes. **Trae:** el mes elegido en pantalla (el del centro), con los filtros
  de unidad y responsable.

| Marcador | Qué trae |
|---|---|
| `mes.nombre` · `mes.desde` · `mes.hasta` | «Noviembre 2026» · 01/11/2026 · 30/11/2026 |
| `indicadores.fechas_limite` · `.vencidas` · `.recordatorios_pendientes` · `.recordatorios_vencidos` · `.bloqueadas` | Las tarjetas de la vista, del mes |
| `eventos` → `e.fecha` · `e.dia` (Lunes…) · `e.tipo` (Fecha límite / Recordatorio) · `e.codigo` · `e.unidad` · `e.texto` (asunto o texto del recordatorio) · `e.asunto` (de la tarea) · `e.responsable` · `e.persona` · `e.estado` · `e.estado_agenda` (Pendiente, En gestión, Bloqueada, Concluida) · `e.alerta` · `e.hecho` (Sí/No) | Cada fecha límite de tarea abierta y cada subtarea con fecha del mes, por fecha (primero las fechas límite) |
| `tareas` → `t.xxx` | Las tareas que tienen algún evento en el mes |

- **Word:** `Agenda Despacho — {{ mes.nombre }}`; tabla `{%tr for e in eventos %}` / `{{ e.dia }} {{ e.fecha }} | {{ e.tipo }} | {{ e.codigo }} | {{ e.texto }} | {{ e.responsable }} | {{ e.estado_agenda }}` / `{%tr endfor %}`.
- **Excel:** fila 1 `Agenda {{ mes.nombre }}`; fila 3 `{{ e.fecha }} | {{ e.dia }} | {{ e.tipo }} | {{ e.codigo }} | {{ e.texto }} | {{ e.alerta }} | {{ e.hecho }}`.
  Use el formato condicional de Excel sobre la columna de `e.alerta` para colorear las vencidas.

#### 6. Tablero con gráficos — alcance `graficos`
- **Se descarga en:** Gráficos o Inicio › Descargar PDF. **Trae:** lo mismo que dibuja la pantalla (con el filtro de unidad).

| Marcador | Qué trae |
|---|---|
| `indicadores.pendientes` · `.vencidas` · `.por_vencer` · `.sin_respuesta` · `.concluidas_mes` | Las tarjetas «¿Cómo estamos hoy?» |
| `indicadores.variacion` | % de concluidas contra el mes anterior (vacío si el mes anterior tuvo 0) |
| `cumplimiento.porcentaje` · `.base` · `.meta` | % concluidas a tiempo · cuántas concluidas con fecha límite · meta (`META_CUMPLIMIENTO`) |
| `por_unidad` → `u.sigla` · `u.nombre` · `u.pendientes` · `u.vencido` · `u.critico` · `u.por_vencer` · `u.seguimiento` · `u.en_curso` · `u.sin_fecha` · `u.cumplimiento` | Pendientes por unidad divididas por alerta (las barras) y % a tiempo (los anillos; vacío sin datos) |
| `mensual` → `m.mes` (nov 26) · `m.creadas` · `m.concluidas` | Los 12 meses de la línea, del más antiguo al actual |
| `embudo` → `f.estado` · `f.tareas` | Abiertas por estado, en el orden del catálogo (solo estados con tareas) |
| `por_instancia` → `i.nombre` · `i.pendientes` | Las 8 instancias del MRE con más gestiones pendientes |
| `imagen.barras` · `imagen.cumplimiento` · `imagen.mensual` · `imagen.embudo` | **Solo Word:** los gráficos como imagen (16 cm de ancho; el velocímetro 8 cm). En Excel quedan vacíos |
| `tareas` → `t.xxx` | Las tareas abiertas |

- **Word:** cada gráfico en su propio párrafo: `{{ imagen.barras }}`; debajo, si quiere los números, una tabla
  `{%tr for u in por_unidad %}` / `{{ u.sigla }} | {{ u.vencido }} | {{ u.por_vencer }} | {{ u.en_curso }} | {{ u.pendientes }}` / `{%tr endfor %}`;
  `Cumplimiento: {{ cumplimiento.porcentaje }} % (meta {{ cumplimiento.meta }} %)`.
- **Excel:** tablas de datos para graficar en Excel: fila `{{ m.mes }} | {{ m.creadas }} | {{ m.concluidas }}` (12 filas)
  y arme sobre ellas un gráfico de líneas; fila `{{ f.estado }} | {{ f.tareas }}` para un gráfico de barras.
  El gráfico de Excel se conserva, pero **su rango no crece solo**: con `mensual` (siempre 12 filas) defina el rango de
  las 12 filas desde ya (p. ej. B5:B16 si la fila del marcador es la 5); con listas de largo variable (`embudo`,
  `por_unidad`) use un rango amplio (las filas sobrantes salen como espacios vacíos al final del gráfico). Ponga el gráfico a la derecha de la tabla, no
  debajo: las filas repetidas bajan el contenido, pero el gráfico queda fijo y lo taparían.

## Configuración (`config.py` y `.env`)
- `.env`: `APP_CONFIG`, `SECRET_KEY`, `DATABASE_URL`, `SESSION_COOKIE_SECURE`, `STORAGE_DIR` (opcional).
- `config.py`: sesión y bloqueo (`HORAS_SESION`, `MAX_INTENTOS`, `MINUTOS_BLOQUEO`), umbrales de alertas, `META_CUMPLIMIENTO`, `MAX_MB_ADJUNTO`, `EXTENSIONES_ADJUNTO`, `TAREAS_POR_PAGINA`.

## Comandos
```
pip install -r requirements.txt
flask db upgrade                 # aplicar migraciones
flask crear-admin                # crea el primer admin (pide usuario y clave)
flask cargar-catalogos           # carga catálogos, unidades y cargos iniciales (se puede repetir)
flask run --debug
pytest
flask db check                   # verifica que modelos y migraciones coincidan
```

## Etapas
1. ✅ Modelos, migración inicial, comandos CLI, login con roles (incluido invitado) y admin de usuarios.
2. ✅ Tareas: CRUD, responsables, subtareas, dependencias, adjuntos, papelera.
3. ✅ Tablero: resumen ejecutivo, alertas, informe crítico, cronograma, filtros.
4. ✅ Invitados: configuración de unidades y vistas de solo lectura con PDF.
5. ✅ Plantillas: subida, validación, generación Word/Excel/PDF. ✅ Administración de catálogos.
6. ✅ Agenda Despacho como sección de la app (sin Google Sheets) para todos los roles, con PDF. ✅ Tablero con gráficos y su PDF.
   (El campo `tarea.agenda_id` quedó de la integración anterior y no se usa.)

Cada etapa termina con tests de permisos: una unidad no ve otra unidad, un invitado no puede escribir.
Tests por área: `test_auth`, `test_usuarios`, `test_permisos`, `test_tareas`, `test_responsables`, `test_tablero`, `test_invitados`, `test_plantillas`, `test_catalogos`, `test_agenda_graficos`, `test_cli`.
