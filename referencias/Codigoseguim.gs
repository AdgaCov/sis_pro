/**
 * BOLIVIA EN EL MUNDO — Seguimiento de tareas y trámites con el MRE (versión 2)
 * Aplicación web gratuita (Google Apps Script) con acceso por unidad organizacional.
 *
 *  - Cada unidad entra con su usuario y contraseña y SOLO ve y edita sus tareas.
 *  - PLANIFICACION ve todo: resumen ejecutivo, alertas, cronograma, todas las unidades y usuarios.
 *  - Tipos de tarea: Tarea interna · Solicitud al MRE · Autorización del MRE ·
 *    Gestión con el MRE (habilita otra tarea).
 *  - El RESUMEN EJECUTIVO solo considera solicitudes, autorizaciones y gestiones con el MRE,
 *    y se publica en la hoja «RESUMEN EJECUTIVO MRE», que puede alimentar la Agenda digital.
 *  - Las listas desplegables (tipos, instancias del MRE, estados, prioridades) se editan en la
 *    hoja CATALOGOS, sin tocar código.
 *
 * Instalación (una sola vez):
 *  1. Abrir la matriz como Hoja de cálculo de Google > Extensiones > Apps Script.
 *  2. Pegar este archivo en Código.gs y crear el archivo HTML «Index» con su contenido.
 *  3. Ejecutar la función  instalar  y anotar las contraseñas temporales del registro.
 *  4. Implementar > Nueva implementación > Aplicación web
 *       Ejecutar como: Yo   ·   Quién tiene acceso: Cualquier usuario
 *  Si ya tenía la versión 1 instalada: pegue ambos archivos, ejecute instalar
 *  y luego Implementar > Gestionar implementaciones > Editar > Nueva versión.
 */

// ------------------------------------------------------------------ CONFIGURACIÓN
var HOJA_TAREAS = 'TAREAS';
var HOJA_RESP = 'RESPONSABLES';
var HOJA_CAT = 'CATALOGOS';
var HOJA_USUARIOS = 'USUARIOS';
var HOJA_RESUMEN = 'RESUMEN EJECUTIVO MRE';
var HORAS_SESION = 8;
var MAX_INTENTOS = 5;
var DIAS_POR_VENCER = 3;     // alerta «POR VENCER» cuando faltan estos días o menos
var DIAS_SIN_ACTUALIZAR = 7; // alerta «SIN ACTUALIZAR» cuando nadie la tocó en estos días

var UNIDADES = [
  { usuario: 'DGE-STAF', nombre: 'DGE - STAF',                                         hojaAnterior: 'DGE-STAF' },
  { usuario: 'UAF',      nombre: 'UAF - Unidad Administrativa Financiera',             hojaAnterior: 'UAF' },
  { usuario: 'UPT',      nombre: 'UPT - Unidad de Promoción Turística',                hojaAnterior: 'UPT' },
  { usuario: 'UDTP',     nombre: 'UDTP - Unidad de Desarrollo Turístico y Proyectos',  hojaAnterior: 'UDTP' },
  { usuario: 'UEP',      nombre: 'UEP - Unidad Ejecutora del Programa BID 4643/BL-BO', hojaAnterior: 'UEP_BID 4643BL-BO ' },
  { usuario: 'SISTEMAS', nombre: 'Área de Sistemas',                                    hojaAnterior: '' }
];
var USUARIO_PLAN = 'PLANIFICACION';
var USUARIO_DGE = 'DGE';                       // Dirección General Ejecutiva: acceso a todo
var NIVELES_RIESGO = ['Alto', 'Medio', 'Bajo'];

// Cargos responsables precargados por unidad (Planificación puede moverlos de unidad desde la app)
// Cargo comodín en cada unidad para asignar provisionalmente a alguien del personal cuando un cargo está acéfalo
var CARGO_APOYO = 'Apoyo';
var CARGOS_INICIALES = {
  'DGE-STAF': ['Técnico en Planificación', 'Técnico Administrativo Director General Ejecutivo', 'Secretaria'],
  'UAF': ['Jefe Administrativo Financiero', 'Profesional en Presupuesto, Contabilidad y Tesorería',
          'Profesional en Contrataciones', 'Técnico en Recursos Humanos', 'Mensajero'],
  'SISTEMAS': ['Técnico en Sistemas'],
  'UPT': ['Técnico en Diseño Gráfico', 'Técnico en Fotografía'],
  'UDTP': ['Jefe de Desarrollo Turístico y Proyectos', 'Profesional en Turismo', 'Profesional en Preparación y Evaluación de Proyectos',
           'Profesional en Ingeniería de Proyectos', 'Profesional en Infraestructura', 'Profesional en Arquitectura II',
           'Profesional en Medio Ambiente'],
  'UEP': ['Coordinador del Programa', 'Especialista Administrativo Financiero', 'Especialista en Planificación y Monitoreo',
          'Especialista en Infraestructura', 'Especialista en Adquisiciones', 'Especialista Legal', 'Profesional Ambiental',
          'Profesional Arquitecto', 'Ingeniero Civil II', 'Ingeniero Civil I',
          'Técnico en Gestión Documental y Organización de Archivo']
};

var TIPO_INTERNA = 'Tarea interna';
var CAT_DEFECTO = {
  TIPOS: [TIPO_INTERNA, 'Solicitud al MRE', 'Autorización del MRE', 'Gestión con el MRE (habilita otra tarea)'],
  INSTANCIAS: [
    'Dirección General de Asuntos Administrativos',
    'Dirección General de Asuntos Jurídicos',
    'Dirección General de Planificación',
    'Despacho Ministerial',
    'Viceministerio de Comercio Exterior, Inversiones Extranjeras e Integración',
    'Viceministerio de Turismo Sostenible y Culturas',
    'Viceministerio de Relaciones Exteriores',
    'Viceministerio de Gestión Consular e Institucional',
    'Unidad de Comunicación',
    'ADECINE',
    'Orquesta Sinfónica Nacional',
    'CIAAAT',
    'Otras'
  ],
  ESTADOS: ['Pendiente', 'En proceso', 'Remitido a DGE', 'Con V.º B.º de DGE', 'Ingresado por Ventanilla Única',
    'Remitido a instancia del MRE', 'En instancia del MRE – Sin respuesta', 'Observado / Devuelto',
    'Respuesta recibida del MRE', 'Autorizado', 'Concluido', 'Otro'],
  PRIORIDADES: ['Alta', 'Media', 'Baja'],
  // Áreas funcionales según las atribuciones de Bolivia en el Mundo (entidad desconcentrada del MRE)
  AREAS: [
    'Gestión institucional / Planificación',
    'Administración y finanzas',
    'Asuntos jurídicos y convenios',
    'Promoción turística (ferias, campañas, Marca País)',
    'Desarrollo turístico y proyectos de inversión',
    'Diplomacia cultural e imagen país',
    'Cooperación y financiamiento externo',
    'Comunicación y contenidos digitales',
    'Capacitación y asistencia técnica',
    'Tecnología y sistemas'
  ]
};

