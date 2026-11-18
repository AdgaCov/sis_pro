// Botones con data-imprimir abren el diálogo de impresión (se puede guardar como PDF).
document.addEventListener("click", function (ev) {
  if (ev.target.closest && ev.target.closest("[data-imprimir]")) window.print();
});
