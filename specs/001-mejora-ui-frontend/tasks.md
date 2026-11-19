# Tasks: Mejora UI Frontend

**Input**: Design documents from `specs/001-mejora-ui-frontend/`

**Prerequisites**: plan.md ✅ · spec.md ✅ · research.md ✅ · data-model.md ✅ · contracts/layout-blocks.md ✅ · quickstart.md ✅

**Tests**: No test tasks — ningún test existente prueba HTML/CSS; la validación es manual
(ver quickstart.md). Los tests de pytest se ejecutan en Polish para verificar que no
hay regresión.

**Organization**: Fases por historia de usuario. Todo el trabajo es HTML/CSS/JS de
presentación. Sin cambios de base de datos, servicios ni controladores.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo (distinto archivo, sin dependencias incompletas)
- **[Story]**: historia de usuario a la que pertenece (US1–US4)
- Rutas relativas a la raíz del repositorio

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Reestructura `base.html` e introduce los estilos y JS de layout. Sin esto
ninguna historia puede integrarse.

**⚠️ CRÍTICO**: Ninguna historia de usuario puede implementarse hasta completar esta fase.

- [X] T001 Restructurar `app/templates/base.html`: eliminar `<nav class="navbar">` actual; añadir estructura `.app-shell` (flex-column, 100vh) → `.app-header` (header sticky) + `.app-cuerpo` (flex-row, flex:1) → `.app-sidebar` (nav desktop 240 px, `d-none d-lg-block`) + nodo Offcanvas Bootstrap (`id="sidebarOffcanvas"`, `offcanvas-start`) con los mismos hijos + `<main class="app-contenido">` con `{% block ancho_contenido %}ancho-wide{% endblock %}` como wrapper interno de `{% block contenido %}`; eliminar `{% block contenedor %}`; añadir `<script src="{{ url_for('static', filename='js/sidebar.js') }}"></script>` antes de `{% block scripts %}`

- [X] T002 Añadir a `app/static/css/app.css` los estilos de layout: `.app-shell { display: flex; flex-direction: column; min-height: 100vh; }`, `.app-header { background: var(--azul); position: sticky; top: 0; z-index: 1030; }`, `.app-cuerpo { display: flex; flex: 1; min-height: 0; }`, `.app-sidebar { width: 240px; background: var(--azul); overflow-y: auto; }`, `.app-contenido { flex: 1; min-width: 0; overflow-y: auto; }`, `.ancho-wide { width: 100%; padding: 1.5rem 1.25rem; }`, `.ancho-form { max-width: 860px; margin: 0 auto; padding: 1.5rem 1.25rem; }`; también variable `--espacio-seccion: 1.5rem` en `:root`

- [X] T003 [P] Crear `app/static/js/sidebar.js`: escuchar `click` en enlaces dentro de `#sidebarOffcanvas`; al hacer click obtener instancia de Bootstrap Offcanvas (`bootstrap.Offcanvas.getInstance`) y llamar `.hide()` si existe; sin dependencias externas; < 20 líneas

**Checkpoint**: Con T001–T003 completos, la app carga con la nueva estructura de shell
(sidebar vacío visible en escritorio, drawer en móvil). Resto de historias puede empezar.

---

## Phase 2: User Story 1 — Navegación por Sidebar (Priority: P1) 🎯 MVP

**Goal**: Todos los ítems de navegación trasladados al sidebar con la misma lógica de
permisos que el navbar actual; active state; sección Admin agrupada.

**Independent Test**: Cargar cualquier vista como admin, supervisor, unidad e invitado
y verificar que el sidebar muestra exactamente los ítems correctos y que el ítem activo
está marcado. Ver quickstart.md §1 y §5.

- [X] T004 [US1] Poblar la lista `ul.sidebar-nav` en ambos nodos del sidebar (`app/templates/base.html`): trasladar la lógica de ítems del navbar original (Inicio, Tareas, Resumen, Alertas, Informe crítico, Cronograma, Agenda, Gráficos, Responsables) con los mismos condicionales `{% if puede_ver_vista %}` y `{% if not current_user.es_invitado %}`; en cada `<a>` añadir clase `activo` cuando `request.endpoint == endpoint`

- [X] T005 [US1] Añadir separador de sección «Administración» en el sidebar en `app/templates/base.html` para `{% if current_user.es_admin %}`: un `<li class="sidebar-separador">Administración</li>` seguido de los ítems Usuarios, Invitados, Plantillas, Catálogos, Papelera

- [X] T006 [P] [US1] Añadir CSS del sidebar nav a `app/static/css/app.css`: `.sidebar-nav { list-style: none; padding: 0; margin: 0; }`, `.sidebar-nav a { display: block; color: rgba(255,255,255,.8); padding: .5rem 1rem; text-decoration: none; font-size: .875rem; }`, `.sidebar-nav a:hover, .sidebar-nav a.activo { background: rgba(255,255,255,.12); color: #fff; }`, `.sidebar-nav a.activo { border-left: 3px solid #fff; }`, `.sidebar-separador { font-size: .65rem; text-transform: uppercase; letter-spacing: .06em; color: rgba(255,255,255,.45); padding: 1rem 1rem .25rem; }`