// columnas de la hoja TAREAS (orden fijo)
var COLS = [
  ['id', 'ID'], ['unidad', 'UNIDAD'], ['tipo', 'TIPO'], ['tarea', 'TAREA / ASUNTO'],
  ['instancia', 'INSTANCIA DEL MRE'], ['gestion', 'GESTIÓN REQUERIDA'], ['habilita', '¿QUÉ HABILITA?'],
  ['habilitaA', 'HABILITA LA TAREA (ID)'], ['riesgo', 'RIESGO POR DEMORA'], ['responsable', 'RESPONSABLE (CARGO)'],
  ['hojaRuta', 'HOJA DE RUTA'], ['fechaSol', 'FECHA SOLICITUD / INICIO'], ['fechaLim', 'FECHA LÍMITE'],
  ['estado', 'ESTADO'], ['prioridad', 'PRIORIDAD'], ['resultado', 'RESULTADO OBTENIDO'],
  ['medio', 'MEDIO DE VERIFICACIÓN'], ['fechaFin', 'FECHA CONCLUSIÓN'], ['obs', 'OBSERVACIONES'], ['actualizado', 'ÚLTIMA ACTUALIZACIÓN'],
  ['actualizadoPor', 'ACTUALIZADO POR'], ['adjuntos', 'ARCHIVOS DE RESPALDO'],
  ['nivelRiesgo', 'NIVEL DE RIESGO'], ['solucion', 'LÍNEA DE SOLUCIÓN'], ['plazoSolucion', 'PLAZO DE LA SOLUCIÓN'],
  ['area', 'ÁREA FUNCIONAL'], ['subtareas', 'SUBTAREAS / PASOS'], ['agendaId', 'ID EN AGENDA DESPACHO']
];
var AGENDA_ID = '1YxlEA8gJkAPR7LiA6z2ZWdqcpdYnAjVMa_X5BB9CQTU';   // hoja «Agenda Despacho- BOLMUN»
var CARPETA_RESPALDOS = 'Medios de verificación – Seguimiento MRE';
var MAX_MB_ARCHIVO = 10;
var FECHAS = ['fechaSol', 'fechaLim', 'fechaFin', 'actualizado', 'plazoSolucion'];
var EDITABLES = ['tipo', 'tarea', 'instancia', 'gestion', 'habilita', 'habilitaA', 'riesgo', 'responsable',
  'hojaRuta', 'fechaSol', 'fechaLim', 'estado', 'prioridad', 'resultado', 'medio', 'fechaFin', 'obs', 'nivelRiesgo', 'solucion', 'plazoSolucion', 'area', 'subtareas'];

// ------------------------------------------------------------------ INSTALACIÓN
/** Ejecutar desde el editor. Se puede repetir sin perder datos ni contraseñas. */
function instalar() {
  soloDueno_();
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var informe = [];

  // TAREAS
  var t = ss.getSheetByName(HOJA_TAREAS);
  if (!t) {
    t = ss.insertSheet(HOJA_TAREAS, 0);
    encabezado_(t, COLS.map(function (c) { return c[1]; }));
    t.setFrozenRows(1);
    var n = migrarMatriz_(t);
    informe.push(n ? 'Se migraron ' + n + ' trámites de las pestañas anteriores (las pestañas anteriores quedaron ocultas, sin cambios).'
                   : 'Hoja TAREAS creada.');
  } else {
    encabezado_(t, COLS.map(function (c) { return c[1]; }));
    informe.push('Hoja TAREAS ya existía: se conservaron sus datos.');
  }

  // RESPONSABLES
  informe.push(prepararResponsables_());

  // CATALOGOS
  if (!ss.getSheetByName(HOJA_CAT)) {
    var c = ss.insertSheet(HOJA_CAT);
    encabezado_(c, ['TIPOS', 'INSTANCIAS', 'ESTADOS', 'PRIORIDADES', 'ÁREAS FUNCIONALES']);
    var largo = Math.max(CAT_DEFECTO.TIPOS.length, CAT_DEFECTO.INSTANCIAS.length, CAT_DEFECTO.ESTADOS.length, CAT_DEFECTO.AREAS.length);
    var filas = [];
    for (var i = 0; i < largo; i++) {
      filas.push([CAT_DEFECTO.TIPOS[i] || '', CAT_DEFECTO.INSTANCIAS[i] || '', CAT_DEFECTO.ESTADOS[i] || '', CAT_DEFECTO.PRIORIDADES[i] || '', CAT_DEFECTO.AREAS[i] || '']);
    }
    c.getRange(2, 1, filas.length, 5).setValues(filas);
    c.getRange(1, 7).setValue('Puede agregar, quitar o renombrar opciones en estas columnas. No cambie el texto «Tarea interna» ni «Concluido».');
    informe.push('Hoja CATALOGOS creada (listas desplegables editables).');
  } else {
    var cat = ss.getSheetByName(HOJA_CAT);
    if (String(cat.getRange(1, 5).getValue()).trim() === '') {
      cat.getRange(1, 5).setValue('ÁREAS FUNCIONALES').setFontWeight('bold').setBackground(cat.getRange(1, 1).getBackground()).setFontColor(cat.getRange(1, 1).getFontColor());
      cat.getRange(2, 5, CAT_DEFECTO.AREAS.length, 1).setValues(CAT_DEFECTO.AREAS.map(function (a) { return [a]; }));
      cat.setColumnWidth(5, 320);
      informe.push('Se agregó la lista ÁREAS FUNCIONALES en la hoja CATALOGOS (editable).');
    }
  }

  // USUARIOS
  var u = ss.getSheetByName(HOJA_USUARIOS);
  if (!u || u.getLastRow() < 2) {
    if (!u) u = ss.insertSheet(HOJA_USUARIOS);
    u.clear();
    encabezado_(u, ['USUARIO', 'PESTAÑA', 'HASH', 'SAL', 'ACTIVO', 'DEBE CAMBIAR CLAVE']);
    var lista = [[USUARIO_PLAN, 'TODAS'], [USUARIO_DGE, 'TODAS']].concat(UNIDADES.map(function (x) { return [x.usuario, x.usuario]; }));
    var filasU = [];
    informe.push('CONTRASEÑAS TEMPORALES (se pedirá cambiarlas al primer ingreso):');
    lista.forEach(function (x) {
      var clave = claveAleatoria_(), sal = Utilities.getUuid();
      filasU.push([x[0], x[1], hash_(clave, sal), sal, true, true]);
      informe.push('   ' + x[0] + '  →  ' + clave);
    });
    u.getRange(2, 1, filasU.length, 6).setValues(filasU);
    u.hideColumns(3, 2);
  } else {
    var existentes = todosUsuarios_().map(function (x) { return x.usuario; });
    [[USUARIO_DGE, 'TODAS']].concat(UNIDADES.map(function (x) { return [x.usuario, x.usuario]; })).forEach(function (x) {
      if (existentes.indexOf(x[0]) >= 0) return;
      var clave = claveAleatoria_(), sal = Utilities.getUuid();
      u.getRange(u.getLastRow() + 1, 1, 1, 6).setValues([[x[0], x[1], hash_(clave, sal), sal, true, true]]);
      informe.push('USUARIO NUEVO ' + x[0] + (x[1] === 'TODAS' ? ' (acceso a todo)' : '') + '  →  contraseña temporal: ' + clave);
    });
    informe.push('Usuarios existentes conservados (las contraseñas no cambiaron).');
  }

  UNIDADES.forEach(function (un) { carpetaUnidad_(un.usuario); });
  try { iconoUrl_(); informe.push('Ícono de la app listo.'); } catch (e) { informe.push('No se pudo crear el ícono: ' + e.message); }
  informe.push('Carpeta de Drive «' + CARPETA_RESPALDOS + '» lista para los archivos de respaldo (no se comparte con nadie).');
  actualizarResumen_();
  informe.push('Hoja «' + HOJA_RESUMEN + '» lista para la Agenda digital. En la agenda puede usar:');
  informe.push('   =IMPORTRANGE("' + ss.getUrl() + '"; "\'' + HOJA_RESUMEN + '\'!A1:S")');

  console.log(informe.join('\n'));
  try { SpreadsheetApp.getUi().alert(informe.join('\n')); } catch (e) { /* sin interfaz */ }
}

