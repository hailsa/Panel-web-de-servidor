const {$, size, esc, row, setConnection, showError} = window.SHC;
const HISTORY_KEY = 'shc-resource-history-v1';
const HISTORY_MAX_AGE = 24 * 60 * 60 * 1000;
const HISTORY_STEP = 20000;
const spark = {cpu: [], ram: [], storage: [], network: [], temperature: []};
let history = loadHistory();

function loadHistory() {
  try {
    const stored = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    return Array.isArray(stored) ? stored.filter(point => Number(point.t) > Date.now() - HISTORY_MAX_AGE) : [];
  } catch (_) { return []; }
}

function remember(cpu, ram, disk) {
  const point = {t: Date.now(), cpu, ram, disk};
  const last = history.at(-1);
  if (last && point.t - last.t < HISTORY_STEP) Object.assign(last, {cpu, ram, disk});
  else history.push(point);
  history = history.filter(item => item.t > Date.now() - HISTORY_MAX_AGE);
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(history)); } catch (_) { /* storage is optional */ }
}

function pushSpark(name, value) {
  if (!Number.isFinite(value)) return;
  spark[name].push(value);
  if (spark[name].length > 30) spark[name].shift();
  const values = spark[name];
  const fixedScale = ['cpu', 'ram', 'storage'].includes(name);
  const low = fixedScale ? 0 : Math.min(...values);
  const high = fixedScale ? 100 : Math.max(...values);
  const range = Math.max(1, high - low);
  const points = values.map((item, index) => `${values.length === 1 ? 100 : index * 100 / (values.length - 1)},${34 - ((item - low) / range) * 30}`).join(' ');
  $(`${name}-spark`).setAttribute('points', points);
}

function drawChart() {
  const canvas = $('resource-chart');
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * ratio);
  canvas.height = Math.round(rect.height * ratio);
  const context = canvas.getContext('2d');
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  const width = rect.width;
  const height = rect.height;
  const pad = {left: 34, right: 8, top: 8, bottom: 22};
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const style = getComputedStyle(document.documentElement);
  const colors = {cpu: style.getPropertyValue('--green').trim(), ram: style.getPropertyValue('--blue').trim(), disk: '#a855f7'};
  context.clearRect(0, 0, width, height);
  context.font = '10px system-ui';
  context.fillStyle = style.getPropertyValue('--muted').trim();
  context.strokeStyle = style.getPropertyValue('--border').trim();
  context.lineWidth = 1;
  for (let value = 0; value <= 100; value += 25) {
    const y = pad.top + plotHeight - value / 100 * plotHeight;
    context.beginPath(); context.moveTo(pad.left, y); context.lineTo(width - pad.right, y); context.stroke();
    context.fillText(String(value), 4, y + 3);
  }
  if (!history.length) return;
  const visible = history.length > plotWidth ? history.filter((_, index) => index % Math.ceil(history.length / plotWidth) === 0) : history;
  const drawLine = (field, color) => {
    context.beginPath();
    visible.forEach((point, index) => {
      const x = pad.left + (visible.length === 1 ? plotWidth : index * plotWidth / (visible.length - 1));
      const y = pad.top + plotHeight - Math.min(100, Math.max(0, Number(point[field]) || 0)) / 100 * plotHeight;
      if (index === 0) context.moveTo(x, y); else context.lineTo(x, y);
    });
    context.strokeStyle = color; context.lineWidth = 1.7; context.stroke();
  };
  drawLine('cpu', colors.cpu); drawLine('ram', colors.ram); drawLine('disk', colors.disk);
  const time = value => new Intl.DateTimeFormat('es-AR', {hour: '2-digit', minute: '2-digit'}).format(new Date(value));
  context.fillStyle = style.getPropertyValue('--muted').trim();
  context.fillText(time(visible[0].t), pad.left, height - 4);
  const end = time(visible.at(-1).t);
  context.fillText(end, width - pad.right - context.measureText(end).width, height - 4);
  const minutes = Math.max(1, Math.round((visible.at(-1).t - visible[0].t) / 60000));
  $('chart-range').textContent = `${minutes < 60 ? minutes + ' min' : (minutes / 60).toFixed(1) + ' h'} · historial local hasta 24 h`;
}

function renderProcesses(processes) {
  $('processes').innerHTML = processes.map(process => `<tr><td>${process.pid}</td><td title="${esc(process.name)}">${esc(process.name)}</td><td>${process.cpu_percent.toFixed(1)}%</td><td>${process.memory_percent.toFixed(1)}%</td></tr>`).join('') || '<tr><td colspan="4" class="empty compact-empty">No disponible</td></tr>';
}

