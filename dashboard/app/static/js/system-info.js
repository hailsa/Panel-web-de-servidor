/* Compact host summary. Values come from the authenticated host snapshot. */
function renderSystemInfo(data, localNetwork, privateNetwork) {
  const {esc, size, duration} = window.SHC;
  const system = data.system;
  const unavailable = 'No disponible';
  const line = (label, value) => `<dt>${esc(label)}</dt><dd>${esc(value ?? unavailable)}</dd>`;
  const section = (title, rows) => `<section class="system-info-group"><h3>${esc(title)}</h3><dl>${rows}</dl></section>`;
  let booted = unavailable;
  if (system.booted_at && Number.isFinite(Date.parse(system.booted_at))) {
    const options = {dateStyle: 'short', timeStyle: 'short'};
    if (system.timezone) options.timeZone = system.timezone;
    try { booted = new Intl.DateTimeFormat('es-AR', options).format(new Date(system.booted_at)); }
    catch (_) { booted = new Intl.DateTimeFormat('es-AR', {dateStyle: 'short', timeStyle: 'short'}).format(new Date(system.booted_at)); }
  }
  const board = [system.board_vendor, system.board_name].filter(value => value && value !== unavailable).join(' · ');
  const cores = `${system.cpu_physical_cores ?? '—'} núcleos / ${system.cpu_count ?? '—'} hilos · ${system.architecture || unavailable}`;
  document.getElementById('system-info').innerHTML = section('Sistema',
    line('Hostname', system.hostname) + line('Sistema operativo', system.os) + line('Kernel', system.kernel) +
    line('Tiempo encendido', duration(system.uptime_seconds)) + line('Último arranque', booted) + line('Zona horaria', system.timezone)
  ) + section('Hardware',
    line('Procesador', system.cpu_model) + line('CPU / arquitectura', cores) +
    line('RAM total / disponible', `${size(data.memory.total)} / ${size(data.memory.available)}`) +
    line('Swap usada / total', data.memory.swap_total ? `${size(data.memory.swap_used)} / ${size(data.memory.swap_total)}` : 'Sin swap configurada') +
    line('Placa base', board || unavailable) + line('Arranque / firmware', [system.boot_mode, system.bios_version].filter(Boolean).join(' · ') || unavailable)
  ) + section('Red',
    line('IP local', localNetwork?.address) + line('Interfaz local', localNetwork?.interface) +
    (privateNetwork ? line('Red privada', `${privateNetwork.address} · ${privateNetwork.interface}`) : '')
  );
}
