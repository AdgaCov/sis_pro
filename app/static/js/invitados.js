// Si se marca «Todas las unidades», la lista individual se desactiva.
(function () {
  var todas = document.getElementById("todas");
  var lista = document.getElementById("listaUnidades");
  if (!todas || !lista) return;
  function actualizar() { lista.disabled = todas.checked; }
  todas.addEventListener("change", actualizar);
  actualizar();
})();
