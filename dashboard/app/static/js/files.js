(() => {
  const {$, size} = window.SHC;
  const dialog = $('files-dialog');
  let folder = '';
  let pending;
  let busy = false;
  const join = name => folder ? folder + '/' + name : name;
  const button = (label, click) => {
    const item = document.createElement('button');
    item.type = 'button';
    item.textContent = label;
    item.addEventListener('click', click);
    return item;
  };
  async function call(payload) {
    const response = await fetch('/api/files', {
      method: 'POST', cache: 'no-store',
      headers: {'Content-Type': 'application/json', 'X-SHC-Action': 'confirm'},
      body: JSON.stringify(payload)
    });
    if (response.status === 401) location.replace('/login');
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'No se pudo completar la operación');
    return data;
  }
  async function list(path) {
    const data = await call({action: 'list', path});
    folder = path;
    $('files-path').textContent = '/' + folder;
    $('files-up').disabled = !folder;
    $('files-status').textContent = data.truncated ? 'Se muestran las primeras 2000 entradas.' : data.entries.length + ' entradas';
    const rows = data.entries.sort((a, b) => (b.kind === 'directory') - (a.kind === 'directory') || a.name.localeCompare(b.name));
    $('files-body').replaceChildren(...rows.map(entry => {
      const tr = document.createElement('tr');
      const path = join(entry.name);
      const name = tr.insertCell();
      if (entry.kind === 'directory') name.append(button('Abrir ' + entry.name, () => navigate(path)));
      else name.textContent = entry.name;
      tr.insertCell().textContent = {directory: 'Carpeta', file: 'Archivo', other: 'Enlace o especial'}[entry.kind];
      tr.insertCell().textContent = entry.kind === 'file' ? size(entry.size) : '—';
      tr.insertCell().textContent = new Date(entry.mtime * 1000).toLocaleString('es-AR');
      const actions = tr.insertCell();
      if (entry.kind !== 'other') actions.append(
        button('Mover / renombrar', () => promptAction('move', path)),
        button('Eliminar', () => promptAction('delete', path))
      );
      return tr;
    }));
  }
  async function navigate(path) {
    if (busy) return;
    busy = true;
    try { await list(path); }
    catch (error) { $('files-status').textContent = error.message; }
    finally { busy = false; }
  }
  function promptAction(action, path = '') {
    if (busy) return;
    pending = {action, path};
    $('files-title').textContent = {move: 'Mover o renombrar', delete: 'Eliminar', mkdir: 'Nueva carpeta', create: 'Nuevo archivo vacío'}[action];
    $('files-target').value = action === 'move' ? path : folder ? folder + '/' : '';
    $('files-field').hidden = action === 'delete';
    $('files-target').required = action !== 'delete';
    $('files-description').textContent = action === 'delete' ? 'Se eliminará /' + path + '. Las carpetas deben estar vacías.' : '';
    dialog.showModal();
  }
  $('files-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    busy = true;
    $('files-confirm').disabled = true;
    $('files-cancel').disabled = true;
    const target = $('files-target').value;
    const {action, path} = pending;
    try {
      await call({action, path: ['mkdir', 'create'].includes(action) ? target : path, destination: target});
      dialog.close();
      await list(folder);
    } catch (error) {
      $(dialog.open ? 'files-description' : 'files-status').textContent = error.message;
    } finally {
      busy = false;
      $('files-confirm').disabled = false;
      $('files-cancel').disabled = false;
    }
  });
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  $('files-cancel').onclick = () => dialog.close();
  $('files-up').onclick = () => navigate(folder.split('/').slice(0, -1).join('/'));
  $('files-refresh').onclick = () => navigate(folder);
  $('files-mkdir').onclick = () => promptAction('mkdir');
  $('files-create').onclick = () => promptAction('create');
  navigate('');
})();
