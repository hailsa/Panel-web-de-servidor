const {$, esc, setConnection, showError} = window.SHC;
let users = [];
let filter = 'all';

const isPerson = user => user.role !== 'Sistema';
function badge(value, kind = '') { return `<span class="badge ${kind}">${esc(value)}</span>`; }
function renderUsers() {
  const query = $('user-search').value.trim().toLocaleLowerCase('es');
  const visible = users.filter(user => {
    if (filter === 'people' && !isPerson(user)) return false;
    if (filter === 'system' && isPerson(user)) return false;
    const haystack = [user.username, user.primary_group, user.role, user.shell, user.home, ...user.groups].join(' ').toLocaleLowerCase('es');
    return haystack.includes(query);
  });
  $('users-body').innerHTML = visible.map(user => `<tr>
    <td><strong class="username">${esc(user.username)}</strong></td>
    <td>${user.uid}</td><td>${esc(user.primary_group)}</td>
    <td class="groups">${user.groups.map(group => badge(group)).join(' ')}</td>
    <td>${badge(user.role, user.role === 'Sistema' ? 'neutral' : 'role')}</td>
    <td><code>${esc(user.shell)}</code></td><td><code>${esc(user.home)}</code></td>
    <td>${esc(user.last_access)}</td>
    <td>${badge(user.state, user.state === 'En línea' ? 'online-badge' : user.state === 'Sin login' ? 'disabled-badge' : 'active-badge')}</td>
  </tr>`).join('') || '<tr><td colspan="9" class="empty">No hay usuarios que coincidan con el filtro.</td></tr>';
  const people = users.filter(isPerson).length;
  $('count-all').textContent = users.length;
  $('count-people').textContent = people;
  $('count-system').textContent = users.length - people;
  $('users-summary').textContent = `${visible.length} de ${users.length} usuarios`;
}
async function refreshUsers() {
  try {
    const response = await fetch('/api/users', {cache: 'no-store'});
    if (!response.ok) throw new Error('Collector no disponible');
    const payload = await response.json();
    users = payload.users || [];
    renderUsers();
    setConnection(true, payload.system?.hostname, payload.system?.uptime_seconds);
    showError(false);
  } catch (_) { setConnection(false); showError(true); }
}
$('user-search').addEventListener('input', renderUsers);
document.querySelectorAll('.filter').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.filter').forEach(item => item.classList.remove('active'));
  button.classList.add('active');
  filter = button.dataset.filter;
  renderUsers();
}));
refreshUsers();
setInterval(refreshUsers, 30000);
