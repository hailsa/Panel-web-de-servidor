const {$, size, esc, row, setConnection, showError} = window.SHC;
const valueOr = value => value === null || value === undefined || value === '' ? 'No disponible' : value;
const temperature = value => value === null || value === undefined ? 'No disponible' : `${Number(value).toFixed(1)} °C`;
function statusClass(state) { return ['active', 'running', 'up'].includes(String(state).toLowerCase()) ? 'status' : 'muted'; }

function renderStatus(data) {
  const snapshot = data;
  const systemTemp = snapshot.temperatures.find(item => /acpi|system|motherboard|temp1/i.test(`${item.source} ${item.label}`));
  const voltage = data.voltages[0];
  $('status-cpu-temp').textContent = temperature(snapshot.cpu.temperature_c);
  $('status-cpu-health').textContent = snapshot.cpu.temperature_c == null ? 'Sensor no detectado' : snapshot.cpu.temperature_c < 75 ? 'Normal' : 'Temperatura elevada';
  $('status-system-temp').textContent = systemTemp ? temperature(systemTemp.current_c) : 'No disponible';
  $('status-voltage').textContent = voltage ? `${voltage.volts.toFixed(2)} V` : 'No disponible';
  $('status-voltage-label').textContent = voltage ? `${voltage.label} · ${voltage.source}` : 'Sensor no detectado';

  $('physical-disks').innerHTML = data.physical_disks.map(disk => `<div class="disk-detail">
    <div><strong>${esc(disk.path)} · ${esc(disk.model)}</strong><small>${size(disk.size)} · ${disk.rotational ? 'HDD' : 'SSD'} · ${esc(disk.transport)} · Serie ${esc(disk.serial)}</small></div>
    <div><span class="badge ${disk.state === 'running' ? 'online-badge' : 'neutral'}">${esc(disk.state)}</span><small>SMART: ${esc(disk.smart.available ? 'Disponible' : disk.smart.reason)}</small></div>
  </div>`).join('') || row('Discos físicos', 'No disponibles', 'muted');

  const raid = snapshot.raid;
  $('raid-detail').innerHTML = raid.configured
    ? row('Estado', 'Configurado', 'status') + (raid.arrays || []).map(array => row(array.name || 'Array', array.state || 'Detectado', 'status')).join('')
    : '<div class="empty-state"><strong>Sin RAID configurado</strong><p>No se detectaron arreglos mdadm en este servidor.</p></div>';
  $('sensor-detail').innerHTML = snapshot.temperatures.map(item => row(`${item.source} · ${item.label}`, temperature(item.current_c), 'status')).join('')
    + snapshot.fans.map(item => row(`${item.source} · ${item.label}`, `${item.rpm} RPM`, 'status')).join('')
    + data.voltages.map(item => row(`${item.source} · ${item.label}`, `${item.volts.toFixed(2)} V`, 'status')).join('')
    || row('Sensores', 'No disponibles', 'muted');

  const hardware = data.hardware;
  $('hardware-detail').innerHTML = `<dt>Modelo</dt><dd>${esc(hardware.system_vendor)} ${esc(hardware.system_model)}</dd>
    <dt>Placa base</dt><dd>${esc(hardware.board_vendor)} ${esc(hardware.board_name)} ${esc(hardware.board_version)}</dd>
    <dt>BIOS</dt><dd>${esc(hardware.bios_vendor)} ${esc(hardware.bios_version)} · ${esc(hardware.bios_date)}</dd>
    <dt>Procesador</dt><dd>${esc(snapshot.system.cpu_model)}</dd>
    <dt>Núcleos lógicos</dt><dd>${snapshot.system.cpu_count}</dd>
    <dt>Memoria</dt><dd>${size(snapshot.memory.total)}</dd>
    <dt>Sistema</dt><dd>${esc(snapshot.system.os)} · ${esc(snapshot.system.architecture)}</dd>`;
  $('service-detail').innerHTML = data.services.map(service => row(service.name, service.state, statusClass(service.state))).join('');
  $('docker-detail').innerHTML = snapshot.docker.available
    ? snapshot.docker.containers.map(container => row(container.name, container.status, container.state === 'running' ? 'status' : 'muted')).join('') || row('Docker', 'Sin contenedores', 'muted')
    : row('Docker', valueOr(snapshot.docker.reason), 'muted');
  $('vm-detail').innerHTML = snapshot.virtual_machines.available
    ? (snapshot.virtual_machines.machines || []).map(machine => row(machine.name, machine.state, statusClass(machine.state))).join('') || row('Virtualización', 'Sin máquinas', 'muted')
    : `<div class="empty-state"><strong>No detectadas</strong><p>${esc(snapshot.virtual_machines.reason || 'No hay proveedor de virtualización disponible.')}</p></div>`;
  setConnection(true, snapshot.system.hostname, snapshot.system.uptime_seconds);
  showError(false);
}
async function refreshStatus() {
  try {
    const response = await fetch('/api/server-status', {cache: 'no-store'});
    if (!response.ok) throw new Error('Collector no disponible');
    renderStatus(await response.json());
  } catch (_) { setConnection(false); showError(true); }
}
refreshStatus();
setInterval(refreshStatus, 2000);
