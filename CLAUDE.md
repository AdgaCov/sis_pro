# Seguimiento MRE · Bolivia en el Mundo

App web para que las unidades de Bolivia en el Mundo registren sus tareas y trámites con el MRE,
y para que Planificación y la DGE vean todo con alertas, cronograma, informes y descargas.
Es la migración de una app en Google Apps Script (ver `referencias/`) a Python.

## Stack
- Python 3.11+, Flask (application factory + blueprints)
- Flask-SQLAlchemy, Flask-Migrate (Alembic), PyMySQL → MariaDB 10.6+
- Flask-Login (sesiones), Flask-WTF (formularios + CSRF), python-dotenv
- Jinja2 + Bootstrap 5 (sin frameworks JS; JS mínimo en `static/js/`)
- `reportlab` para el PDF del resumen ejecutivo (no requiere LibreOffice)
- Plantillas: `docxtpl` (Word) y `openpyxl` (Excel); PDF con LibreOffice headless
- Tests: pytest

## Idioma y estilo
- Interfaz, mensajes, nombres de tablas, modelos, rutas y variables **en español** (sin tildes en identificadores).
- Fechas en pantalla: dd/mm/aaaa. Zona horaria: America/La_Paz.
- Controladores cortos: la lógica va en `app/services/`. Los modelos no importan servicios.
- Nunca confiar en la interfaz para permisos: todo se valida en el servidor.

## Estructura
```
seg_pro/
├── run.py · config.py · .env.example · requirements.txt
├── migrations/
├── referencias/           # código Apps Script original (solo lectura, no se ejecuta)
├── storage/               # fuera de static/, no se sirve directo
│   ├── respaldos/<unidad>/
│   ├── plantillas/
│   └── generados/         # temporales, se borran
├── tests/
└── app/
    ├── __init__.py        # create_app()
    ├── extensions.py      # db, migrate, login_manager, csrf
    ├── models/            # usuario, unidad, tarea, catalogo, permiso_invitado, plantilla, auditoria
    ├── controllers/       # auth, tareas, tablero, responsables, reportes, admin/{usuarios,invitados,plantillas,catalogos}
    ├── services/          # permisos, alertas, resumen, plantillas, pdf, archivos
    ├── forms/
    ├── utils/decoradores.py   # @rol_requerido, @solo_lectura
    ├── templates/         # base.html, auth/, tareas/, tablero/, admin/, reportes/
    └── static/
```

## Roles y permisos
Cada persona tiene su propio usuario y contraseña, ligado a una unidad (salvo admin/supervisor/invitado, que pueden no tener).

| Rol | Ve | Puede |
|---|---|---|
| `admin` (Planificación) | Todo | Todo: tareas de cualquier unidad, reasignar tareas, mover cargos, usuarios, invitados, plantillas, catálogos |
| `supervisor` (DGE) | Todo | Editar tareas de cualquier unidad y reasignarlas. No administra usuarios ni plantillas |
| `unidad` | Solo su unidad | Crear/editar/eliminar sus tareas, adjuntos, subtareas y cargos de su unidad |
| `invitado` | Solo el resumen ejecutivo, de las unidades que el admin configure | Leerlo y descargarlo en PDF. Nunca modifica nada |

- **Contraseñas:** hash con `werkzeug.security`. Mínimo 8 caracteres con letras y números.
- **Crear usuario:** el admin escribe la contraseña inicial (con confirmación). Opcionalmente marca «pedir cambio al primer ingreso» (`debe_cambiar_clave`); por defecto no.
- **Restablecer:** solo el admin, desde Usuarios. Pone una clave temporal → `debe_cambiar_clave = True` → al entrar se obliga a cambiarla. No hay recuperación por correo.
- **Bloqueo:** 5 intentos fallidos → 15 minutos bloqueado. Sesión de 8 horas.
- Al restablecer la clave o desactivar a un usuario, se invalidan sus sesiones abiertas.
- Siempre debe existir al menos un admin activo.

### Invitado
Solo ve el **resumen ejecutivo** (`/tablero/resumen`) y lo descarga en PDF (`/tablero/resumen.pdf`).
No ve tareas, alertas, informe, cronograma, responsables ni adjuntos.
Tabla `permiso_invitado` por usuario invitado: unidades permitidas (`todas_unidades` o una lista).
Se configura en Admin › Invitados.

`@solo_lectura` rechaza con 403 cualquier POST/PUT/PATCH/DELETE de un invitado (excepto logout y cambiar su propia clave).
`services/permisos.py` filtra las consultas: ningún controlador consulta tareas sin pasar por ahí.

