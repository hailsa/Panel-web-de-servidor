(() => {
const $ = id => document.getElementById(id);
const size = value => {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let index = 0;
  let number = Number(value) || 0;
  while (number >= 1024 && index < units.length - 1) { number /= 1024; index += 1; }
  return `${number.toFixed(index > 1 ? 1 : 0)} ${units[index]}`;
};
const duration = value => {
  const seconds = Math.max(0, Number(value) || 0);
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor(seconds % 86400 / 3600);
  const minutes = Math.floor(seconds % 3600 / 60);
  return `${days}d ${hours}h ${minutes}m`;
};
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const row = (label, value, status = '') => `<div class="row"><span>${esc(label)}</span><span class="${status}">${esc(value)}</span></div>`;
const setConnection = (online, hostname = null, uptime = null) => {
  $('server-state').textContent = online ? 'Servidor en línea' : 'Sin datos';
  document.querySelector('.online').classList.toggle('offline', !online);
  if (hostname) $('side-host').textContent = hostname;
  if (uptime !== null) $('uptime').textContent = duration(uptime);
};
const showError = visible => {
  const box = $('error');
  if (!box) return;
  box.textContent = 'No se pudieron obtener datos del collector.';
  box.classList.toggle('hidden', !visible);
};

window.SHC = {$, size, duration, esc, row, setConnection, showError};

const sidebar = document.querySelector('.sidebar');
const menu = $('menu');
const backdrop = $('sidebar-backdrop');
const isMobile = () => window.matchMedia('(max-width: 720px)').matches;
const closeSidebar = () => {
  sidebar.classList.remove('open');
  document.body.classList.remove('sidebar-open');
  menu.setAttribute('aria-expanded', 'false');
};
const toggleSidebar = () => {
  if (isMobile()) {
    const opening = !sidebar.classList.contains('open');
    sidebar.classList.toggle('open', opening);
    document.body.classList.toggle('sidebar-open', opening);
    menu.setAttribute('aria-expanded', String(opening));
  } else {
    document.body.classList.toggle('sidebar-collapsed');
    menu.setAttribute('aria-expanded', String(!document.body.classList.contains('sidebar-collapsed')));
  }
};

const savedTheme = localStorage.getItem('shc-theme');
if (savedTheme) document.documentElement.dataset.theme = savedTheme;
$('theme').onclick = () => {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem('shc-theme', next);
};
menu.onclick = toggleSidebar;
$('sidebar-close').onclick = closeSidebar;
backdrop.onclick = closeSidebar;
document.querySelectorAll('.sidebar nav a').forEach(link => link.addEventListener('click', closeSidebar));
document.addEventListener('keydown', event => { if (event.key === 'Escape') closeSidebar(); });
window.addEventListener('resize', () => { if (!isMobile()) closeSidebar(); });

const powerButton = $('power');
const powerMenu = $('power-menu');
const powerDialog = $('power-dialog');
let pendingPowerAction = null;
powerButton.onclick = event => {
  event.stopPropagation();
  const opening = powerMenu.classList.contains('hidden');
  powerMenu.classList.toggle('hidden', !opening);
  powerButton.setAttribute('aria-expanded', String(opening));
};
document.querySelectorAll('[data-power]').forEach(button => button.addEventListener('click', () => {
  pendingPowerAction = button.dataset.power;
  const reboot = pendingPowerAction === 'reboot';
  $('power-dialog-title').textContent = reboot ? '¿Reiniciar el servidor?' : '¿Apagar el servidor?';
  $('power-dialog-copy').textContent = reboot
    ? 'Las conexiones y servicios se interrumpirán durante el reinicio.'
    : 'El servidor quedará fuera de línea y deberá encenderse físicamente.';
  powerMenu.classList.add('hidden');
  powerDialog.showModal();
}));
powerDialog.addEventListener('close', async () => {
  if (powerDialog.returnValue !== 'confirm' || !pendingPowerAction) return;
  const action = pendingPowerAction;
  pendingPowerAction = null;
  $('power-confirm').disabled = true;
  try {
    const response = await fetch('/api/system/power', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-SHC-Action': 'confirm'},
      body: JSON.stringify({action}),
    });
    if (!response.ok) throw new Error('Acción rechazada');
    setConnection(false);
    $('server-state').textContent = action === 'reboot' ? 'Reiniciando…' : 'Apagando…';
  } catch (_) {
    window.alert('No se pudo ejecutar la acción. Revisá el estado del collector.');
  } finally {
    $('power-confirm').disabled = false;
  }
});

const NOTIFICATION_KEY = 'shc-notifications-v1';
const STATE_KEY = 'shc-monitor-state-v1';
let notifications = JSON.parse(localStorage.getItem(NOTIFICATION_KEY) || '[]');
let priorState = JSON.parse(localStorage.getItem(STATE_KEY) || '{}');
const notificationId = (kind, target) => `${kind}:${target}`;
const addNotification = (kind, severity, title, message) => {
  const id = notificationId(kind, title);
  const existing = notifications.find(item => item.id === id && !item.resolved);
  if (existing) { existing.message = message; existing.updatedAt = Date.now(); return; }
  notifications.unshift({id, severity, title, message, createdAt: Date.now(), updatedAt: Date.now(), resolved: false});
  notifications = notifications.slice(0, 50);
};
const resolveMissing = activeIds => notifications.forEach(item => {
  if (!activeIds.has(item.id) && !item.resolved) { item.resolved = true; item.updatedAt = Date.now(); }
});
const renderNotifications = () => {
  const active = notifications.filter(item => !item.resolved);
  $('notification-badge').textContent = active.length;
  $('notification-badge').classList.toggle('hidden', active.length === 0);
  $('notification-summary').textContent = active.length ? `${active.length} activa${active.length === 1 ? '' : 's'}` : 'Todo funciona normalmente';
  $('notification-list').innerHTML = notifications.length ? notifications.map(item => `
    <article class="notification-item ${item.severity} ${item.resolved ? 'resolved' : ''}">
      <i></i><div><strong>${esc(item.title)}</strong><p>${esc(item.message)}</p><time>${new Intl.DateTimeFormat('es-AR', {dateStyle:'short', timeStyle:'short'}).format(item.createdAt)}</time></div>
    </article>`).join('') : '<p class="notification-empty">No hay incidencias activas.</p>';
  localStorage.setItem(NOTIFICATION_KEY, JSON.stringify(notifications));
};
const evaluateAlerts = data => {
  const active = new Set();
  const alert = (kind, severity, title, message) => { active.add(notificationId(kind, title)); addNotification(kind, severity, title, message); };
  const cpu = Number(data.cpu?.percent || 0);
  const ram = Number(data.memory?.percent || 0);
  if (cpu >= 99) alert('cpu', 'critical', 'Procesador al 100%', `Uso actual: ${cpu.toFixed(1)}%.`);
  if (ram >= 99) alert('ram', 'critical', 'Memoria RAM al 100%', `Uso actual: ${ram.toFixed(1)}%.`);
  (data.filesystems || []).forEach(disk => {
    const percent = Number(disk.percent || 0);
    if (percent >= 90) alert('disk', percent >= 95 ? 'critical' : 'warning', `Unidad ${disk.mountpoint} casi llena`, `Ocupación: ${percent.toFixed(1)}%. Revisá o reemplazá la unidad si su estado se degrada.`);
  });
  (data.temperatures || []).forEach(sensor => {
    const current = Number(sensor.current_c);
    const critical = Number(sensor.critical_c || 0);
    const high = Number(sensor.high_c || 0);
    const limit = critical > 0 ? critical : high > 0 ? high : 85;
    if (current >= limit) alert('temperature', 'critical', `Temperatura crítica: ${sensor.label}`, `${current.toFixed(1)} °C (límite ${limit.toFixed(1)} °C).`);
    else if (current >= Math.min(limit - 5, 80)) alert('temperature', 'warning', `Temperatura elevada: ${sensor.label}`, `${current.toFixed(1)} °C.`);
  });
  (data.docker?.containers || []).forEach(container => {
    if (container.state !== 'running') alert('docker', 'critical', `Docker detenido: ${container.name}`, container.status || 'El contenedor dejó de ejecutarse.');
  });
  (data.virtual_machines?.machines || []).forEach(machine => {
    if (!['running', 'encendida', 'active'].includes(String(machine.state).toLowerCase())) alert('vm', 'critical', `Máquina virtual detenida: ${machine.name}`, `Estado: ${machine.state || 'desconocido'}.`);
  });
  if (data.network?.internet_available === false) alert('internet', 'critical', 'Sin conexión a Internet', 'El servidor no pudo establecer conectividad externa.');
  if (data.smart?.available && data.smart?.healthy === false) alert('smart', 'critical', 'Riesgo en unidad física', data.smart.reason || 'SMART informa un estado no saludable.');
  resolveMissing(active);
  priorState = {collectedAt: data.collected_at, docker: data.docker, virtualMachines: data.virtual_machines};
  localStorage.setItem(STATE_KEY, JSON.stringify(priorState));
  renderNotifications();
};
async function refreshNotifications() {
  try {
    const response = await fetch('/api/snapshot', {cache: 'no-store'});
    if (!response.ok) throw new Error('Sin datos');
    evaluateAlerts(await response.json());
  } catch (_) {
    addNotification('collector', 'critical', 'Collector sin respuesta', 'El dashboard no puede obtener métricas del servidor.');
    renderNotifications();
  }
}
const notificationButton = $('notifications');
const notificationPanel = $('notification-panel');
notificationButton.onclick = event => {
  event.stopPropagation();
  const opening = notificationPanel.classList.contains('hidden');
  notificationPanel.classList.toggle('hidden', !opening);
  notificationButton.setAttribute('aria-expanded', String(opening));
};
$('clear-notifications').onclick = () => { notifications = []; renderNotifications(); };
document.addEventListener('click', event => {
  if (!notificationPanel.contains(event.target) && event.target !== notificationButton) notificationPanel.classList.add('hidden');
  if (!powerMenu.contains(event.target) && event.target !== powerButton) powerMenu.classList.add('hidden');
});
renderNotifications();
refreshNotifications();
setInterval(refreshNotifications, 30000);
function updateClock() {
  $('clock').textContent = new Intl.DateTimeFormat('es-AR', {dateStyle: 'short', timeStyle: 'medium'}).format(new Date());
}
updateClock();
setInterval(updateClock, 1000);
})();