/** Crea la hoja RESPONSABLES (UNIDAD | CARGO | NOMBRE | ACTIVO) y precarga los cargos que falten. */
function prepararResponsables_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(HOJA_RESP);
  var previos = [];
  if (!sh) sh = ss.insertSheet(HOJA_RESP);
  else if (sh.getLastRow() > 1 && String(sh.getRange(1, 2).getValue()).toUpperCase() === 'NOMBRE') {
    // formato anterior UNIDAD | NOMBRE | CARGO | ACTIVO
    previos = sh.getRange(2, 1, sh.getLastRow() - 1, 4).getValues()
      .map(function (r) { return [r[0], r[2] || r[1], r[2] ? r[1] : '', r[3]]; });
    sh.clear();
  }
  encabezado_(sh, ['UNIDAD', 'CARGO', 'NOMBRE (PERSONA DESIGNADA)', 'ACTIVO']);
  if (previos.length) sh.getRange(2, 1, previos.length, 4).setValues(previos);
  // el Técnico en Sistemas pasa de UAF al Área de Sistemas
  var ts = leerResponsables_().filter(function (r) { return r.cargo.toUpperCase() === 'TÉCNICO EN SISTEMAS'; });
  if (ts.length === 1 && ts[0].unidad === 'UAF') sh.getRange(ts[0].fila, 1).setValue('SISTEMAS');
  var existentes = leerResponsables_().map(function (r) { return r.unidad + '|' + r.cargo.toUpperCase(); });
  var nuevos = [];
  Object.keys(CARGOS_INICIALES).forEach(function (u) {
    CARGOS_INICIALES[u].concat([CARGO_APOYO]).forEach(function (cargo) {
      if (existentes.indexOf(u + '|' + cargo.toUpperCase()) < 0) nuevos.push([u, cargo, '', true]);
    });
  });
  if (nuevos.length) sh.getRange(sh.getLastRow() + 1, 1, nuevos.length, 4).setValues(nuevos);
  return 'Responsables: ' + nuevos.length + ' cargos precargados (cada unidad puede agregar nombres o más cargos desde la app).';
}

/** Copia los trámites de las pestañas de la matriz anterior (si existen) y las oculta. */
function migrarMatriz_(destino) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var filas = [], ahora = new Date();
  UNIDADES.forEach(function (un) {
    var sh = buscarHoja_(un.hojaAnterior);
    if (!sh) return;
    var vals = sh.getRange(7, 1, 60, 10).getValues();
    var k = 0;
    vals.forEach(function (r) {
      if (String(r[1]).trim() === '') return;
      k++;
      var o = {
        id: un.usuario + '-' + ('00' + k).slice(-3), unidad: un.usuario, tipo: 'Solicitud al MRE',
        tarea: r[1], instancia: r[2], gestion: r[3], habilita: r[4], riesgo: r[5],
        fechaSol: r[6] instanceof Date ? r[6] : '', estado: r[7], prioridad: r[8], obs: r[9],
        actualizado: ahora, actualizadoPor: 'MIGRACIÓN'
      };
      filas.push(COLS.map(function (c) { return o[c[0]] === undefined ? '' : o[c[0]]; }));
    });
  });
  if (filas.length) {
    destino.getRange(2, 1, filas.length, COLS.length).setValues(filas);
    formatoFechas_(destino);
    UNIDADES.forEach(function (un) { var sh = buscarHoja_(un.hojaAnterior); if (sh) sh.hideSheet(); });
    var res = ss.getSheetByName('RESUMEN EJECUTIVO');
    if (res) res.hideSheet();
  }
  return filas.length;
}

// ------------------------------------------------------------------ WEB
// doGet() está en el archivo «Proyectos»: abre esta app o, con ?m=proyectos, el módulo de Seguimiento de Proyectos.

/** Guarda el ícono de la app en Drive (solo ese archivo es visible con enlace) y devuelve su dirección. */
function iconoUrl_() {
  var props = PropertiesService.getScriptProperties();
  var url = props.getProperty('ICONO_URL');
  if (url) return url;
  var raiz = DriveApp.getFolderById(props.getProperty('CARPETA_RAIZ'));
  var f = raiz.createFile(Utilities.newBlob(Utilities.base64Decode(ICONO_B64), 'image/png', 'icono-app-seguimiento-mre.png'));
  f.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  url = 'https://drive.google.com/uc?export=view&id=' + f.getId() + '#.png';
  props.setProperty('ICONO_URL', url);
  return url;
}

// Ícono de la app (PNG 192 × 192)
var ICONO_B64 = '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';

// ------------------------------------------------------------------ SESIÓN
function autenticar_(usuario, clave) {
  usuario = String(usuario || '').trim().toUpperCase();
  var cache = CacheService.getScriptCache();
  var kInt = 'int_' + usuario;
  var intentos = Number(cache.get(kInt) || 0);
  if (intentos >= MAX_INTENTOS) throw new Error('Usuario bloqueado temporalmente por intentos fallidos. Intente en 15 minutos.');
  var u = leerUsuario_(usuario);
  if (!u || !u.activo || hash_(String(clave || ''), u.sal) !== u.hash) {
    cache.put(kInt, String(intentos + 1), 900);
    Utilities.sleep(600);
    throw new Error('Usuario o contraseña incorrectos.');
  }
  cache.remove(kInt);
  var token = Utilities.getUuid() + Utilities.getUuid().replace(/-/g, '');
  cache.put('ses_' + token, usuario + '|' + Date.now(), HORAS_SESION * 3600);
  return { u: u, token: token };
}

/** Ingreso único (app Seguimiento MRE). Los usuarios solo de proyectos pasan directo al módulo. */
function login(usuario, clave) {
  var a = autenticar_(usuario, clave);
  if (String(a.u.hoja).trim().toUpperCase() === 'PROYECTOS') return { irProyectos: irA(a.token, 'proyectos') };
  return Object.assign({ token: a.token }, perfil_(a.u));
}

/** Pase de un solo uso (2 minutos) para moverse entre la app y el módulo de proyectos sin volver a ingresar. */
function irA(token, destino) {
  var u = validar_(token);
  if (destino === 'proyectos') { if (!urlProyectos_(u)) throw new Error('Su usuario no tiene acceso al módulo de proyectos.'); }
  else if (String(u.hoja).trim().toUpperCase() === 'PROYECTOS') throw new Error('Su usuario es solo del módulo de proyectos.');
  var c = (Utilities.getUuid() + Utilities.getUuid()).replace(/-/g, '');
  CacheService.getScriptCache().put('pase_' + c, token, 120);
  return ScriptApp.getService().getUrl() + (destino === 'proyectos' ? '?m=proyectos&' : '?') + 'pase=' + c;
}
function canjearPase_(c) {
  if (!/^[a-f0-9]{64}$/.test(String(c || ''))) throw new Error('SESION: Ingrese desde la app Seguimiento MRE.');
  var cache = CacheService.getScriptCache(), t = cache.get('pase_' + c);
  if (!t) throw new Error('SESION: El acceso expiró. Ingrese nuevamente desde la app Seguimiento MRE.');
  cache.remove('pase_' + c);
  validar_(t);
  return t;
}
/** La app recibe el pase: abre la sesión sin pedir la contraseña otra vez. */
function sesionPase(c) {
  var t = canjearPase_(c), u = validar_(t);
  if (String(u.hoja).trim().toUpperCase() === 'PROYECTOS') return { irProyectos: irA(t, 'proyectos') };
  return Object.assign({ token: t }, perfil_(u));
}
/** El módulo de proyectos recibe el pase. */
function pxSesionPase(c) {
  var t = canjearPase_(c), yo = pxYo_(t);                  // archivo «Proyectos»
  return { token: t, me: yo, debeCambiar: !!yo.debeCambiar };
}

/** Enlace al módulo de proyectos si el usuario tiene un rol allí (para el botón «Proyectos»). */
function urlProyectos_(u) {
  try {
    if (typeof pxRows_ !== 'function') return '';
    var tiene = pxRows_('PROY_ROLES').some(function (r) { return String(r.usuario || '').trim().toUpperCase() === u.usuario && String(r.rol || '').trim(); });
    return tiene ? ScriptApp.getService().getUrl() + '?m=proyectos' : '';
  } catch (e) { return ''; }
}

function sesion(token) { return perfil_(validar_(token)); }

function cerrarSesion(token) { CacheService.getScriptCache().remove('ses_' + token); return true; }

function cambiarClave(token, actual, nueva) {
  var u = validar_(token);
  if (hash_(String(actual || ''), u.sal) !== u.hash) throw new Error('La contraseña actual no es correcta.');
  validarClaveNueva_(nueva);
  guardarClave_(u, nueva, false);
  return true;
}


