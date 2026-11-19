# Feature Specification: Mejora UI Frontend

**Feature Branch**: `001-mejora-ui-frontend`

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "mejorar estilos y diseño del frontend, en cuanto al dashboard y estructura, patrones y sidebar, margins, etc. no alterar colores ni diseños, paginas propias cuando sea necesarias."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Navegación por Sidebar (Priority: P1)

Cualquier usuario autenticado navega por la aplicación usando un panel lateral (sidebar)
en lugar de la barra horizontal superior, que actualmente acumula demasiados ítems y se
colapsa en menú hamburguesa incluso en pantallas medianas.

**Why this priority**: El sidebar es el cambio estructural central del que dependen el
layout del dashboard y el aprovechamiento del espacio. Es el andamio que habilita el resto.

**Independent Test**: Puede probarse abriendo cualquier vista del sistema y verificando
que el menú lateral aparece, lista todos los ítems accesibles al rol actual, y que el
área de contenido ocupa el espacio restante.

**Acceptance Scenarios**:

1. **Given** el usuario está autenticado como cualquier rol, **When** carga cualquier
   página, **Then** ve un panel lateral izquierdo con todos los ítems de navegación
   que antes estaban en la barra superior.
2. **Given** el usuario está en pantalla ≤ 768 px, **When** carga la página,
   **Then** el sidebar está oculto por defecto y un botón lo despliega como capa
   superpuesta (drawer), sin desplazar el contenido.
3. **Given** el sidebar está desplegado en móvil, **When** el usuario pulsa un enlace
   o el área fuera del panel, **Then** el sidebar se cierra automáticamente.
4. **Given** el usuario navega a una vista, **When** esa vista es la activa,
   **Then** su ítem en el sidebar aparece marcado visualmente (estado activo).
5. **Given** el usuario es invitado, **When** carga cualquier página,
   **Then** el sidebar solo muestra Resumen, Agenda y Gráficos (igual que hoy).

---

### User Story 2 - Dashboard Reestructurado (Priority: P2)

El usuario de rol unidad, supervisor o admin abre la página de Inicio y ve los
indicadores y gráficos bien organizados en una cuadrícula con jerarquía clara,
sin que el encabezado y los accesos rápidos compitan visualmente con los datos.

**Why this priority**: El dashboard es la primera pantalla de trabajo; una estructura
más legible reduce el tiempo de orientación y hace evidente qué necesita atención.

**Independent Test**: Puede probarse cargando `/` con un usuario que tiene datos
y verificando que las tarjetas KPI, los gráficos y los accesos rápidos tienen
separación visual clara y se alinean sin desbordamientos.

**Acceptance Scenarios**:

1. **Given** el usuario tiene datos, **When** carga el Inicio, **Then** los KPIs
   aparecen en una banda superior compacta, seguida de los gráficos, y luego los
   accesos rápidos, sin mezclar secciones.
2. **Given** la pantalla tiene ≥ 1200 px, **When** el usuario ve el dashboard,
   **Then** los gráficos se distribuyen en dos columnas con alineación consistente.
3. **Given** el usuario no tiene datos o no tiene vistas habilitadas, **When** carga
   el Inicio, **Then** ve un estado vacío claro con instrucción de qué hacer.

---

### User Story 3 - Espaciado y Márgenes Consistentes (Priority: P3)

Cualquier usuario ve que las páginas de listado (Tareas, Responsables, Alertas,
Cronograma) y los formularios tienen márgenes y padding uniformes, sin que el
contenido toque los bordes del área útil ni quede demasiado alejado de ellos.

**Why this priority**: Mejora la lectura y la percepción de calidad sin riesgo de
romper funcionalidad existente.

**Independent Test**: Se verifica abriendo Tareas, Alertas y el formulario de nueva
tarea y confirmando que los márgenes laterales son iguales en todas las vistas y que
los elementos tienen el mismo espaciado vertical entre secciones.

**Acceptance Scenarios**:

1. **Given** el usuario navega entre Tareas, Alertas y Cronograma, **When** compara
   el espaciado lateral, **Then** es idéntico en todas las vistas.
2. **Given** el usuario abre un formulario (nueva tarea, nuevo usuario, etc.),
   **When** lee los campos, **Then** la separación entre grupos de campos es uniforme
   y no hay saltos bruscos de tamaño.

---

### User Story 4 - Vistas con Layout Propio (Priority: P4)

Las vistas de Inicio y las páginas de administración (Usuarios, Invitados, Plantillas,
Catálogos) usan un layout de ancho completo con sidebar, mientras que las páginas de
detalle de tarea usan un layout centrado de ancho moderado que favorece la lectura
de formularios largos.

**Why this priority**: No todas las vistas tienen las mismas necesidades de ancho;
forzar el mismo contenedor a todo produce páginas con exceso o escasez de espacio.

**Independent Test**: Se prueba abriendo el detalle de una tarea y la lista de tareas
y verificando que el primero usa un contenedor más estrecho que el segundo.

**Acceptance Scenarios**:

1. **Given** el usuario abre el listado de Tareas o Alertas, **When** ve la tabla,
   **Then** ocupa el ancho disponible sin scrollbar horizontal innecesario.
