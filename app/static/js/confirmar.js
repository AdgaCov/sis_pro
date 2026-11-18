// Pide confirmación antes de enviar formularios con data-confirmar="mensaje".
document.addEventListener("submit", function (ev) {
  var f = ev.target;
  var msg = f.getAttribute && f.getAttribute("data-confirmar");
  if (msg && !window.confirm(msg)) ev.preventDefault();
});