- [X] T007 [US1] Actualizar cabecera en `app/templates/base.html`: `.app-header` contiene `<div class="d-flex align-items-center justify-content-between px-3 py-2">`; izquierda: `<a class="text-white fw-semibold text-decoration-none" href="...">Seguimiento MRE</a>` + botón `data-bs-toggle="offcanvas" data-bs-target="#sidebarOffcanvas"` con clase `d-lg-none btn btn-sm text-white`; derecha: dropdown de usuario (nombre + badge rol/unidad + «Cambiar contraseña» + separador + «Salir»), idéntico al del navbar actual

**Checkpoint**: US1 completa — sidebar funcional con todos los ítems, active state y
soporte de drawer en móvil. MVP demostrable.

---

## Phase 3: User Story 2 — Dashboard Reestructurado (Priority: P2)

**Goal**: Inicio muestra KPIs en banda superior, gráficos en cuadrícula de dos columnas
en escritorio, accesos rápidos en sección inferior separada.

**Independent Test**: Cargar `/` como admin con datos y verificar tres bandas visuales
distinguibles: KPIs → gráficos → accesos. Ver quickstart.md §2.

- [X] T008 [US2] Restructurar `app/templates/inicio.html`: encabezado de bienvenida + botones de descarga mantienen su posición; mover `{% include "tablero/_graficos.html" %}` dentro de `<section class="dashboard-graficos mb-4">`; mover tarjetas `enlaces` dentro de `<section class="dashboard-accesos"><h2 class="h6 seccion-titulo">Accesos</h2>...</section>` con separación `mt-4`; mantener filtro de unidad antes de la sección gráficos; mantener bloque `{% block scripts %}` sin cambios

- [X] T009 [P] [US2] Añadir a `app/static/css/app.css` `.dashboard-graficos` para cuadrícula de dos columnas en lg+: `@media (min-width: 992px) { .dashboard-graficos > .row { --bs-gutter-x: 1.5rem; } }` (los gráficos ya usan `.row` internamente en `_graficos.html`; verificar antes de añadir nueva regla y adaptar si la estructura interna difiere)

**Checkpoint**: US2 completa — dashboard con jerarquía visual clara.

---

## Phase 4: User Story 3 — Espaciado y Márgenes Consistentes (Priority: P3)

**Goal**: Mismo padding lateral y espaciado vertical entre secciones en todas las vistas.

**Independent Test**: Navegar entre Tareas, Alertas, Resumen y un formulario; confirmar
que el margen lateral es idéntico visualmente (derivado de `.ancho-wide` / `.ancho-form`
ya definidos en T002). Ver quickstart.md §4.

- [X] T010 [US3] Verificar que todos los templates de listado y tablero NO tienen `{% block contenedor %}` sobreescrito (ese bloque ya fue eliminado en T001); si algún template aún usa el bloque antiguo, eliminarlo para que hereden `.ancho-wide` por defecto; archivos a revisar: `tareas/lista.html`, `tareas/papelera.html`, `tablero/alertas.html`, `tablero/resumen.html`, `tablero/informe.html`, `tablero/cronograma.html`, `tablero/graficos.html`, `agenda/mes.html`, `responsables/lista.html`, `admin/catalogos/lista.html`, `admin/usuarios/lista.html`, `admin/invitados/lista.html`, `admin/plantillas/lista.html`, `admin/plantillas/marcadores.html`

- [X] T011 [P] [US3] Reemplazar en `app/static/css/app.css` los valores literales de `padding: 1.5rem 1.25rem` en `.ancho-wide` y `.ancho-form` (añadidos en T002) con `padding: var(--espacio-seccion) calc(var(--espacio-seccion) * 0.833)` usando la variable `--espacio-seccion: 1.5rem` ya declarada, para que el espaciado sea configurable desde un único punto

**Checkpoint**: US3 completa — márgenes y padding uniformes en toda la app.

---

## Phase 5: User Story 4 — Vistas con Layout Propio (Priority: P4)

**Goal**: Formularios y detalle de tarea usan contenedor estrecho; listados usan ancho
completo. Requiere que T002 esté completo (`.ancho-form` disponible).

**Independent Test**: Abrir detalle de tarea y lista de tareas; confirmar que el primero
tiene contenedor más estrecho que el segundo. Ver quickstart.md §3.

- [X] T012 [P] [US4] Añadir `{% block ancho_contenido %}ancho-form{% endblock %}` a `app/templates/tareas/detalle.html` (después de `{% extends "base.html" %}`)

- [X] T013 [P] [US4] Añadir `{% block ancho_contenido %}ancho-form{% endblock %}` a `app/templates/tareas/form.html`