// ------------------------------------------------------------------ RECUPERACIÓN DE CONTRASEÑA
/** EMERGENCIA: ejecutar desde el editor. Crea una contraseña temporal nueva para PLANIFICACION. */
function recuperarPlanificacion() {
  soloDueno_();
  var u = leerUsuario_(USUARIO_PLAN);
  var clave = claveAleatoria_();
  guardarClave_(u, clave, true);
  hojaUsuarios_().getRange(u.fila, 5).setValue(true);
  CacheService.getScriptCache().remove('int_' + USUARIO_PLAN);
  console.log('Nueva contraseña temporal de PLANIFICACION: ' + clave + '  (se pedirá cambiarla al ingresar)');
}

/** Paso 1 desde la pantalla de ingreso: envía un código al correo de la cuenta dueña (solo PLANIFICACION). */
function solicitarRecuperacion(usuario) {
  usuario = String(usuario || '').trim().toUpperCase();
  var ur = leerUsuario_(usuario);
  if (!ur || !esPlan_(ur)) {
    return { tipo: 'unidad', msg: 'Pida a Planificación que restablezca su contraseña desde la pestaña Usuarios de la app.' };
  }
  var cache = CacheService.getScriptCache();
  if (cache.get('rec_espera_' + usuario)) throw new Error('Ya se envió un código hace poco. Revise su correo (también la carpeta de spam) o espere 2 minutos.');
  var envios = Number(cache.get('rec_dia_' + usuario) || 0);
  if (envios >= 5) throw new Error('Se alcanzó el máximo de códigos por hoy. Intente más tarde o use la recuperación desde el editor.');
  cache.put('rec_dia_' + usuario, String(envios + 1), 21600);
  var codigo = String(100000 + azar_(900000));
  cache.put('rec_cod_' + usuario, codigo, 900);
  cache.put('rec_int_' + usuario, '0', 900);
  cache.put('rec_espera_' + usuario, '1', 120);
  var correo = Session.getEffectiveUser().getEmail();
  MailApp.sendEmail(correo, 'Código para recuperar la contraseña · Seguimiento MRE',
    'Su código para restablecer la contraseña de ' + usuario + ' es: ' + codigo +
    '\n\nVence en 15 minutos. Si usted no lo solicitó, ignore este correo.\n\nBolivia en el Mundo · Seguimiento de tareas y trámites con el MRE');
  return { tipo: 'plan', msg: 'Enviamos un código de 6 dígitos a ' + ocultarCorreo_(correo) + '. Vence en 15 minutos.' };
}

/** Paso 2: valida el código y guarda la contraseña nueva de PLANIFICACION. */
function restablecerConCodigo(usuario, codigo, nueva) {
  usuario = String(usuario || '').trim().toUpperCase();
  var u = leerUsuario_(usuario);
  if (!u || !esPlan_(u)) throw new Error('Este usuario no puede recuperar su contraseña con código. Pida el restablecimiento a Planificación.');
  var cache = CacheService.getScriptCache();
  var real = cache.get('rec_cod_' + usuario);
  var n = Number(cache.get('rec_int_' + usuario) || 0);
  if (!real) throw new Error('El código venció o no fue solicitado. Pida uno nuevo.');
  if (n >= 5) { cache.remove('rec_cod_' + usuario); throw new Error('Demasiados intentos. Pida un código nuevo.'); }
  if (String(codigo || '').trim() !== real) { cache.put('rec_int_' + usuario, String(n + 1), 900); Utilities.sleep(600); throw new Error('El código no es correcto.'); }
  validarClaveNueva_(nueva);
  guardarClave_(u, nueva, false);
  cerrarSesiones_(u.usuario);
  hojaUsuarios_().getRange(u.fila, 5).setValue(true);
  cache.remove('rec_cod_' + usuario); cache.remove('int_' + usuario);
  return true;
}

function ocultarCorreo_(c) { var p = String(c).split('@'); return p[0].slice(0, 3) + '•••@' + (p[1] || ''); }

// ------------------------------------------------------------------ DATOS
/** Todo lo que el usuario puede ver: sus tareas (o todas, si es Planificación) y responsables. */
function obtenerDatos(token) {
  var u = validar_(token);
  try { sincronizarAgenda_(false); } catch (e) { console.warn('Agenda: ' + e); }
  var plan = esPlan_(u);
  var tareas = leerTareas_().filter(function (t) { return plan || t.unidad === u.usuario; });
  var resp = leerResponsables_().filter(function (r) { return plan || r.unidad === u.usuario; });
  return { tareas: tareas, responsables: resp, hoy: hoyIso_() };
}

function guardarTarea(token, datos) {
  var u = validar_(token);
  datos = datos || {};
  var unidad = unidadPermitida_(u, datos.unidad);
  if (!String(datos.tarea || '').trim()) throw new Error('La TAREA / ASUNTO es obligatoria.');
  if (!String(datos.tipo || '').trim()) throw new Error('Seleccione el TIPO de tarea.');

  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var sh = hojaTareas_();
    var todas = leerTareasCrudas_();
    var fila, actual = null;
    if (datos.id) {
      for (var i = 0; i < todas.length; i++) if (todas[i].id === datos.id) { actual = todas[i]; fila = i + 2; break; }
      if (!actual) throw new Error('La tarea ya no existe (pudo ser eliminada).');
      if (!esPlan_(u) && actual.unidad !== u.usuario) throw new Error('No tiene acceso a esa tarea.');
      if (actual.unidad !== unidad.usuario && !esPlan_(u)) throw new Error('Solo la DGE o Planificación pueden reasignar una tarea a otra unidad.');
    }
    if (datos.habilitaA) {
      var obj = todas.filter(function (t) { return t.id === datos.habilitaA; })[0];
      if (!obj) throw new Error('La tarea que habilita ya no existe.');
      if (!esPlan_(u) && obj.unidad !== unidad.usuario) throw new Error('La tarea que habilita debe ser de la misma unidad.');
      if (datos.habilitaA === datos.id) throw new Error('Una tarea no puede habilitarse a sí misma.');
    }
    var o = actual ? actual : { id: siguienteId_(todas, unidad.usuario), unidad: unidad.usuario };
    var idAnterior = '';
    if (actual && actual.unidad !== unidad.usuario) {
      // reasignación a otra unidad (DGE o Planificación): nuevo código en la unidad de destino
      idAnterior = actual.id;
      o.unidad = unidad.usuario;
      o.id = siguienteId_(todas, unidad.usuario);
      if (datos.habilitaA === o.id) datos.habilitaA = '';
    }
    EDITABLES.forEach(function (k) {
      if (k === 'subtareas') { o[k] = textoSubtareas_(normSubtareas_(datos[k])); return; }
      o[k] = FECHAS.indexOf(k) >= 0 ? aFecha_(datos[k]) : limpiar_(datos[k]);
    });
    if (o.estado === 'Concluido' && !o.fechaFin) o.fechaFin = aFecha_(hoyIso_());
    o.actualizado = new Date();
    o.actualizadoPor = u.usuario;
    var valores = [COLS.map(function (c) { return o[c[0]] === undefined || o[c[0]] === null ? '' : o[c[0]]; })];
    if (fila) sh.getRange(fila, 1, 1, COLS.length).setValues(valores);
    else sh.getRange(sh.getLastRow() + 1, 1, 1, COLS.length).setValues(valores);
    if (idAnterior) {
      var colH = colDe_('habilitaA');
      todas.forEach(function (x, j) { if (x.habilitaA === idAnterior) sh.getRange(j + 2, colH).setValue(o.id); });
    }
    formatoFechas_(sh);
    SpreadsheetApp.flush();
    actualizarResumen_();
  } finally {
    lock.releaseLock();
  }
  try { sincronizarAgenda_(true); } catch (e) { console.warn('Agenda: ' + e); }
  return obtenerDatos(token);
}

