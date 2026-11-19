# Implementation Plan: Mejora UI Frontend

**Branch**: `001-mejora-ui-frontend` | **Date**: 2026-11-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-mejora-ui-frontend/spec.md`

## Summary

Reestructura el layout de la aplicación reemplazando la barra de navegación horizontal
por un sidebar vertical con soporte de drawer (Offcanvas de Bootstrap 5) en móvil.
Introduce dos variantes de contenedor (wide / form) y unifica el espaciado entre vistas.
No hay cambios de base de datos, servicios ni lógica de permisos: todo el trabajo es
HTML/CSS/JS de presentación, en `base.html`, `app.css` y un módulo JS mínimo.

## Technical Context

**Language/Version**: Python 3.12 · Flask 3.1.0 · Jinja2 (bundled)

**Primary Dependencies**: Bootstrap 5.3.3 (CDN) — ya instalado; sin dependencias nuevas.
JS: vanilla ES2017 para el toggle del drawer (< 20 líneas). Chart.js 4.4.1 (ya
instalado; solo en Gráficos; sin cambios).

**Storage**: N/A — sin cambios de base de datos ni modelos.

**Testing**: pytest (tests existentes; ningún test prueba HTML/CSS — se valida
manualmente según quickstart.md).

**Target Platform**: Navegador de escritorio + móvil. Breakpoint sidebar: Bootstrap `lg`
(≥ 992 px) para escritorio; Offcanvas para < 992 px.

**Project Type**: Aplicación web Flask — Jinja2 + Bootstrap 5 (server-side rendering).

**Performance Goals**: Sin regresión de carga perceptible. No se añaden recursos
externos nuevos; solo ~1 KB de CSS adicional y < 1 KB de JS.

**Constraints**:
- Colores y componentes de alerta sin modificar (constitución Principio V + requisito del usuario).
- Sin frameworks JS externos (constitución sección «Flujo de Desarrollo»).
- Bootstrap Offcanvas es el mecanismo nativo para drawer en móvil — evita código custom.

**Scale/Scope**: 27 plantillas HTML existentes + 1 CSS + JS mínimo.

## Constitution Check

*GATE: Debe pasar antes de Phase 0. Re-verificado tras Phase 1.*

| Principio | Aplica | Estado |
|---|---|---|
| I. Permisos como Puerta de Entrada | No — sin cambios de consultas | ✅ No aplica |
| II. Controladores Delgados / Servicios | No — sin cambios de lógica | ✅ No aplica |
| III. Alertas Calculadas, No Almacenadas | No — sin cambios de servicios | ✅ No aplica |
| IV. Auditoría Obligatoria | No — sin mutaciones de datos | ✅ No aplica |
| V. Disciplina UTC / Hora Local | No — sin cambios de fechas | ✅ No aplica |
| Español en identificadores | ✅ Nuevas clases CSS y bloques Jinja2 en español | ✅ |
| Colores protegidos (chips, barras, KPIs) | ✅ No se tocan | ✅ |

**Veredicto**: sin violaciones. Ningún ítem de Complexity Tracking requerido.

*Re-verificación post-Phase 1*: confirmada — ningún artifact introduce lógica de
negocio ni consultas de base de datos.

## Project Structure

### Documentation (this feature)

```text
specs/001-mejora-ui-frontend/
├── plan.md              ← este archivo
├── research.md          ← decisiones de diseño (Phase 0)
├── data-model.md        ← contrato de bloques Jinja2 (Phase 1)
├── quickstart.md        ← guía de validación manual (Phase 1)
├── contracts/
│   └── layout-blocks.md ← bloques Jinja2 que cada template puede sobreescribir
└── tasks.md             ← generado por /speckit-tasks (no existe aún)
```

### Source Code (repository root)

```text
app/
├── templates/
│   ├── base.html                   ← restructurado (sidebar + header + contenido)
│   ├── _macros.html                ← sin cambios
│   ├── inicio.html                 ← ajuste de bloque contenedor
│   ├── tareas/
│   │   ├── detalle.html            ← bloque contenedor → form
│   │   └── form.html               ← bloque contenedor → form
│   └── auth/
│       └── cambiar_clave.html      ← layout centrado; sin cambios de fondo
└── static/
    ├── css/
    │   └── app.css                 ← estilos del sidebar, header, variantes de contenedor
    └── js/
        └── sidebar.js              ← nuevo: toggle del drawer en móvil (< 20 líneas)
```

Resto de templates: solo se verifica que el `{% block contenedor %}` sea correcto;
los `container-fluid` de listados no necesitan cambio.