2. **Given** el usuario abre el detalle/formulario de una tarea, **When** ve el
   formulario, **Then** el contenido tiene un ancho máximo cómodo para leer
   (~860 px) y está centrado.

---

### Edge Cases

- ¿Qué ocurre en pantallas muy estrechas (< 360 px)? El sidebar no debe romper el layout.
- ¿Qué ocurre si el sidebar tiene ítems de admin y de invitado en el mismo menú? No puede suceder, pero el layout debe funcionar con la lista más corta (invitado: 3 ítems) y la más larga (admin: ~12 ítems).
- ¿Qué ocurre en la pantalla de cambio de contraseña temporal, donde no hay menú? El sidebar no debe aparecer; el layout centrado de autenticación se mantiene igual.
- ¿El sidebar afecta las páginas de error (404, 403, 500)? No; esas páginas no muestran navegación.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST mostrar los ítems de navegación en un panel lateral
  izquierdo para todos los usuarios autenticados que no estén en flujo de cambio
  de contraseña temporal.
- **FR-002**: El sidebar MUST colapsar a un drawer (capa superpuesta) en pantallas
  < 768 px, activado por un botón de menú en la cabecera.
- **FR-003**: El ítem del sidebar correspondiente a la vista activa MUST tener un
  estado visual diferenciado (fondo o indicador lateral).
- **FR-004**: Los ítems del sidebar MUST filtrarse por rol exactamente igual que hoy
  (misma lógica `puede_ver_vista`); no se añaden ni quitan secciones.
- **FR-005**: La cabecera superior MUST reducirse a marca + botón de menú móvil +
  menú de usuario (nombre, rol, cambiar contraseña, salir); los ítems de
  navegación se trasladan al sidebar.
- **FR-006**: El dashboard (Inicio) MUST mostrar KPIs en una banda superior, gráficos
  en cuadrícula de dos columnas en escritorio, y accesos rápidos en sección inferior
  claramente separada.
- **FR-007**: Las vistas de listado y tablero MUST usar ancho completo del área
  de contenido (equivalente al `container-fluid` actual).
- **FR-008**: Las vistas de formulario/detalle MUST usar un contenedor de ancho
  limitado (máx. ~860 px) centrado en el área de contenido.
- **FR-009**: El espaciado vertical entre secciones (encabezado de vista, filtros,
  tabla/contenido, paginación) MUST ser uniforme en todas las vistas (un único
  valor de espaciado definido como variable CSS).
- **FR-010**: Los colores, chips de alerta, barras del Gantt, calendarios, KPI cards
  y cualquier otro componente visual existente MUST permanecer sin cambios de color
  ni de estilo interno.
- **FR-011**: El layout MUST funcionar correctamente con y sin LibreOffice disponible
  (el botón PDF no es parte del layout).

### Key Entities

- **Layout de página**: estructura base (`base.html`) que define sidebar, cabecera y
  área de contenido; aplica a todas las vistas autenticadas.
- **Layout wide**: variante para listados y tableros (ancho completo).
- **Layout form**: variante para formularios y detalle de tarea (ancho limitado centrado).
- **Sidebar**: panel de navegación lateral con ítems filtrados por rol.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Todos los ítems de navegación son accesibles desde el sidebar en ≤ 1
  clic desde cualquier vista, sin que el usuario necesite hacer scroll en el sidebar
  para verlos todos (en pantallas ≥ 900 px de alto).
- **SC-002**: En pantalla de 1280 × 800 px el contenido del dashboard no produce
  scrollbar horizontal.
- **SC-003**: En pantalla de 375 × 667 px (móvil estándar) el sidebar se oculta
  por defecto y el contenido ocupa el 100 % del ancho disponible.
- **SC-004**: El espaciado lateral del contenido es idéntico (± 2 px) en al menos
  5 vistas distintas (Tareas, Alertas, Resumen, Formulario tarea, Inicio).
- **SC-005**: Ningún test existente falla como consecuencia de los cambios de layout
  (los tests no prueban HTML/CSS, solo lógica; este criterio verifica que no se
  alteraron rutas ni contextos de plantilla).
- **SC-006**: El tiempo de carga visual de cualquier vista no aumenta respecto al
  estado actual (no se añaden dependencias JS/CSS nuevas pesadas).

## Assumptions

- Bootstrap 5.3.3 (ya instalado) provee las utilidades de grid, flex y breakpoints
  necesarias para el sidebar; no se añade ninguna librería CSS/JS nueva.
- El sidebar se implementa con HTML/CSS puro + mínimo JS vanilla (toggle del drawer
  en móvil), coherente con la restricción "sin frameworks JS" del proyecto.
- Los ítems de administración (Usuarios, Invitados, Plantillas, Catálogos, Papelera)
  se agrupan visualmente en el sidebar bajo una sección «Administración» solo para
  roles admin, sin cambiar la lógica de permisos.
- Las páginas de autenticación (`/login`, `/cambiar-clave`) mantienen su layout
  centrado actual y no se ven afectadas.
- «Páginas propias cuando sea necesario» se interpreta como bloques `{% block contenedor %}`
  diferenciados en Jinja2, no como blueprints o rutas nuevas.
- El sidebar no tiene estado persistente entre sesiones (siempre abierto en escritorio,
  cerrado en móvil al cargar).
