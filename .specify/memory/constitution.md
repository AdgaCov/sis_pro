<!--
SYNC IMPACT REPORT (remove before committing)
=============================================
Version change: [none] → 1.0.0 (initial ratification)
Added sections:
  - Core Principles (I–V)
  - Restricciones de Dominio
  - Flujo de Desarrollo
  - Governance
Removed sections: n/a (first version)
Follow-up TODOs:
  - RATIFICATION_DATE marked as 2026-11-19 (today); confirm with project owner if a prior date applies.
-->

# Seguimiento MRE Constitution

## Core Principles

### I. Permisos como Puerta de Entrada (NON-NEGOTIABLE)

Ningún controlador consulta `Tarea` directamente. Toda consulta de tareas MUST pasar por
`services/permisos.py:consulta_tareas(usuario)`. Las funciones derivadas
(`unidades_visibles`, `puede_ver_tarea`, `puede_editar_tarea`, `puede_ver_adjuntos`) son el
único lugar donde se decide visibilidad.

La lógica de permisos se valida en el servidor: primero en el decorador/guardia,
y de nuevo dentro del servicio. La interfaz nunca es la última línea de defensa.

Lo que el usuario no puede ver responde **404**; lo que ve pero no puede modificar, **403**.

### II. Controladores Delgados — Lógica en Servicios

Los controladores leen el formulario, llaman un servicio, hacen flash y redirigen.
La lógica de negocio vive en `services/`. Los modelos no importan servicios.

Los servicios lanzan `ErrorNegocio(mensaje)` cuando una operación no puede
completarse por regla de negocio. El controlador MUST hacer `db.session.rollback()`
y mostrar el mensaje con `flash(..., "danger")`. Ninguna otra capa captura
`ErrorNegocio`; dejarla burbujear produce un 500.

Los servicios validan sus precondiciones incluso cuando el controlador ya lo hizo;
la duplicación intencionada evita bypasses desde la CLI o tests.

### III. Alertas Calculadas, Nunca Almacenadas (NON-NEGOTIABLE)

Las alertas (`services/alertas.py`) se calculan en Python al leer. No existe columna
de alerta en la base de datos. Las listas filtradas por alerta se pagiran en memoria
(`utils/paginacion.py`).

Consecuencia: nunca ordenar ni filtrar alertas con SQL. Cambiar los umbrales
(`DIAS_POR_VENCER`, `DIAS_SEGUIMIENTO`, `DIAS_CRITICO`, `DIAS_SIN_ACTUALIZAR`)
en `config.py` recalcula automáticamente todo el tablero sin migración.

### IV. Auditoría Obligatoria

Toda acción que modifica datos MUST llamar a `services/auditoria.registrar()`
dentro de la misma sesión de base de datos, antes del `commit`. El registro
se confirma junto con la mutación; si el commit falla, la auditoría también
revierte. No se auditan lecturas.

### V. Disciplina UTC / Hora Local

Los datetimes se guardan en la base como UTC naive (sin tzinfo).
`utils/fechas.ahora_utc()` es la única fuente de timestamps para modelos.
La conversión a America/La_Paz ocurre exclusivamente en la capa de presentación
mediante `utils/fechas.a_local()` y los filtros Jinja2 `|fecha` y `|fecha_hora`.
Mezclar tzinfo en modelos o servicios rompe la coherencia de fechas.

## Restricciones de Dominio

**Español en identificadores**: nombres de tablas, modelos, rutas, variables y
mensajes van en español. Los identificadores no usan tildes.

**Valores protegidos del catálogo**: `Tarea interna`, `Concluido` y `Alta` son
referenciados por nombre en el código (`catalogo.py:TIPO_INTERNA`, `ESTADO_CONCLUIDO`,
`PRIORIDAD_ALTA`). Renombrarlos en la base rompe las alertas y el filtro MRE.
No se desactivan ni eliminan. El campo `protegido=True` en la tabla es la señal
de esta restricción.

**Código de tarea**: formato `<SIGLA>-<NNN>`, asignado con `SELECT ... FOR UPDATE`
en `services/tareas.siguiente_codigo()`. Un código nunca se reutiliza; al
reasignar una tarea a otra unidad recibe un código nuevo de destino.

**Dependencias de tarea**: `habilita_a_id` apunta a otra tarea. Una unidad solo
puede apuntar a tareas de su propia unidad. Una tarea no puede habilitarse a sí
misma. Al eliminar una tarea, se limpia `habilita_a_id` en las que la referenciaban.

**Sesión de usuario**: `get_id()` devuelve `"{id}:{version_sesion}"`. Incrementar
`version_sesion` invalida todas las sesiones abiertas del usuario sin tocar el
almacén de sesiones. MUST hacerse al restablecer la clave, cambiar rol/unidad
o desactivar.

## Flujo de Desarrollo

**Migraciones con Alembic**: cada cambio de esquema genera una migración numerada
(`0001_`, `0002_`, ...). `flask db check` debe pasar antes de cualquier PR.
No se editan migraciones ya aplicadas en producción.

**Tests**: se ejecutan con SQLite en memoria (`PruebasConfig`). Cada fichero de
test cubre un área funcional. Los tests de permisos son obligatorios para toda
nueva vista: una unidad no debe ver datos de otra, un invitado no debe poder
escribir. `TEST_DATABASE_URL` permite correr contra MariaDB real.

**Sin JS frameworks**: la interfaz usa Bootstrap 5 + Jinja2. JS se limita a
`static/js/` y solo para interacciones que CSS no puede cubrir. La única
excepción autorizada es Chart.js 4.4.1 en la vista Gráficos.

**LibreOffice es opcional**: si `SOFFICE_PATH` no está configurado, la generación
de PDF desde plantillas no está disponible. Los PDF propios (reportlab) no
dependen de LibreOffice. El código MUST degradarse sin soffice, no fallar.

## Governance

Esta constitución rige sobre cualquier decisión técnica no especificada en
`CLAUDE.md`. En caso de conflicto, `CLAUDE.md` (reglas de negocio del dominio)
prevalece sobre esta constitución (principios de ingeniería).

**Enmiendas**: cualquier cambio a un principio existente MUST documentarse con
justificación en el commit. Los cambios de MAJOR version requieren revisión
explícita del equipo. Los de MINOR o PATCH pueden aprobarse en PR.

**Versionado**:
- MAJOR: eliminación o redefinición incompatible de un principio.
- MINOR: principio nuevo o sección nueva con guía sustancial.
- PATCH: aclaraciones, correcciones de redacción, ajustes no semánticos.

**Revisión de cumplimiento**: toda PR que toque `services/`, `models/` o
`controllers/` SHOULD verificar los principios I–IV antes de merge.

**Version**: 1.0.0 | **Ratified**: 2026-11-19 | **Last Amended**: 2026-11-19