function borrarTarea(token, id) {
  var u = validar_(token);
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var todas = leerTareasCrudas_();
    for (var i = 0; i < todas.length; i++) {
      if (todas[i].id === id) {
        if (!esPlan_(u) && todas[i].unidad !== u.usuario) throw new Error('No tiene acceso a esa tarea.');
        aPapelera_(todas[i], u.usuario);
        hojaTareas_().deleteRow(i + 2);
        // quitar referencias de otras tareas que dependían de esta
        var sh = hojaTareas_(), col = colDe_('habilitaA');
        leerTareasCrudas_().forEach(function (t, j) { if (t.habilitaA === id) sh.getRange(j + 2, col).setValue(''); });
        SpreadsheetApp.flush();
        actualizarResumen_();
        return obtenerDatos(token);
      }
    }
    throw new Error('La tarea ya no existe.');
  } finally {
    lock.releaseLock();
  }
}

// ------------------------------------------------------------------ RESPONSABLES
/** Agrega un cargo responsable o actualiza la persona designada en él. */
function guardarResponsable(token, unidadUsuario, cargo, nombre) {
  var u = validar_(token);
  var unidad = unidadPermitida_(u, unidadUsuario);
  cargo = limpiar_(cargo); nombre = limpiar_(nombre);
  if (!cargo) throw new Error('Escriba el cargo del responsable.');
  var sh = hojaResp_();
  var existe = buscarResp_(unidad.usuario, cargo);
  if (existe) sh.getRange(existe.fila, 3, 1, 2).setValues([[nombre, true]]);
  else sh.getRange(sh.getLastRow() + 1, 1, 1, 4).setValues([[unidad.usuario, cargo, nombre, true]]);
  return obtenerDatos(token);
}

function cambiarResponsable(token, unidadUsuario, cargo, activo) {
  var u = validar_(token);
  var unidad = unidadPermitida_(u, unidadUsuario);
  var r = buscarResp_(unidad.usuario, cargo);
  if (!r) throw new Error('Responsable no encontrado.');
  hojaResp_().getRange(r.fila, 4).setValue(!!activo);
  return obtenerDatos(token);
}

/** Solo Planificación: mueve un cargo a otra unidad. */
function moverResponsable(token, unidadUsuario, cargo, nuevaUnidad) {
  var u = validar_(token);
  if (!esPlan_(u)) throw new Error('Solo Planificación puede mover cargos entre unidades.');
  var destino = unidadPermitida_(u, nuevaUnidad);
  var r = buscarResp_(String(unidadUsuario).toUpperCase(), cargo);
  if (!r) throw new Error('Responsable no encontrado.');
  if (buscarResp_(destino.usuario, cargo)) throw new Error('Ese cargo ya existe en ' + destino.usuario + '.');
  hojaResp_().getRange(r.fila, 1).setValue(destino.usuario);
  return obtenerDatos(token);
}

function buscarResp_(unidad, cargo) {
  var c = String(cargo || '').trim().toUpperCase();
  return leerResponsables_().filter(function (r) { return r.unidad === unidad && r.cargo.toUpperCase() === c; })[0] || null;
}

// ------------------------------------------------------------------ MEDIOS DE VERIFICACIÓN (ARCHIVOS)
/** Adjunta un archivo de respaldo a una tarea. Se guarda en el Drive de la cuenta dueña, sin compartir. */
function subirMedio(token, id, nombre, mime, base64) {
  var u = validar_(token);
  var bytes = Utilities.base64Decode(String(base64 || ''));
  if (!bytes.length) throw new Error('El archivo está vacío.');
  if (bytes.length > MAX_MB_ARCHIVO * 1024 * 1024) throw new Error('El archivo supera ' + MAX_MB_ARCHIVO + ' MB. Reduzca su tamaño (por ejemplo, escanee en menor resolución).');
  nombre = String(nombre || 'respaldo').replace(/[\\/:*?"<>|\n]/g, '_').slice(0, 150);
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var ref = tareaConAcceso_(u, id);
    var carpeta = carpetaUnidad_(ref.tarea.unidad);
    var f = carpeta.createFile(Utilities.newBlob(bytes, mime || 'application/octet-stream', ref.tarea.id + ' - ' + nombre));
    f.setDescription('Medio de verificación de la tarea ' + ref.tarea.id + ' · subido por ' + u.usuario);
    var lista = adjuntosDe_(ref.tarea.adjuntos);
    lista.push({ id: f.getId(), nombre: nombre });
    escribirAdjuntos_(ref, lista, u);
  } finally {
    lock.releaseLock();
  }
  return obtenerDatos(token);
}

/** Devuelve el archivo (en base64) solo si el usuario tiene acceso a la tarea. */
function descargarMedio(token, id, fileId) {
  var u = validar_(token);
  var ref = tareaConAcceso_(u, id);
  var a = adjuntosDe_(ref.tarea.adjuntos).filter(function (x) { return x.id === fileId; })[0];
  if (!a) throw new Error('El archivo no pertenece a esta tarea.');
  var blob = DriveApp.getFileById(fileId).getBlob();
  return { nombre: a.nombre, mime: blob.getContentType(), b64: Utilities.base64Encode(blob.getBytes()) };
}

/** Quita un archivo de la tarea y lo envía a la papelera de Drive (recuperable 30 días). */
function quitarMedio(token, id, fileId) {
  var u = validar_(token);
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var ref = tareaConAcceso_(u, id);
    var lista = adjuntosDe_(ref.tarea.adjuntos);
    if (!lista.some(function (x) { return x.id === fileId; })) throw new Error('El archivo no pertenece a esta tarea.');
    try { DriveApp.getFileById(fileId).setTrashed(true); } catch (e) { /* ya no existe */ }
    escribirAdjuntos_(ref, lista.filter(function (x) { return x.id !== fileId; }), u);
  } finally {
    lock.releaseLock();
  }
  return obtenerDatos(token);
}

function tareaConAcceso_(u, id) {
  var todas = leerTareasCrudas_();
  for (var i = 0; i < todas.length; i++) {
    if (todas[i].id === id) {
      if (!esPlan_(u) && todas[i].unidad !== u.usuario) throw new Error('No tiene acceso a esa tarea.');
      return { tarea: todas[i], fila: i + 2 };
    }
  }
  throw new Error('La tarea no existe. Guárdela antes de adjuntar archivos.');
}

