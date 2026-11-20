# Quickstart: Validación Manual — Mejora UI Frontend

**Feature**: 001-mejora-ui-frontend | **Date**: 2026-11-19

## Prerequisitos

```bash
pip install -r requirements.txt
flask db upgrade
flask cargar-catalogos
flask crear-admin          # crea usuario admin/clave
flask run --debug
```

Abrir `http://localhost:5000` en un navegador.

## Escenarios de validación

### 1. Layout escritorio — Sidebar visible

**Setup**: ventana ≥ 992 px de ancho. Iniciar sesión como `admin`.

| Verificar | Esperado |
|---|---|
| Panel izquierdo visible | Sidebar con todos los ítems de navegación |
| Cabecera superior | Solo marca «Seguimiento MRE» + dropdown de usuario |
| No existe `navbar-toggler` en cabecera | El botón hamburguesa estándar del navbar antiguo no aparece |
| Ítem activo | El ítem de la vista actual tiene clase `.activo` o indicador visual |
| Sección «Administración» | Separador visible sobre Usuarios/Invitados/Plantillas/Catálogos/Papelera |
| Área de contenido | Ocupa el espacio a la derecha del sidebar sin scrollbar horizontal |

### 2. Layout móvil — Drawer

**Setup**: ventana < 992 px (o DevTools móvil 375 × 667).

| Verificar | Esperado |
|---|---|
| Sidebar oculto por defecto | No ocupa espacio en el layout |
| Botón toggle visible en cabecera | Ícono de menú (hamburguesa o ≡) visible |
| Pulsar toggle | Sidebar aparece como capa superpuesta (Offcanvas) sobre el contenido |
| Pulsar un enlace del sidebar | Sidebar se cierra y navega a la vista |
| Pulsar fuera del sidebar | Sidebar se cierra |
| Contenido sin sidebar | Ocupa 100 % del ancho disponible |

### 3. Variante `ancho-form` — Formulario de tarea

**Setup**: escritorio ≥ 992 px. Ir a Tareas → Nueva tarea.

| Verificar | Esperado |
|---|---|
| Formulario centrado | No ocupa todo el ancho; máx. ~860 px, centrado |
| Comparar con lista de tareas | Lista de tareas usa todo el ancho disponible |

### 4. Espaciado uniforme

**Setup**: navegar por Tareas, Alertas, Resumen y Inicio.

| Verificar | Esperado |
|---|---|
| Margen lateral del contenido | Idéntico en todas las vistas (± 2 px) |
| Espacio entre sección-titulo y tabla/contenido | Uniforme |

### 5. Rol invitado

**Setup**: crear usuario con rol `invitado`, configurar unidades, iniciar sesión.

| Verificar | Esperado |
|---|---|
| Ítems del sidebar | Solo Resumen, Agenda, Gráficos (3 ítems) |
| Sección «Administración» | No aparece |
| Intentar POST directo | 403 (guardas_globales sin cambios) |

### 6. Tests existentes — Sin regresión

```bash
pytest
```

Todos los tests deben pasar (los tests no prueban HTML).

### 7. Impresión

**Setup**: cualquier vista. Usar «Imprimir» del navegador o `Ctrl+P`.

| Verificar | Esperado |
|---|---|
| Sidebar en impresión | No aparece |
| Contenido | Se imprime igual que antes |

## Criterios de aceptación rápida

- [ ] Sidebar visible en escritorio, drawer en móvil.
- [ ] Todos los ítems del navbar antiguo existen en el sidebar con la misma lógica de permisos.
- [ ] Formularios usan `ancho-form`, listados `ancho-wide`.
- [ ] `pytest` pasa sin errores.
- [ ] No se añadieron nuevas dependencias en `requirements.txt`.
- [ ] No se añadieron librerías JS/CSS externas en `base.html`.
