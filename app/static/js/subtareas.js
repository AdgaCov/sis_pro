// Agrega y quita filas de subtareas en el formulario de tarea.
(function () {
  var lista = document.getElementById("listaPasos");
  var plantilla = document.getElementById("plantillaPaso");
  var boton = document.getElementById("agregarPaso");
  if (!lista || !plantilla || !boton) return;

  var siguiente = parseInt(lista.dataset.siguiente, 10) || 0;
  var maximo = parseInt(lista.dataset.maximo, 10) || 40;

  function actualizar() {
    boton.disabled = lista.querySelectorAll(".paso").length >= maximo;
  }

  boton.addEventListener("click", function () {
    if (lista.querySelectorAll(".paso").length >= maximo) return;
    var html = plantilla.innerHTML.replace(/__i__/g, String(siguiente++));
    lista.insertAdjacentHTML("beforeend", html);
    var filas = lista.querySelectorAll(".paso");
    var texto = filas[filas.length - 1].querySelector("input[type=text]");
    if (texto) texto.focus();
    actualizar();
  });

  lista.addEventListener("click", function (ev) {
    if (ev.target.classList.contains("quitar-paso")) {
      ev.target.closest(".paso").remove();
      actualizar();
    }
  });

  actualizar();
})();