// En la hoja: una línea por archivo «nombre — https://drive.google.com/file/d/ID/view»
function adjuntosDe_(texto) {
  return String(texto || '').split('\n').map(function (l) {
    var m = l.match(/^(.*) — https:\/\/drive\.google\.com\/file\/d\/([^\/]+)\//);
    return m ? { nombre: m[1], id: m[2] } : null;
  }).filter(Boolean);
}
function escribirAdjuntos_(ref, lista, u) {
  var txt = lista.map(function (a) { return a.nombre + ' — https://drive.google.com/file/d/' + a.id + '/view'; }).join('\n');
  var sh = hojaTareas_();
  sh.getRange(ref.fila, colDe_('adjuntos')).setValue(txt);
  sh.getRange(ref.fila, colDe_('actualizado'), 1, 2).setValues([[new Date(), u.usuario]]);
  SpreadsheetApp.flush();
  actualizarResumen_();
}
function textoMedio_(t) {
  var n = adjuntosDe_(t.adjuntos).length;
  return [t.medio, n ? n + (n === 1 ? ' archivo adjunto' : ' archivos adjuntos') : ''].filter(String).join(' · ');
}
function carpetaUnidad_(unidad) {
  var props = PropertiesService.getScriptProperties();
  var raizId = props.getProperty('CARPETA_RAIZ'), raiz = null;
  if (raizId) { try { raiz = DriveApp.getFolderById(raizId); } catch (e) { raiz = null; } }
  if (!raiz) { raiz = DriveApp.createFolder(CARPETA_RESPALDOS); props.setProperty('CARPETA_RAIZ', raiz.getId()); }
  var it = raiz.getFoldersByName(unidad);
  return it.hasNext() ? it.next() : raiz.createFolder(unidad);
}

// ------------------------------------------------------------------ RESUMEN PARA LA AGENDA
/** Reescribe la hoja RESUMEN EJECUTIVO MRE (solo solicitudes, autorizaciones y gestiones con el MRE). */
// Responsable de otra unidad (asignado por DGE o Planificación): se guarda como «UNIDAD · Cargo».
function respClave_(t) {
  var r = String(t.responsable || ''), m = r.match(/^(.+?) · (.+)$/);
  if (m && UNIDADES.some(function (x) { return x.usuario === m[1]; })) return m[1] + '|' + m[2].toUpperCase();
  return t.unidad + '|' + r.toUpperCase();
}

function actualizarResumen_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(HOJA_RESUMEN) || ss.insertSheet(HOJA_RESUMEN);
  var cab = ['ID', 'UNIDAD', 'TIPO', 'TAREA / ASUNTO', 'INSTANCIA DEL MRE', '¿QUÉ HABILITA?', 'RESPONSABLE',
    'HOJA DE RUTA', 'FECHA SOLICITUD', 'FECHA LÍMITE', 'ESTADO', 'PRIORIDAD', 'DÍAS', 'ALERTA', 'RESULTADO', 'OBSERVACIONES', 'MEDIO DE VERIFICACIÓN', 'NIVEL DE RIESGO', 'LÍNEA DE SOLUCIÓN', 'ÁREA FUNCIONAL'];
  var tz = Session.getScriptTimeZone();
  var personas = {};
  leerResponsables_().forEach(function (r) { if (r.nombre) personas[r.unidad + '|' + r.cargo.toUpperCase()] = r.nombre; });
  var filas = leerTareasCrudas_().filter(function (t) { return t.tipo && t.tipo !== TIPO_INTERNA; })
    .map(function (t) {
      var p = personas[respClave_(t)];
      return [t.id, t.unidad, t.tipo, t.tarea, t.instancia, t.habilita, t.responsable + (p ? ' (' + p + ')' : ''), t.hojaRuta,
        t.fechaSol || '', t.fechaLim || '', t.estado, t.prioridad, '', '', t.resultado, t.obs, textoMedio_(t), t.nivelRiesgo, t.solucion, t.area];
    });
  sh.clear();
  encabezado_(sh, cab);
  sh.setFrozenRows(1);
  if (filas.length) {
    sh.getRange(2, 1, filas.length, cab.length).setValues(filas);
    var f = [];
    for (var i = 0; i < filas.length; i++) {
      var r = i + 2;
      f.push([
        '=IF(I' + r + '="","",MAX(0,TODAY()-I' + r + '))',
        '=IF(K' + r + '="Concluido","CONCLUIDO",IF(AND(J' + r + '<>"",J' + r + '<TODAY()),"VENCIDO",' +
          'IF(AND(L' + r + '="Alta",ISNUMBER(M' + r + '),M' + r + '>15),"CRÍTICO",' +
          'IF(AND(J' + r + '<>"",J' + r + '-TODAY()<=' + DIAS_POR_VENCER + '),"POR VENCER",' +
          'IF(M' + r + '="","SIN FECHA",IF(M' + r + '>7,"SEGUIMIENTO","EN CURSO"))))))'
      ]);
    }
    sh.getRange(2, 13, filas.length, 2).setFormulas(f);
    sh.getRange(2, 9, filas.length, 2).setNumberFormat('dd/mm/yyyy');
  }
  sh.getRange(1, 21).setValue('Hoja generada automáticamente por la app. No editar: los cambios se sobrescriben. Actualizado: ' +
    Utilities.formatDate(new Date(), tz, 'dd/MM/yyyy HH:mm'));
  return filas.length;
}

// ------------------------------------------------------------------ ADMINISTRACIÓN (PLANIFICACION)
function listarUsuarios(token) {
  var u = validar_(token);
  if (!esPlan_(u)) throw new Error('Sin permiso.');
  return todosUsuarios_().map(function (x) { return { usuario: x.usuario, activo: x.activo, debeCambiar: x.debeCambiar }; });
}

function restablecerClave(token, usuario, nueva) {
  var u = validar_(token);
  if (!esPlan_(u)) throw new Error('Sin permiso.');
  var obj = leerUsuario_(String(usuario).toUpperCase());
  if (!obj) throw new Error('Usuario no encontrado.');
  if (obj.usuario === USUARIO_DGE && u.usuario !== USUARIO_DGE) throw new Error('Solo la DGE puede cambiar la contraseña de la DGE.');
  validarClaveNueva_(nueva);
  guardarClave_(obj, nueva, obj.usuario !== u.usuario);
  if (obj.usuario !== u.usuario) cerrarSesiones_(obj.usuario);
  CacheService.getScriptCache().remove('int_' + obj.usuario);
  return listarUsuarios(token);
}

function cambiarEstadoUsuario(token, usuario, activo) {
  var u = validar_(token);
  if (!esPlan_(u)) throw new Error('Sin permiso.');
  var obj = leerUsuario_(String(usuario).toUpperCase());
  if (!obj) throw new Error('Usuario no encontrado.');
  if ((obj.usuario === USUARIO_PLAN || obj.usuario === USUARIO_DGE) && !activo) throw new Error('No se puede desactivar a ' + obj.usuario + '.');
  hojaUsuarios_().getRange(obj.fila, 5).setValue(!!activo);
  if (!activo) cerrarSesiones_(obj.usuario);
  return listarUsuarios(token);
}

// ------------------------------------------------------------------ SUBTAREAS
// En la hoja: una línea por paso «☐ 2026-11-05 · texto» (☑ = hecho; «sin fecha» si no tiene).
function subtareasDe_(texto) {
  return String(texto || '').split('\n').map(function (l) {
    var m = l.trim().match(/^([☐☑]) (\d{4}-\d{2}-\d{2}|sin fecha) · (.*)$/);
    return m ? { hecho: m[1] === '☑', fecha: m[2] === 'sin fecha' ? '' : m[2], texto: m[3] } : null;
  }).filter(Boolean);
}
function normSubtareas_(lista) {
  return (Array.isArray(lista) ? lista : []).map(function (x) {
    return { texto: String((x && x.texto) || '').replace(/\s+/g, ' ').trim().slice(0, 300),
             fecha: /^\d{4}-\d{2}-\d{2}$/.test((x && x.fecha) || '') ? x.fecha : '', hecho: !!(x && x.hecho) };
  }).filter(function (x) { return x.texto; }).slice(0, 40);
}
function textoSubtareas_(lista) {
  return lista.map(function (x) { return (x.hecho ? '☑' : '☐') + ' ' + (x.fecha || 'sin fecha') + ' · ' + x.texto; }).join('\n');
}

