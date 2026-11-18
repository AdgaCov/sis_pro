# Seguimiento MRE · Bolivia en el Mundo

App web para que las unidades de Bolivia en el Mundo registren sus tareas y trámites con el MRE,
y para que Planificación y la DGE vean todo con alertas, cronograma, informes y descargas.
Es la migración de una app en Google Apps Script (ver `referencias/`) a Python.

## Stack
- Python 3.11+, Flask (application factory + blueprints)
- Flask-SQLAlchemy, Flask-Migrate (Alembic), PyMySQL → MariaDB 10.6+
- Flask-Login (sesiones), Flask-WTF (formularios + CSRF), python-dotenv
- Jinja2 + Bootstrap 5 (sin frameworks JS; JS mínimo en `static/js/`)
- `reportlab` para los PDF propios (resumen ejecutivo, agenda, tablero con gráficos); no requiere LibreOffice
- Chart.js 4.4.1 (CDN) solo en la vista Gráficos: única excepción a «sin frameworks JS»
- Plantillas: `docxtpl` (Word) y `openpyxl` (Excel); PDF de plantillas con LibreOffice headless
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
├── migrations/versions/   # 0001 esquema inicial · 0002 invitado solo resumen · 0003 plantillas
├── referencias/           # código Apps Script original (solo lectura, no se ejecuta)
├── storage/               # fuera de static/, no se sirve directo
│   ├── respaldos/<SIGLA>/<id_tarea>/   # adjuntos
│   ├── plantillas/                     # plantillas subidas (<uuid>.docx|xlsx)
│   └── generados/                      # temporales de LibreOffice, se borran siempre
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
    │                      # invitados, plantillas, pdf, catalogos, agenda, graficos, auditoria
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
| `/tablero/alertas` · `/informe` · `/cronograma` | admin, supervisor, unidad | Vistas del tablero |
| `/documentos/<plantilla>/{tarea/<id>, listado, informe}` | admin, supervisor, unidad | Generar documento (`?formato=original\|pdf`) |
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
Solo ve tres vistas (`VISTAS_INVITADO` en `models/permiso_invitado.py`), cada una con su PDF:
**resumen ejecutivo**, **agenda** y **gráficos**. En las tres ve solo gestiones con el MRE (nunca tareas internas;
`permisos.solo_gestiones_mre`) y sin enlaces al detalle de las tareas.
No ve tareas, alertas, informe, cronograma, responsables, adjuntos ni genera documentos de plantillas.
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
- Calendario mensual (lunes a domingo), cada día coloreado con su peor alerta; navegación por mes; «Próximos 14 días».
- Estado de agenda (como la app original): Concluido → Concluida, Pendiente → Pendiente, Observado / Devuelto → Bloqueada, el resto → En gestión.
- Filtros: unidad y responsable. PDF del mes: indicadores y eventos día por día.

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
- PDF con los mismos bloques dibujados con `reportlab.graphics` (sin JS).
- «Cuántas vencidas había cada día» no se puede graficar porque las alertas no se guardan; si se necesita, haría falta una tabla `foto_diaria` y un comando nocturno.

## Plantillas con marcadores (Admin › Plantillas)
El admin sube `.docx` o `.xlsx` (máx. 10 MB) a `storage/plantillas/` e indica su **alcance**: `tarea` (ficha), `listado` (lo que muestra el filtro) o `informe` (solo tareas críticas).
- Word: `docxtpl` con `jinja2.sandbox.SandboxedEnvironment` y autoescape. Listas con `{% for t in tareas %}…{% endfor %}`; en tablas, `{%tr for t in tareas %}` repite la fila.
- Excel: `openpyxl`, reemplaza `{{ marcador }}` en celdas; una fila con marcadores `{{ t.xxx }}` se repite por cada tarea conservando el formato. Una celda con un solo marcador numérico queda como número. Las fórmulas debajo de la fila repetida no se ajustan.
- Al subir: se validan los marcadores contra `MARCADORES` (en `services/plantillas.py`, visible en Admin › Plantillas › Marcadores) y se listan los desconocidos (quedan vacíos al generar). Una sintaxis inválida rechaza el archivo. Botón «Probar» con datos de ejemplo.
- Se generan desde «Generar documento»: ficha (detalle de tarea), listado (Tareas, con los filtros) e informe (Informe crítico), con los permisos de cada vista. El invitado no genera documentos.
- Salida: el mismo formato o PDF con LibreOffice (`soffice --headless --convert-to pdf`, perfil propio, tiempo límite `SOFFICE_TIMEOUT`, temporales en `storage/generados/` que se borran siempre). Sin LibreOffice solo se ofrece el formato original; `SOFFICE_PATH` en `.env` indica su ruta.

Marcadores principales: `unidad.nombre`, `unidad.sigla`, `tarea.codigo`, `tarea.asunto`, `tarea.tipo`, `tarea.instancia`, `tarea.estado`, `tarea.prioridad`, `tarea.alerta`, `tarea.fecha_solicitud`, `tarea.fecha_limite`, `tarea.responsable`, `tarea.persona`, `tarea.hoja_ruta`, `tarea.resultado`, `tarea.solucion`, `tarea.subtareas` (`s.texto`, `s.fecha`, `s.hecho`), `tareas`, `resumen.total`, `resumen.pendientes`, `resumen.vencidas`, `resumen.por_vencer`, `resumen.criticas`, `resumen.sin_solucion`, `resumen.concluidas`, `generado.fecha`, `generado.por`, `generado.filtros`. La lista completa está en `MARCADORES`.

## Configuración (`config.py` y `.env`)
- `.env`: `APP_CONFIG`, `SECRET_KEY`, `DATABASE_URL`, `SESSION_COOKIE_SECURE`, `SOFFICE_PATH` (opcional), `STORAGE_DIR` (opcional).
- `config.py`: sesión y bloqueo (`HORAS_SESION`, `MAX_INTENTOS`, `MINUTOS_BLOQUEO`), umbrales de alertas, `META_CUMPLIMIENTO`, `MAX_MB_ADJUNTO`, `EXTENSIONES_ADJUNTO`, `TAREAS_POR_PAGINA`, `SOFFICE_TIMEOUT`.

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
