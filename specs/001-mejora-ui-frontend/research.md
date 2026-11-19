# Research: Mejora UI Frontend

**Feature**: 001-mejora-ui-frontend | **Date**: 2026-11-19

## Decisión 1: Mecanismo de Sidebar en Móvil

**Decision**: Bootstrap 5 Offcanvas (`<div class="offcanvas offcanvas-start">`)

**Rationale**: Bootstrap 5.3.3 ya está cargado en la app. Offcanvas provee el
comportamiento de drawer (overlay, focus-trap, dismiss con Escape o clic exterior)
sin añadir código. El toggle se hace con `data-bs-toggle="offcanvas"` — cero JS
propio para el caso base. El único JS custom necesario es un helper de < 20 líneas
que cierra el Offcanvas al navegar a un enlace del sidebar en móvil.

**Alternatives considered**:
- CSS puro con checkbox-hack: sin JS pero sin focus-trap, no accesible.
- Librería externa (Sidenav JS): viola la restricción de sin librerías nuevas.
- Bootstrap Collapse: diseñado para contenido vertical; no produce overlay, desplaza
  el contenido hacia abajo.

---

## Decisión 2: Layout Escritorio — Sidebar + Contenido

**Decision**: Flexbox en `body` / wrapper principal. Sidebar con
`position: sticky; top: 0; height: 100vh; overflow-y: auto` y ancho fijo (`240px`).
Área de contenido con `flex: 1; min-width: 0`.

**Rationale**: Sin CSS Grid externo, sin dependencias. `min-width: 0` previene que
tablas anchas rompan el flex. `sticky` mantiene el sidebar visible al hacer scroll
sin `position: fixed` (que requeriría compensar el margen del `body`).

**Alternatives considered**:
- Bootstrap `col-auto` / `col`: aumenta el número de divs, el sidebar pasa por el
  sistema de grid de 12 columnas innecesariamente.
- `position: fixed` sidebar: requiere `margin-left: 240px` en el contenido y causa
  problemas con el scroll y el print CSS. Descartado.

---

## Decisión 3: Breakpoint de Visibilidad del Sidebar

**Decision**: Bootstrap `lg` (≥ 992 px). En escritorio, sidebar siempre visible.
En móvil/tablet (< 992 px), sidebar oculto; se activa con botón en la cabecera.

**Rationale**: `md` (768 px) es demasiado estrecho para sidebar + tabla; con 240 px
de sidebar quedan ~528 px para tablas — insuficiente. `lg` deja ~752 px de contenido
en un portátil de 992 px, aceptable. `xl` (1200 px) excluye portátiles medianos.

**Alternatives considered**:
- Sidebar colapsable en escritorio (hover/botón toggle): mayor complejidad, estado
  persistente requerido. YAGNI — no pedido.

---

## Decisión 4: Variantes de Contenedor (`wide` vs `form`)

**Decision**: El bloque Jinja2 `{% block ancho_contenido %}` define la clase del
wrapper interno de cada vista. Valores: `ancho-wide` (sin límite, por defecto para
listados) y `ancho-form` (máx. 860 px, centrado, para formularios y detalle).

**Rationale**: El patrón `{% block contenedor %}` ya existe en la app — algunas
vistas sobreescriben la clase del `<main>`. Extenderlo con un bloque interno es menos
invasivo que cambiar cada template: se define un default en `base.html` y solo los
templates de formulario lo sobreescriben.

**Alternatives considered**:
- Una clase directamente en `<main>`: mezcla responsabilidades del contenedor
  (padding, scroll) con el ancho del contenido.
- Dos `base.html` distintos: duplicación de la cabecera y el sidebar.

---

## Decisión 5: Agrupación de Ítems Admin en el Sidebar

**Decision**: Los ítems de administración (Usuarios, Invitados, Plantillas, Catálogos,
Papelera) se agrupan bajo un separador etiquetado «Administración» solo cuando el rol
es `admin`. Los demás ítems van sin sección explícita arriba.

**Rationale**: Con ~12 ítems totales para admin, sin agrupación el sidebar parece una
lista plana difícil de escanear. Un separador visual es suficiente sin añadir un
acordeón o submenú (YAGNI).

**Alternatives considered**:
- Submenú desplegable para Admin: complejidad innecesaria, 5 ítems no justifican
  un árbol.
- Ninguna agrupación: válido para roles no-admin (máx. 7 ítems); aceptable también
  para admin pero menos legible.

---

## Decisión 6: Header Superior

**Decision**: Se mantiene una cabecera delgada con: marca («Seguimiento MRE» + botón
toggle del Offcanvas en móvil) a la izquierda, y el dropdown de usuario (nombre +
rol/unidad + cambiar contraseña + salir) a la derecha. En escritorio el toggle de
Offcanvas se oculta (`d-lg-none`).

**Rationale**: Eliminar completamente el header y poner la marca en el sidebar es
una opción, pero la cabecera también aloja el menú de usuario — separarlo del sidebar
simplifica el sidebar y mantiene la cohesión de «acciones de cuenta» en un lugar.

---

## Decisión 7: Print CSS

**Decision**: El sidebar se oculta en impresión con `.sidebar { display: none; }` en
el bloque `@media print` de `app.css`. No hay otros cambios en el print CSS existente.

**Rationale**: Las vistas de Informe y Cronograma tienen un botón «Imprimir» propio;
el sidebar en impresión sería ruido.