// ------------------------------------------------------------------ SINCRONIZACIÓN CON LA AGENDA DESPACHO
// Las tareas que también están en la Agenda Despacho (mismo título u hoja de ruta) comparten
// estado, hoja de ruta, fecha límite y subtareas (en la agenda: «recordatorios»). La app alimenta la agenda, no al revés.
function estadoAAgenda_(e) {
  if (e === 'Concluido') return 'Concluida';
  if (e === 'Pendiente') return 'Pendiente';
  if (e === 'Observado / Devuelto') return 'Bloqueada';
  return 'En gestión';
}
function sincronizarAgenda_(forzar) {
  var cache = CacheService.getScriptCache();
  if (!forzar && cache.get('sync_agenda')) return 0;
  cache.put('sync_agenda', '1', 120);
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(15000)) return 0;
  try {
    var ag;
    try { ag = SpreadsheetApp.openById(AGENDA_ID).getSheetByName('Datos'); } catch (e) { return 0; }
    if (!ag || ag.getLastRow() < 2) return 0;
    var agenda = [];
    ag.getRange(2, 1, ag.getLastRow() - 1, 2).getValues().forEach(function (r, i) {
      if (!r[1]) return;
      try { var d = JSON.parse(r[1]); d.id = d.id || String(r[0]); if (d.id) agenda.push({ fila: i + 2, d: d }); } catch (e) { /* fila dañada */ }
    });
    var norm = function (x) { return String(x || '').toLowerCase().replace(/^hr\s*/, '').replace(/\s+/g, ' ').trim(); };
    var tz = Session.getScriptTimeZone(), sh = hojaTareas_(), nAg = 0;
    leerTareasCrudas_().forEach(function (t, i) {
      var a = t.agendaId ? agenda.filter(function (x) { return x.d.id === t.agendaId; })[0] : null;
      if (!a) a = agenda.filter(function (x) {
        return norm(x.d.titulo) === norm(t.tarea) && (!t.hojaRuta || !x.d.hojaRuta || norm(x.d.hojaRuta) === norm(t.hojaRuta));
      })[0];
      if (!a) return;
      var fila = i + 2, d = a.d;
      if (t.agendaId !== d.id) sh.getRange(fila, colDe_('agendaId')).setValue(d.id);
      var subApp = subtareasDe_(t.subtareas);
      var subAg = normSubtareas_(d.recordatorios);
      var limApp = t.fechaLim instanceof Date ? Utilities.formatDate(t.fechaLim, tz, 'yyyy-MM-dd') : '';
      // Un solo sentido: la app alimenta la agenda; la agenda nunca cambia la app.
      // Si la tarea de la app todavía no tiene subtareas, se conservan los recordatorios que ya tenía la agenda.
      var subNuevo = subApp.length ? subApp : subAg;
      var e2 = estadoAAgenda_(t.estado);
      if (e2 !== d.estado || JSON.stringify(subNuevo) !== JSON.stringify(subAg) || t.hojaRuta !== (d.hojaRuta || '') || limApp !== (d.fechaLimite || '')) {
        d.estado = e2; d.recordatorios = subNuevo; d.hojaRuta = t.hojaRuta; d.fechaLimite = limApp;
        d.actualizado = new Date().toISOString();
        ag.getRange(a.fila, 1, 1, 2).setValues([[d.id, JSON.stringify(d)]]);
        nAg++;
      }
    });
    if (nAg) ag.getRange('C1').setValue(new Date().toISOString());
    return nAg;
  } finally {
    lock.releaseLock();
  }
}

// ------------------------------------------------------------------ LECTURA Y CÁLCULO
function leerTareasCrudas_() {
  var sh = hojaTareas_();
  if (sh.getLastRow() < 2) return [];
  return sh.getRange(2, 1, sh.getLastRow() - 1, COLS.length).getValues().map(function (r) {
    var o = {};
    COLS.forEach(function (c, i) { o[c[0]] = (r[i] instanceof Date) ? r[i] : String(r[i] === null ? '' : r[i]).trim(); });
    FECHAS.forEach(function (k) { if (!(o[k] instanceof Date)) o[k] = ''; });
    return o;
  }).filter(function (o) { return o.id; });
}

/** Tareas listas para la app: fechas en texto, días, alerta y señales. */
function leerTareas_() {
  var tz = Session.getScriptTimeZone(), hoy = soloDia_(new Date(), tz);
  var crudas = leerTareasCrudas_();
  var abiertas = {};
  crudas.forEach(function (t) { if (t.estado !== 'Concluido') abiertas[t.id] = t; });
  return crudas.map(function (t) {
    var o = {};
    COLS.forEach(function (c) { o[c[0]] = t[c[0]]; });
    FECHAS.forEach(function (k) { o[k] = t[k] instanceof Date ? Utilities.formatDate(t[k], tz, 'yyyy-MM-dd') : ''; });
    o.actualizadoTxt = t.actualizado instanceof Date ? Utilities.formatDate(t.actualizado, tz, 'dd/MM/yyyy HH:mm') : '';
    o.mre = !!t.tipo && t.tipo !== TIPO_INTERNA;
    o.concluida = t.estado === 'Concluido';
    o.dias = t.fechaSol instanceof Date ? Math.max(0, difDias_(soloDia_(t.fechaSol, tz), hoy)) : '';
    o.faltan = t.fechaLim instanceof Date ? difDias_(hoy, soloDia_(t.fechaLim, tz)) : '';
    o.alerta = alerta_(o);
    o.sinActualizar = !o.concluida && t.actualizado instanceof Date &&
      difDias_(soloDia_(t.actualizado, tz), hoy) > DIAS_SIN_ACTUALIZAR;
    o.diasSinActualizar = t.actualizado instanceof Date ? difDias_(soloDia_(t.actualizado, tz), hoy) : '';
    o.sinResponsable = !o.concluida && !t.responsable;
    o.bloquea = !o.concluida && !!t.habilitaA;
    o.adjuntos = adjuntosDe_(t.adjuntos).map(function (a) { return { id: a.id, nombre: a.nombre }; });
    o.sinRespaldo = o.concluida && !t.medio && !o.adjuntos.length;
    o.critica = !o.concluida && (o.alerta === 'VENCIDO' || o.alerta === 'CRÍTICO' || t.nivelRiesgo === 'Alto' ||
      (t.prioridad === 'Alta' && o.alerta === 'POR VENCER'));
    o.sinSolucion = o.critica && !t.solucion;
    o.subtareas = subtareasDe_(t.subtareas);
    var hoyTxt = Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd');
    o.subPend = o.subtareas.filter(function (x) { return !x.hecho; });
    o.subVencidas = o.concluida ? 0 : o.subPend.filter(function (x) { return x.fecha && x.fecha < hoyTxt; }).length;
    o.bloqueadaPor = crudas.filter(function (x) { return x.habilitaA === t.id && abiertas[x.id]; }).map(function (x) { return x.id; });
    return o;
  });
}

// misma lógica que la columna ALERTA de la hoja RESUMEN EJECUTIVO MRE
function alerta_(t) {
  if (t.concluida) return 'CONCLUIDO';
  if (t.faltan !== '' && t.faltan < 0) return 'VENCIDO';
  if (t.prioridad === 'Alta' && t.dias !== '' && t.dias > 15) return 'CRÍTICO';
  if (t.faltan !== '' && t.faltan <= DIAS_POR_VENCER) return 'POR VENCER';
  if (t.dias === '') return 'SIN FECHA';
  if (t.dias > 7) return 'SEGUIMIENTO';
  return 'EN CURSO';
}

function leerResponsables_() {
  var sh = hojaResp_();
  if (sh.getLastRow() < 2) return [];
  return sh.getRange(2, 1, sh.getLastRow() - 1, 4).getValues().map(function (r, i) {
    return { fila: i + 2, unidad: String(r[0]).trim().toUpperCase(), cargo: String(r[1]).trim(), nombre: String(r[2]).trim(),
      activo: r[3] === true || String(r[3]).toUpperCase() === 'TRUE' };
  }).filter(function (r) { return r.cargo; });
}

function catalogos_() {
  var out = JSON.parse(JSON.stringify(CAT_DEFECTO));
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(HOJA_CAT);
  if (sh && sh.getLastRow() > 1) {
    var v = sh.getRange(2, 1, sh.getLastRow() - 1, 5).getValues();
    ['TIPOS', 'INSTANCIAS', 'ESTADOS', 'PRIORIDADES', 'AREAS'].forEach(function (k, i) {
      var l = v.map(function (r) { return String(r[i]).trim(); }).filter(String);
      if (l.length) out[k] = l;
    });
  }
  if (out.TIPOS.indexOf(TIPO_INTERNA) < 0) out.TIPOS.unshift(TIPO_INTERNA);
  if (out.ESTADOS.indexOf('Concluido') < 0) out.ESTADOS.push('Concluido');
  return out;
}

// ------------------------------------------------------------------ AUXILIARES
function perfil_(u) {
  var plan = esPlan_(u);
  return {
    usuario: u.usuario, esPlan: plan, debeCambiar: u.debeCambiar,
    unidades: (plan ? UNIDADES : UNIDADES.filter(function (x) { return x.usuario === u.usuario; }))
      .map(function (x) { return { usuario: x.usuario, nombre: x.nombre }; }),
    etiqueta: u.usuario === USUARIO_DGE ? 'Dirección General Ejecutiva' : (plan ? 'Planificación' : ''), nivelesRiesgo: NIVELES_RIESGO,
    cat: catalogos_(), tipoInterna: TIPO_INTERNA, diasPorVencer: DIAS_POR_VENCER, diasSinActualizar: DIAS_SIN_ACTUALIZAR,
    urlProyectos: urlProyectos_(u)
  };
}

