document.addEventListener('DOMContentLoaded', function () {
  // Mobile: close offcanvas when a nav link is clicked.
  var offcanvasEl = document.getElementById('sidebarOffcanvas');
  if (offcanvasEl) {
    offcanvasEl.querySelectorAll('.sidebar-link').forEach(function (a) {
      a.addEventListener('click', function () {
        var instance = bootstrap.Offcanvas.getInstance(offcanvasEl);
        if (instance) instance.hide();
      });
    });
  }

  // Desktop: toggle sidebar collapse.
  var toggleBtn = document.querySelector('[data-action="toggle-sidebar"]');
  if (!toggleBtn) return;

  var shell = document.querySelector('.app-shell');
  var iconOff = toggleBtn.querySelector('.icon-drawer-off');
  var iconOn  = toggleBtn.querySelector('.icon-drawer-on');

  function setCollapsed(collapsed) {
    shell.classList.toggle('sidebar-colapsado', collapsed);
    if (iconOff) iconOff.classList.toggle('d-none',  collapsed);
    if (iconOn)  iconOn.classList.toggle('d-none',  !collapsed);
    toggleBtn.setAttribute('aria-label', collapsed ? 'Mostrar menú' : 'Ocultar menú');
    try { localStorage.setItem('sidebar-collapsed', collapsed ? '1' : '0'); } catch (_) {}
  }

  var stored = false;
  try { stored = localStorage.getItem('sidebar-collapsed') === '1'; } catch (_) {}
  setCollapsed(stored);

  toggleBtn.addEventListener('click', function () {
    setCollapsed(!shell.classList.contains('sidebar-colapsado'));
  });
});