- [X] T014 [P] [US4] Añadir `{% block ancho_contenido %}ancho-form{% endblock %}` a `app/templates/admin/usuarios/form.html`

- [X] T015 [P] [US4] Añadir `{% block ancho_contenido %}ancho-form{% endblock %}` a `app/templates/admin/invitados/form.html`

- [X] T016 [P] [US4] Añadir `{% block ancho_contenido %}ancho-form{% endblock %}` a `app/templates/admin/plantillas/form.html`

- [X] T017 [P] [US4] Añadir `{% block ancho_contenido %}ancho-form{% endblock %}` a `app/templates/auth/cambiar_clave.html`

**Checkpoint**: US4 completa — cada tipo de vista usa el ancho adecuado a su contenido.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Ajustes que afectan a varias historias, validación final y regresión.

- [X] T018 [P] Añadir a `app/static/css/app.css` en el bloque `@media print` existente: `.app-sidebar, .app-header .d-lg-none { display: none !important; }` y `.app-cuerpo { display: block; }` para que el contenido se imprima sin sidebar ni toggle

- [X] T019 Ejecutar `pytest` desde la raíz del proyecto y confirmar que todos los tests pasan sin modificación; si algún test falla por cambios de contexto de plantilla (p.ej. `block contenedor` eliminado), corregir el test para que refleje la nueva estructura sin cambiar la lógica de negocio probada

- [X] T020 Validación manual completa según `specs/001-mejora-ui-frontend/quickstart.md`: verificar los 7 escenarios (escritorio, móvil, formulario, espaciado, invitado, pytest, impresión) y marcar los criterios de aceptación de quickstart.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: Sin dependencias — puede empezar inmediatamente.
- **US1 (Phase 2)**: Depende de Phase 1 completa. Es el MVP.
- **US2 (Phase 3)**: Depende de Phase 1. Independiente de US1.
- **US3 (Phase 4)**: Depende de T002 (CSS vars) de Phase 1. Independiente de US1/US2.
- **US4 (Phase 5)**: Depende de T002 (`.ancho-form` disponible) de Phase 1. Todas sus tareas son paralelas entre sí.
- **Polish (Phase 6)**: Depende de todas las fases anteriores.

### User Story Dependencies

- **US1 (P1)**: Depende de Foundational. Sin dependencia de otras historias.
- **US2 (P2)**: Depende de Foundational. Sin dependencia de US1.
- **US3 (P3)**: Depende de T002. Sin dependencia de US1/US2.
- **US4 (P4)**: Depende de T002. T012–T017 son todas paralelas entre sí.

### Within Each User Story

- Fundacional primero (T001–T003).
- CSS y JS pueden ejecutarse en paralelo con el HTML de cada historia (archivos distintos).
- Validar cada historia en su checkpoint antes de continuar.

### Parallel Opportunities

- T003 (sidebar.js) y T002 (CSS) pueden ejecutarse en paralelo con T001.
- Una vez terminado Phase 1: US1, US2, US3 y US4 pueden iniciarse en paralelo.
- Dentro de US4: T012–T017 son completamente paralelas (archivos distintos).

---

## Parallel Example: Phase 1

```text
# En paralelo (archivos distintos):
T001: app/templates/base.html  — restructura el HTML
T002: app/static/css/app.css   — estilos del shell
T003: app/static/js/sidebar.js — JS del drawer
```

## Parallel Example: User Story 4

```text
# Todas en paralelo (una línea por archivo):
T012: app/templates/tareas/detalle.html
T013: app/templates/tareas/form.html
T014: app/templates/admin/usuarios/form.html
T015: app/templates/admin/invitados/form.html
T016: app/templates/admin/plantillas/form.html
T017: app/templates/auth/cambiar_clave.html
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1 (Foundational): T001, T002, T003
2. Completar Phase 2 (US1): T004, T005, T006, T007
3. **DETENER y VALIDAR**: quickstart.md §1 y §2 (escritorio + móvil)
4. Demo funcional con sidebar completo.

### Incremental Delivery

1. Phase 1 → app carga con nueva estructura (sidebar vacío)
2. Phase 1 + Phase 2 → sidebar navegable (MVP)
3. + Phase 3 → dashboard mejorado
4. + Phase 4 → espaciado uniforme
5. + Phase 5 → formularios con ancho propio
6. + Phase 6 → validación completa

---

## Notes

- Todos los condicionales de rol/permisos del navbar original se trasladan **sin cambio
  lógico** al sidebar; no se añaden ni quitan secciones.
- El bloque `{% block contenedor %}` del `base.html` original se elimina en T001; los
  templates que lo sobreescribían migran al nuevo `{% block ancho_contenido %}` en T010/T012–T017.
- No se añaden dependencias a `requirements.txt` ni librerías JS/CSS externas.
- Bootstrap Offcanvas se activa con atributos `data-bs-*` — cero JS propio para abrir.