function render(data) {
  setConnection(true, data.system.hostname, data.system.uptime_seconds);
  showError(false);
  const root = data.filesystems.find(item => item.mountpoint === '/') || data.filesystems[0];
  const diskPercent = root ? root.percent : 0;
  const networkRate = data.network.bytes_received_per_second + data.network.bytes_sent_per_second;
  $('cpu').textContent = `${data.cpu.percent.toFixed(1)}%`;
  $('cpu-extra').textContent = `${data.system.cpu_count} núcleos · ${data.cpu.frequency_mhz ? Math.round(data.cpu.frequency_mhz) + ' MHz' : '—'}`;
  $('ram').textContent = `${data.memory.percent.toFixed(1)}%`;
  $('ram-extra').textContent = `${size(data.memory.used)} / ${size(data.memory.total)}`;
  $('storage').textContent = root ? `${root.percent.toFixed(1)}%` : '—';
  $('storage-extra').textContent = root ? `${size(root.used)} / ${size(root.total)}` : 'No disponible';
  $('network').innerHTML = `<span>↓ ${size(data.network.bytes_received_per_second)}/s</span><span>↑ ${size(data.network.bytes_sent_per_second)}/s</span>`;
  $('temperature').textContent = data.cpu.temperature_c != null ? `${data.cpu.temperature_c.toFixed(1)} °C` : 'No disponible';
  pushSpark('cpu', data.cpu.percent); pushSpark('ram', data.memory.percent); pushSpark('storage', diskPercent); pushSpark('network', networkRate); pushSpark('temperature', data.cpu.temperature_c);
  remember(data.cpu.percent, data.memory.percent, diskPercent); drawChart();
  const hostAddresses = data.network.addresses.filter(item => item.address !== '127.0.0.1' && item.interface !== 'docker0' && !item.interface.startsWith('br-'));
  const privateNetwork = hostAddresses.find(item => /^zt/i.test(item.interface));
  const localNetwork = hostAddresses.find(item => !/^zt/i.test(item.interface)) || hostAddresses[0];
  const networkRows = `<dt>IP local</dt><dd>${esc(localNetwork ? localNetwork.address : 'No disponible')}</dd>` + (privateNetwork ? `<dt>Red privada</dt><dd>${esc(privateNetwork.address)}</dd>` : '');
  $('system-info').innerHTML = `<dt>Hostname</dt><dd>${esc(data.system.hostname)}</dd>${networkRows}<dt>Sistema operativo</dt><dd>${esc(data.system.os)}</dd><dt>Kernel</dt><dd>${esc(data.system.kernel)}</dd><dt>CPU</dt><dd>${esc(data.system.cpu_model)}</dd><dt>Arquitectura</dt><dd>${esc(data.system.architecture)}</dd>`;
  renderProcesses(data.processes || []);
  $('services').innerHTML = row('Collector', 'En ejecución', 'status') + row('Docker', data.docker.available ? `${data.docker.containers.length} contenedores` : 'No disponible', data.docker.available ? 'status' : 'muted') + row('RAID', data.raid.configured ? 'Configurado' : 'No configurado', data.raid.configured ? 'status' : 'muted') + row('Máquinas virtuales', data.virtual_machines.available ? `${data.virtual_machines.machines.length} detectadas` : 'No detectadas', 'muted');
  $('disks').innerHTML = data.filesystems.map(item => `<div class="bar-block"><div class="bar-label"><span>${esc(item.mountpoint)} <small class="muted">${esc(item.device)}</small></span><span>${item.percent.toFixed(1)}% · ${size(item.used)} / ${size(item.total)}</span></div><div class="bar"><i style="width:${Math.min(100, item.percent)}%"></i></div></div>`).join('') || row('Filesystems', 'No disponibles', 'muted');
  $('ports').innerHTML = data.ports.filter(item => [22, 80, 443, 9993].includes(item.port) || item.address.startsWith('127.')).map(item => `<tr><td>${item.port}</td><td>${esc(item.protocol.toUpperCase())}</td><td>${esc(item.address)}</td></tr>`).join('');
  $('containers').innerHTML = data.docker.containers.map(item => row(item.name, item.status, item.state === 'running' ? 'status' : 'muted')).join('') || row('Docker', 'Sin contenedores', 'muted');
  $('sensors').innerHTML = data.temperatures.slice(0, 7).map(item => row(item.label, `${item.current_c.toFixed(1)} °C`, 'status')).join('') + data.fans.slice(0, 2).map(item => row(item.label, `${item.rpm} RPM`, 'status')).join('') || row('Sensores', 'No disponibles', 'muted');
}

async function refresh() {
  try {
    const response = await fetch('/api/snapshot', {cache: 'no-store'});
    if (!response.ok) throw new Error('Collector no disponible');
    render(await response.json());
  } catch (_) { setConnection(false); showError(true); }
}

window.addEventListener('resize', drawChart);
new MutationObserver(drawChart).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
refresh();
setInterval(refresh, 2000);
