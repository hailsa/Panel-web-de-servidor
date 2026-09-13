const {$, size, esc, row, setConnection, showError} = window.SHC;
function render(data) {
  setConnection(true, data.system.hostname, data.system.uptime_seconds);
  showError(false);
  $('cpu').textContent = `${data.cpu.percent.toFixed(1)}%`;
  $('cpu-extra').textContent = `${data.system.cpu_count} núcleos · ${data.cpu.frequency_mhz ? Math.round(data.cpu.frequency_mhz) + ' MHz' : '—'}`;
  $('ram').textContent = `${data.memory.percent.toFixed(1)}%`;
  $('ram-extra').textContent = `${size(data.memory.used)} / ${size(data.memory.total)}`;
  const root = data.filesystems.find(item => item.mountpoint === '/') || data.filesystems[0];
  $('storage').textContent = root ? `${root.percent.toFixed(1)}%` : '—';
  $('storage-extra').textContent = root ? `${size(root.used)} / ${size(root.total)}` : 'No disponible';
  $('network').textContent = `↓ ${size(data.network.bytes_received)}  ↑ ${size(data.network.bytes_sent)}`;
  $('temperature').textContent = data.cpu.temperature_c != null ? `${data.cpu.temperature_c.toFixed(1)} °C` : 'No disponible';
  const addresses = data.network.addresses.filter(item => item.address !== '127.0.0.1').map(item => `${item.interface}: ${item.address}`).join(' · ');
  $('system-info').innerHTML = `<dt>Hostname</dt><dd>${esc(data.system.hostname)}</dd><dt>IP</dt><dd>${esc(addresses)}</dd><dt>Sistema operativo</dt><dd>${esc(data.system.os)}</dd><dt>Kernel</dt><dd>${esc(data.system.kernel)}</dd><dt>CPU</dt><dd>${esc(data.system.cpu_model)}</dd><dt>Arquitectura</dt><dd>${esc(data.system.architecture)}</dd>`;
  $('services').innerHTML = row('Collector', 'En ejecución', 'status') + row('Docker', data.docker.available ? 'Disponible' : 'No disponible', data.docker.available ? 'status' : 'muted') + row('RAID', data.raid.configured ? 'Configurado' : 'No configurado', 'muted') + row('Máquinas virtuales', 'No detectadas', 'muted');
  $('disks').innerHTML = data.filesystems.map(item => `<div class="bar-block"><div class="bar-label"><span>${esc(item.mountpoint)} <small class="muted">${esc(item.device)}</small></span><span>${item.percent.toFixed(1)}% · ${size(item.used)} / ${size(item.total)}</span></div><div class="bar"><i style="width:${Math.min(100, item.percent)}%"></i></div></div>`).join('') || row('Filesystems', 'No disponibles', 'muted');
  $('ports').innerHTML = data.ports.filter(item => [22, 80, 443, 9993].includes(item.port) || item.address.startsWith('127.')).map(item => `<tr><td>${item.port}</td><td>${esc(item.protocol.toUpperCase())}</td><td>${esc(item.address)}</td></tr>`).join('');
  $('containers').innerHTML = data.docker.containers.map(item => row(item.name, item.status, item.state === 'running' ? 'status' : 'muted')).join('') || row('Docker', 'Sin contenedores', 'muted');
  $('sensors').innerHTML = data.temperatures.slice(0, 7).map(item => row(item.label, `${item.current_c.toFixed(1)} °C`, 'status')).join('') + data.fans.slice(0, 2).map(item => row(item.label, `${item.rpm} RPM`, 'status')).join('');
}
async function refresh() {
  try {
    const response = await fetch('/api/snapshot', {cache: 'no-store'});
    if (!response.ok) throw new Error('Collector no disponible');
    render(await response.json());
  } catch (_) { setConnection(false); showError(true); }
}
refresh();
setInterval(refresh, 2000);
