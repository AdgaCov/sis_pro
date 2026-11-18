// Dibuja los gráficos del tablero con Chart.js. Los datos vienen del servidor (ya filtrados por permisos).
(function () {
  var fuente = document.getElementById("datosGraficos");
  if (!fuente || typeof Chart === "undefined") return;
  var d = JSON.parse(fuente.textContent);
  var cfg = document.getElementById("configGraficos").dataset;
  var AZUL = "#1F3864", AZUL2 = "#2E4A7D", VERDE = "#3B9A63", ROJO = "#B42318", GRIS = "#DDE2EC";

  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = "#5B6478";
  Chart.defaults.plugins.legend.labels.boxWidth = 12;

  // Navega a la lista de tareas con filtros (solo si el usuario puede ver tareas)
  function irATareas(filtros) {
    if (!cfg.tareas) return;
    var p = new URLSearchParams(filtros);
    if (cfg.unidad && !p.has("unidad_id")) p.set("unidad_id", cfg.unidad);
    window.location.href = cfg.tareas + "?" + p.toString();
  }
  function cursor(ev, elementos) {
    ev.native.target.style.cursor = cfg.tareas && elementos.length ? "pointer" : "default";
  }

  // Pendientes por unidad, apiladas por alerta
  var gU = document.getElementById("gUnidades");
  if (gU) {
    new Chart(gU, {
      type: "bar",
      data: {
        labels: d.barras.etiquetas,
        datasets: d.barras.series.map(function (s) {
          return { label: s.alerta, data: s.valores, backgroundColor: s.color, borderWidth: 0 };
        })
      },
      options: {
        maintainAspectRatio: false,
        scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } } },
        onHover: cursor,
        onClick: function (ev, el) {
          if (!el.length) return;
          var s = d.barras.series[el[0].datasetIndex];
          irATareas({ unidad_id: d.barras.unidades[el[0].index], alerta: s.alerta });
        }
      }
    });
  }

  // Velocímetro de cumplimiento (media dona) con la meta
  var gC = document.getElementById("gCumplimiento");
  if (gC && d.cumplimiento.pct !== null) {
    var pct = d.cumplimiento.pct, meta = d.cumplimiento.meta;
    new Chart(gC, {
      type: "doughnut",
      data: { datasets: [{ data: [pct, 100 - pct], backgroundColor: [pct >= meta ? VERDE : ROJO, GRIS], borderWidth: 0 }] },
      options: {
        maintainAspectRatio: false, rotation: -90, circumference: 180, cutout: "72%",
        plugins: { legend: { display: false }, tooltip: { enabled: false } }
      },
      plugins: [{
        id: "meta",
        afterDraw: function (chart) {
          var a = chart.getDatasetMeta(0).data[0];
          if (!a) return;
          var ang = Math.PI + Math.PI * meta / 100, c = chart.ctx;
          c.save();
          c.strokeStyle = AZUL; c.lineWidth = 3;
          c.beginPath();
          c.moveTo(a.x + Math.cos(ang) * (a.innerRadius - 6), a.y + Math.sin(ang) * (a.innerRadius - 6));
          c.lineTo(a.x + Math.cos(ang) * (a.outerRadius + 6), a.y + Math.sin(ang) * (a.outerRadius + 6));
          c.stroke();
          c.restore();
        }
      }]
    });
  }

  // Creadas contra concluidas
  var gM = document.getElementById("gMensual");
  if (gM) {
    new Chart(gM, {
      type: "line",
      data: {
        labels: d.mensual.etiquetas,
        datasets: [
          { label: "Creadas", data: d.mensual.creadas, borderColor: AZUL2, backgroundColor: AZUL2, tension: 0.25 },
          { label: "Concluidas", data: d.mensual.concluidas, borderColor: VERDE, backgroundColor: VERDE, tension: 0.25 }
        ]
      },
      options: {
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { grid: { display: false } } }
      }
    });
  }

  // Embudo de estados (barras horizontales)
  var gE = document.getElementById("gEmbudo");
  if (gE) {
    new Chart(gE, {
      type: "bar",
      data: {
        labels: d.embudo.map(function (x) { return x.estado; }),
        datasets: [{ label: "Tareas abiertas", data: d.embudo.map(function (x) { return x.valor; }), backgroundColor: AZUL2 }]
      },
      options: {
        indexAxis: "y", maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { beginAtZero: true, ticks: { precision: 0 } }, y: { grid: { display: false } } },
        onHover: cursor,
        onClick: function (ev, el) { if (el.length) irATareas({ estado_id: d.embudo[el[0].index].id }); }
      }
    });
  }

  // Anillos de cumplimiento por unidad
  d.anillos.forEach(function (a, i) {
    var lienzo = document.getElementById("gAnillo" + i);
    if (!lienzo || a.pct === null) return;
    new Chart(lienzo, {
      type: "doughnut",
      data: { datasets: [{ data: [a.pct, 100 - a.pct], backgroundColor: [a.pct >= d.cumplimiento.meta ? VERDE : ROJO, GRIS], borderWidth: 0 }] },
      options: {
        responsive: false, cutout: "70%",
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        onHover: cursor,
        onClick: function () { irATareas({ unidad_id: a.unidad_id, ver_concluidas: "y" }); }
      }
    });
  });
})();