## Reglas de negocio (vienen de la app original)
- **Unidades:** DGE-STAF, UAF, UPT, UDTP, UEP, SISTEMAS.
- **Código de tarea:** `<SIGLA>-<NNN>` correlativo por unidad (UAF-001). Al reasignar a otra unidad recibe código nuevo de destino y se actualizan las tareas que la referenciaban en `habilita_a`.
- **Tipos:** `Tarea interna` (no entra al resumen ejecutivo), `Solicitud al MRE`, `Autorización del MRE`, `Gestión con el MRE (habilita otra tarea)`.
- **Estados (catálogo editable):** Pendiente, En proceso, Remitido a DGE, Con V.º B.º de DGE, Ingresado por Ventanilla Única, Remitido a instancia del MRE, En instancia del MRE – Sin respuesta, Observado / Devuelto, Respuesta recibida del MRE, Autorizado, Concluido, Otro. `Tarea interna` y `Concluido` no se pueden borrar del catálogo.
- Al pasar a **Concluido** sin fecha de conclusión, se pone la de hoy.
- **Responsable = cargo**, no persona. Cada cargo tiene una persona designada (opcional). Cada unidad tiene un cargo `Apoyo` para asignaciones provisionales. Admin/supervisor pueden asignar un cargo de otra unidad.
- **Dependencias:** `habilita_a` apunta a otra tarea. Una unidad solo puede apuntar a tareas de su propia unidad. Una tarea no puede habilitarse a sí misma.
- **Subtareas:** texto (≤300), fecha opcional, hecho sí/no. Máximo 40 por tarea.
- **Adjuntos:** máx. 10 MB por archivo, en `storage/respaldos/<unidad>/`, descarga solo con permiso sobre la tarea.
- **Eliminar tarea:** se copia a la papelera (auditoría) y se limpian las referencias `habilita_a`.
- Registrar `actualizado_en` y `actualizado_por` en cada cambio.

### Alertas (se calculan al leer, NO se guardan)
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
Los umbrales (3, 7, 15 días) van en `config.py`.

## Plantillas con marcadores
El admin sube `.docx` o `.xlsx` a `storage/plantillas/` e indica su **alcance**: `tarea` (ficha), `listado` (lo que muestra el filtro) o `informe` (informe crítico).
- Word: `docxtpl` con `jinja2.sandbox.SandboxedEnvironment`. Listas con `{% for t in tareas %}…{% endfor %}`.
- Excel: `openpyxl`, reemplaza `{{ marcador }}` en celdas; una fila con marcadores `{{ t.xxx }}` se repite por cada tarea conservando el formato.
- Salida: el mismo formato o PDF (LibreOffice `soffice --headless --convert-to pdf`, con tiempo límite).
- Al subir: validar marcadores contra el catálogo `marcador` y listar los desconocidos. Botón «Probar» con datos de ejemplo.
- El invitado solo descarga el PDF del resumen ejecutivo, con datos de sus unidades.

Marcadores base: `unidad.nombre`, `tarea.codigo`, `tarea.asunto`, `tarea.tipo`, `tarea.instancia`, `tarea.estado`, `tarea.prioridad`, `tarea.alerta`, `tarea.fecha_solicitud`, `tarea.fecha_limite`, `tarea.responsable`, `tarea.persona`, `tarea.hoja_ruta`, `tarea.resultado`, `tarea.solucion`, `resumen.total`, `resumen.pendientes`, `resumen.vencidas`, `generado.fecha`, `generado.por`.

## Comandos
```
flask db upgrade                 # aplicar migraciones
flask crear-admin                # crea el primer admin (pide usuario y clave)
flask cargar-catalogos           # carga catálogos, unidades y cargos iniciales
flask run --debug
pytest
```

## Etapas
1. Modelos, migración inicial, comandos CLI, login con roles (incluido invitado) y admin de usuarios.
2. Tareas: CRUD, responsables, subtareas, dependencias, adjuntos, papelera.
3. Tablero: resumen ejecutivo, alertas, informe crítico, cronograma, filtros.
4. Invitados: configuración de permisos y vistas de solo lectura.
5. Plantillas: subida, validación, generación Word/Excel/PDF.
6. (Opcional) Sincronización con la Agenda Despacho vía Google Sheets API.

Cada etapa termina con tests de permisos: una unidad no ve otra unidad, un invitado no puede escribir.
