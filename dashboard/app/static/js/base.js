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

const savedTheme = localStorage.getItem('shc-theme');
if (savedTheme) document.documentElement.dataset.theme = savedTheme;
$('theme').onclick = () => {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem('shc-theme', next);
};
$('menu').onclick = () => document.querySelector('.sidebar').classList.toggle('open');
document.querySelectorAll('.sidebar nav a').forEach(link => link.addEventListener('click', () => document.querySelector('.sidebar').classList.remove('open')));
function updateClock() {
  $('clock').textContent = new Intl.DateTimeFormat('es-AR', {dateStyle: 'short', timeStyle: 'medium'}).format(new Date());
}
updateClock();
setInterval(updateClock, 1000);
})();
