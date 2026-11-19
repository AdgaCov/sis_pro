# Data Model: Mejora UI Frontend

**Feature**: 001-mejora-ui-frontend | **Date**: 2026-11-19

> No hay cambios de modelos de base de datos. Este archivo documenta los
> «componentes de layout» — las entidades de presentación que esta feature introduce.

## Entidades de Layout

### 1. `base.html` — Estructura Principal

Tres zonas fijas en todas las páginas autenticadas:

| Zona | Elemento HTML | Descripción |
|---|---|---|
| `.app-header` | `<header>` | Marca + toggle móvil + dropdown usuario |
| `.app-sidebar` | `<nav>` | Sidebar de navegación (siempre en DOM) |
| `.app-contenido` | `<main>` | Área de contenido; los bloques Jinja2 viven aquí |

**Relación**: `<body>` → `<div class="app-shell">` → (`<header>` + `<div class="app-cuerpo">` → (`<nav>` + `<main>`))

```
body
└── .app-shell (flex-column, 100vh)
    ├── header.app-header (flex-row, sticky top)
    └── .app-cuerpo (flex-row, flex: 1)
        ├── nav.app-sidebar (240px fixed width, lg+)
        │   └── Offcanvas en móvil (mismos ítems)
        └── main.app-contenido (flex: 1, overflow-y: auto)
            └── .ancho-wide | .ancho-form  ← bloque Jinja2
```

### 2. Variantes de Contenedor

| Nombre CSS | Comportamiento | Uso |
|---|---|---|
| `.ancho-wide` | `width: 100%; padding: 1.5rem 1.25rem` | Listados, tablero, agenda, cronograma, alertas, Inicio |
| `.ancho-form` | `max-width: 860px; margin: 0 auto; padding: 1.5rem 1.25rem` | Formulario/detalle de tarea, formularios admin, cambiar contraseña |

### 3. Sidebar — Secciones y Ítems

```
nav.app-sidebar
├── [marca del sidebar — solo móvil via Offcanvas header]
├── ul.sidebar-nav
│   ├── li → Inicio           (endpoint: inicio.index)        [no invitado]
│   ├── li → Tareas           (endpoint: tareas.lista)         [puede_ver_vista 'tareas']
│   ├── li → Resumen          (endpoint: tablero.resumen_ejecutivo)
│   ├── li → Alertas          (endpoint: tablero.alertas)
│   ├── li → Informe crítico  (endpoint: tablero.informe)
│   ├── li → Cronograma       (endpoint: tablero.cronograma)
│   ├── li → Agenda           (endpoint: agenda.mes)
│   ├── li → Gráficos         (endpoint: tablero.graficos_vista)
│   ├── li → Responsables     (endpoint: responsables.lista)   [no invitado]
│   ├── [separador «Administración» — solo admin]
│   ├── li → Usuarios         (endpoint: admin_usuarios.lista) [admin]
│   ├── li → Invitados        (endpoint: admin_invitados.lista)[admin]
│   ├── li → Plantillas       (endpoint: admin_plantillas.lista)[admin]
│   ├── li → Catálogos        (endpoint: admin_catalogos.lista)[admin]
│   └── li → Papelera         (endpoint: tareas.papelera)      [admin]
```

**Reglas**: idénticas a las del navbar actual; el filtro `puede_ver_vista` y los
condicionales de rol en Jinja2 se mueven sin cambio lógico.

### 4. Header — Slots

| Slot | Contenido | Visible en |
|---|---|---|
| `.header-marca` | Texto «Seguimiento MRE» + enlace a `/` | Siempre |
| `.header-toggle` | Botón `data-bs-toggle="offcanvas"` | Solo < lg (`.d-lg-none`) |
| `.header-usuario` | Dropdown: nombre + badge rol/unidad + ítems | Siempre (autenticado) |

## Bloques Jinja2 — Contrato de Herencia

Ver [contracts/layout-blocks.md](contracts/layout-blocks.md) para la especificación
completa de qué bloque sobreescribir en cada template.

## Estado de Validación

Sin entidades de base de datos afectadas. El ORM y las migraciones no se tocan.