function validar_(token) {
  if (!token || !/^[A-Za-z0-9-]{20,100}$/.test(String(token))) throw new Error('SESION: Su sesión expiró. Ingrese nuevamente.');
  var v = CacheService.getScriptCache().get('ses_' + token);
  if (!v) throw new Error('SESION: Su sesión expiró. Ingrese nuevamente.');
  var p = v.split('|'), usuario = p[0], emitido = Number(p[1] || 0);
  var corte = Number(PropertiesService.getScriptProperties().getProperty('corte_' + usuario) || 0);
  if (emitido < corte) throw new Error('SESION: Su contraseña o acceso cambió. Ingrese nuevamente.');
  var u = leerUsuario_(usuario);
  if (!u || !u.activo) throw new Error('SESION: Usuario desactivado.');
  return u;
}

// ------------------------------------------------------------------ SEGURIDAD
/** Funciones de mantenimiento: solo la cuenta dueña, desde el editor de Apps Script. */
function soloDueno_() {
  var a = '';
  try { a = Session.getActiveUser().getEmail(); } catch (e) { a = ''; }
  if (!a || a !== Session.getEffectiveUser().getEmail()) throw new Error('Esta función solo se puede ejecutar desde el editor de Apps Script de la cuenta dueña.');
}
/** Cierra todas las sesiones abiertas de un usuario (al cambiar su contraseña o quitarle el acceso). */
function cerrarSesiones_(usuario) {
  PropertiesService.getScriptProperties().setProperty('corte_' + usuario, String(Date.now()));
}
/** Números aleatorios seguros (a partir de identificadores únicos del sistema). */
function azar_(max) {
  var h = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, Utilities.getUuid() + Utilities.getUuid());
  var n = 0;
  for (var i = 0; i < 6; i++) n = n * 256 + (h[i] & 255);
  return n % max;
}
/** Guarda una copia de la tarea eliminada en la hoja PAPELERA (oculta) para poder recuperarla. */
function aPapelera_(t, usuario) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName('PAPELERA');
  if (!sh) {
    sh = ss.insertSheet('PAPELERA');
    encabezado_(sh, ['ELIMINADA EL', 'ELIMINADA POR'].concat(COLS.map(function (c) { return c[1]; })));
    sh.hideSheet();
  }
  var fila = [new Date(), usuario].concat(COLS.map(function (c) { return t[c[0]] === undefined ? '' : t[c[0]]; }));
  sh.getRange(sh.getLastRow() + 1, 1, 1, fila.length).setValues([fila]);
}

function esPlan_(u) { return String(u.hoja).trim().toUpperCase() === 'TODAS'; }

function unidadPermitida_(u, usuarioUnidad) {
  var pedida = String(usuarioUnidad || '').toUpperCase();
  var unidad = UNIDADES.filter(function (x) { return x.usuario === pedida; })[0];
  if (!unidad) throw new Error('Unidad no válida.');
  if (!esPlan_(u) && unidad.usuario !== u.usuario) throw new Error('No tiene acceso a esa unidad.');
  return unidad;
}

function siguienteId_(todas, unidad) {
  var max = 0;
  todas.forEach(function (t) {
    if (t.unidad === unidad) { var n = Number(String(t.id).split('-').pop()); if (n > max) max = n; }
  });
  return unidad + '-' + ('00' + (max + 1)).slice(-3);
}

function hojaTareas_() {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(HOJA_TAREAS);
  if (!sh) throw new Error('Falta la hoja TAREAS. Ejecute la función instalar.');
  return sh;
}
function hojaResp_() {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(HOJA_RESP);
  if (!sh) throw new Error('Falta la hoja RESPONSABLES. Ejecute la función instalar.');
  return sh;
}
function hojaUsuarios_() {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(HOJA_USUARIOS);
  if (!sh) throw new Error('Falta la hoja USUARIOS. Ejecute la función instalar.');
  return sh;
}
function colDe_(k) { for (var i = 0; i < COLS.length; i++) if (COLS[i][0] === k) return i + 1; return 0; }

function buscarHoja_(nombre) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(nombre);
  if (sh) return sh;
  var obj = String(nombre).trim().toUpperCase();
  return ss.getSheets().filter(function (s) { return s.getName().trim().toUpperCase() === obj; })[0] || null;
}

function encabezado_(sh, titulos) {
  if (sh.getMaxColumns() < titulos.length) sh.insertColumnsAfter(sh.getMaxColumns(), titulos.length - sh.getMaxColumns());
  sh.getRange(1, 1, 1, titulos.length).setValues([titulos])
    .setFontWeight('bold').setBackground('#1F3864').setFontColor('#FFFFFF');
}

function formatoFechas_(sh) {
  if (sh.getLastRow() < 2) return;
  ['fechaSol', 'fechaLim', 'fechaFin'].forEach(function (k) {
    sh.getRange(2, colDe_(k), sh.getLastRow() - 1, 1).setNumberFormat('dd/mm/yyyy');
  });
  sh.getRange(2, colDe_('actualizado'), sh.getLastRow() - 1, 1).setNumberFormat('dd/mm/yyyy hh:mm');
}

function todosUsuarios_() {
  var sh = hojaUsuarios_();
  if (sh.getLastRow() < 2) return [];
  return sh.getRange(2, 1, sh.getLastRow() - 1, 6).getValues().map(function (r, i) {
    return {
      fila: i + 2, usuario: String(r[0]).trim().toUpperCase(), hoja: String(r[1]),
      hash: String(r[2]), sal: String(r[3]), activo: r[4] === true || String(r[4]).toUpperCase() === 'TRUE',
      debeCambiar: r[5] === true || String(r[5]).toUpperCase() === 'TRUE'
    };
  }).filter(function (x) { return x.usuario; });
}
function leerUsuario_(usuario) { return todosUsuarios_().filter(function (x) { return x.usuario === usuario; })[0] || null; }

function guardarClave_(u, nueva, debeCambiar) {
  var sal = Utilities.getUuid();
  hojaUsuarios_().getRange(u.fila, 3, 1, 4).setValues([[hash_(nueva, sal), sal, u.activo, !!debeCambiar]]);
}
function validarClaveNueva_(c) {
  c = String(c || '');
  if (c.length < 8 || !/[A-Za-z]/.test(c) || !/[0-9]/.test(c)) throw new Error('La contraseña debe tener al menos 8 caracteres, con letras y números.');
}
function hash_(clave, sal) {
  var bytes = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, sal + '|' + clave, Utilities.Charset.UTF_8);
  for (var i = 0; i < 300; i++) {
    bytes = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, bytes.concat(Utilities.newBlob(sal).getBytes()));
  }
  return Utilities.base64Encode(bytes);
}
function claveAleatoria_() {
  var l = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz', n = '23456789', s = '';
  for (var i = 0; i < 6; i++) s += l.charAt(azar_(l.length));
  for (var j = 0; j < 3; j++) s += n.charAt(azar_(n.length));
  return s;
}
function limpiar_(v) {
  var s = String(v === undefined || v === null ? '' : v).trim().slice(0, 2000);
  return /^[=+\-@]/.test(s) ? "'" + s : s;
}
function aFecha_(iso) {
  var p = String(iso || '').split('-');
  return p.length === 3 ? new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2])) : '';
}
function hoyIso_() { return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd'); }
function soloDia_(d, tz) { var p = Utilities.formatDate(d, tz, 'yyyy-MM-dd').split('-'); return Date.UTC(+p[0], +p[1] - 1, +p[2]); }
function difDias_(a, b) { return Math.round((b - a) / 86400000); }
