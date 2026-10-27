import RFB from '/static/vendor/novnc/core/rfb.js';
const {$, size, esc, row, setConnection, showError} = window.SHC;
const domain = document.querySelector('.vm-page').dataset.vmId;
const states = {running:'En ejecución', 'shut off':'Apagada', paused:'Pausada', 'in shutdown':'Apagándose', crashed:'Falló', pmsuspended:'Suspendida'};
let machines = [], current = null, busy = false, pending = null, rfb = null, previousStats = null;
const stateLabel = state => states[state] || state;
const button = (id, action, label, danger=false) => `<button data-id="${esc(id)}" data-action="${action}" class="${danger?'danger':''}">${label}</button>`;
function actions(vm) {
  let html = '';
  if(vm.state==='shut off') html += button(vm.id, 'start', '▶ Encender');
  if(vm.state==='running') html += button(vm.id,'shutdown','Apagar') + button(vm.id,'reboot','Reiniciar') + button(vm.id,'pause','Pausar');
  if(vm.state==='paused') html += button(vm.id,'resume','Reanudar');
  if(['running','paused'].includes(vm.state)) html += `<details class="vm-more"><summary>Más ⋮</summary><div>${button(vm.id,'force-off','Forzar apagado',true)}${vm.state==='running'?button(vm.id,'reset','Forzar reinicio',true):''}</div></details>`;
  return html;
}
async function api(path, payload) {
  const response = await fetch(path,{cache:'no-store',...(payload?{method:'POST',headers:{'Content-Type':'application/json','X-SHC-Action':'confirm'},body:JSON.stringify(payload)}:{})});
  const data = await response.json();
  if(!response.ok) throw new Error(typeof data.detail==='string'?data.detail:'No se pudo completar la operación');
  return data;
}
function message(text, error=false) {
  $('vm-message').textContent = text; $('vm-message').classList.remove('hidden'); $('vm-message').classList.toggle('vm-message-error',error);
}
function renderList() {
  const query = $('vm-search').value.toLocaleLowerCase();
  $('vm-total').textContent=machines.length;
  $('vm-running').textContent=machines.filter(vm=>vm.state==='running').length;
  $('vm-cpus').textContent=machines.reduce((total,vm)=>total+vm.vcpus,0);
  $('vm-memory').textContent=size(machines.reduce((total,vm)=>total+vm.memory_bytes,0));
  $('vm-list').innerHTML=machines.filter(vm=>vm.name.toLocaleLowerCase().includes(query)).map(vm=>`<tr><td><a class="vm-name-link" href="/maquinas-virtuales/${vm.id}">${esc(vm.name)}</a><small class="vm-provider">KVM / libvirt</small></td><td><span class="badge ${vm.state==='running'?'online-badge':'neutral'}">${esc(stateLabel(vm.state))}</span></td><td>${vm.vcpus} vCPU</td><td>${size(vm.memory_bytes)}</td><td>${vm.autostart?'Activado':'Desactivado'}</td><td><div class="vm-actions">${actions(vm)}</div></td></tr>`).join('')||'<tr><td colspan="6" class="empty">No hay máquinas que coincidan.</td></tr>';
}
function renderDetail(vm) {
  current=vm;
  $('vm-name').textContent=vm.name;
  $('vm-subtitle').textContent=`KVM / libvirt · ${stateLabel(vm.state)} · ${vm.id}`;
  $('vm-actions').innerHTML=actions(vm);
  $('vm-overview').innerHTML=`<dt>Estado</dt><dd class="${vm.state==='running'?'status':'muted'}">${esc(stateLabel(vm.state))}</dd><dt>Procesador</dt><dd>${vm.vcpus} vCPU · ${esc(vm.cpu_mode)}</dd><dt>Memoria asignada</dt><dd>${size(vm.memory_bytes)}</dd><dt>Arquitectura</dt><dd>${esc(vm.architecture)}</dd><dt>Máquina emulada</dt><dd>${esc(vm.machine)}</dd><dt>Firmware</dt><dd>${esc(vm.firmware)}</dd><dt>Autoinicio</dt><dd>${vm.autostart?'Activado':'Desactivado'}</dd>`;
  const stamp=Date.now(), cpu=Number(vm.stats['cpu.time']), rss=Number(vm.stats['balloon.rss'])*1024;
  const percent=previousStats&&stamp>previousStats.t?Math.max(0,Math.min(100,(cpu-previousStats.cpu)/((stamp-previousStats.t)*1e6*vm.vcpus)*100)):null;
  previousStats={t:stamp,cpu};
  $('vm-usage').innerHTML=row('CPU (respecto de sus vCPU)',Number.isFinite(percent)?`${percent.toFixed(1)}%`:'Tomando muestra…','status')+row('RAM residente (host)',Number.isFinite(rss)&&rss>0?size(rss):'No disponible');
  $('vm-disks').innerHTML=vm.disks.map(disk=>`<tr><td>${esc(disk.target)} · ${esc(disk.device)}</td><td>${disk.capacity==null?'—':size(disk.capacity)}</td><td>${disk.allocation==null?'—':size(disk.allocation)}</td><td>${esc(disk.bus)}</td><td>${esc(disk.format)}</td><td>${disk.readonly?'Sólo lectura':'Lectura / escritura'}</td><td class="vm-source">${esc(disk.source||'Sin medio')}</td></tr>`).join('');
  $('vm-interfaces').innerHTML=vm.interfaces.map(net=>`<tr><td>${esc(net.type)}</td><td>${esc(net.model)}</td><td>${esc(net.mac)}</td><td>${net.addresses.map(address=>`${esc(address.address)} <small>(${esc(address.source)})</small>`).join('<br>')||'No disponible: requiere agente o concesión DHCP'}</td><td>${esc(Object.values(net.source).join(' · '))}</td></tr>`).join('');
  $('vm-devices').innerHTML=row('QEMU Guest Agent',vm.agent_configured?'Canal configurado':'Sin canal',vm.agent_configured?'status':'muted')+row('Watchdog',vm.watchdog.map(item=>`${item.model} · ${item.action}`).join(', ')||'No configurado')+row('Vsock',vm.vsock?'Configurado':'No configurado')+row('Gráficos VNC',vm.vnc?'Configurados':'No configurados');
  $('vm-snapshots').innerHTML=vm.snapshots.map(snapshot=>`<div class="row"><span>${esc(snapshot.name)}</span><div class="vm-actions"><button data-snapshot="${esc(snapshot.name)}" data-config="snapshot-revert">Restaurar</button><button class="danger" data-snapshot="${esc(snapshot.name)}" data-config="snapshot-delete">Eliminar</button></div></div>`).join('')||'<p class="muted">Todavía no hay instantáneas.</p>';
  $('vm-shares').innerHTML=vm.shares.map(share=>row(share.target,`${share.source} · ${share.readonly?'Sólo lectura':'Lectura / escritura'}`)).join('')||'<p class="muted">No hay directorios compartidos.</p>';
  $('vm-guest-services').innerHTML=vm.guest_services.length?vm.guest_services.map(service=>row(service.Name,service.DisplayName,'status')).join(''):`<p class="muted">${esc(vm.guest_services_reason)}</p>`;
  document.querySelector('[data-config="agent"]').disabled=vm.agent_configured;
  document.querySelector('[data-config="watchdog"]').disabled=vm.watchdog.length>0;
  document.querySelector('[data-config="vsock"]').disabled=vm.vsock;
  $('vm-connect').disabled=vm.state!=='running'||!vm.vnc||!!rfb;
}
async function refresh() {
  if(busy) return;
  busy=true;
  try {
    if(domain) renderDetail(await api(`/api/vms/${domain}`));
    else {machines=(await api('/api/vms')).machines;renderList();}
    setConnection(true);showError(false);
  } catch(error) {showError(true);message(error.message,true);}
  finally {busy=false;}
}
const descriptions={start:'Encender la máquina virtual.',shutdown:'Solicitar apagado ordenado al sistema invitado. Puede tardar unos minutos.',reboot:'Solicitar reinicio ordenado del invitado.',pause:'Pausar la ejecución. La memoria permanece reservada en el host.',resume:'Reanudar la ejecución de la máquina.', 'force-off':'Cortar la energía de la VM. Puede perder datos sin guardar o dañar su sistema de archivos.',reset:'Reiniciar inmediatamente la VM. Puede perder datos sin guardar.',autostart:'Cambiar si esta VM se enciende cuando arranca el host.',watchdog:'Agregar watchdog itco con acción reset. Requiere VM apagada y soporte del invitado; se respalda su XML.',vsock:'Agregar VirtIO vsock con CID automático. Requiere VM apagada y controladores compatibles.',agent:'Agregar canal VirtIO de QEMU Guest Agent. Requiere VM apagada. Luego instalá el agente dentro de Windows.',share:'Compartir con Virtiofs un directorio ya preparado en /srv/shc-shares. Requiere VM apagada, virtiofsd en el host y soporte dentro del invitado.',resources:'Cambiar CPU y memoria asignadas. Requiere VM apagada; se respalda su configuración.', 'snapshot-create':'Crear una instantánea de discos qcow2 con la VM apagada. No incluye RAM.', 'snapshot-revert':'Restaurar el estado del disco guardado. Se perderán los cambios posteriores a la instantánea. La VM debe estar apagada.', 'snapshot-delete':'Eliminar esta instantánea guardada. Esta operación no se puede deshacer.'};
function openAction(id,action,name) {
  pending={id,action,name};
  $('vm-dialog-title').textContent=action.startsWith('snapshot')?'Instantáneas': 'Confirmar acción de VM';
  const vm=current||machines.find(item=>item.id===id);
  $('vm-dialog-copy').textContent=`${vm?.name||id}: ${descriptions[action]||action}`;
  let fields='';
  if(action==='autostart') fields=`<label><input name="enabled" type="checkbox" ${vm.autostart?'checked':''}> Iniciar con el sistema</label>`;
  if(action==='resources') fields=`<label>vCPU <input name="cpus" type="number" min="1" max="1024" required value="${vm.vcpus}"></label><label>Memoria (MiB) <input name="memory_mib" type="number" min="256" required value="${Math.round(vm.memory_bytes/1048576)}"></label>`;
  if(action==='snapshot-create'||action==='share') fields=`<label>${action==='share'?'Nombre de directorio existente':'Nombre de instantánea'}<input name="name" maxlength="64" pattern="[A-Za-z0-9][A-Za-z0-9_.-]{0,63}" required value="${action==='snapshot-create'?'snapshot-'+new Date().toISOString().replace(/[:.]/g,'-'):''}"></label>`;
  if(action==='share') fields+='<label><input name="readonly" type="checkbox" checked> Sólo lectura</label>';
  if(['force-off','reset','snapshot-revert','snapshot-delete'].includes(action)) fields+=`<label>Escribí el nombre de la VM para confirmar<input name="verify" autocomplete="off" required></label>`;
  $('vm-dialog-fields').innerHTML=fields;
  $('vm-confirm').disabled=false;
  $('vm-dialog').showModal();
}
document.addEventListener('click',event=>{
  const action=event.target.closest('[data-action]');
  if(action) openAction(action.dataset.id,action.dataset.action);
  const config=event.target.closest('[data-config]');
  if(config&&!config.disabled) openAction(domain,config.dataset.config,config.dataset.snapshot);
});
$('vm-cancel').onclick=()=>$('vm-dialog').close();
$('vm-action-form').onsubmit=async event=>{
  event.preventDefault();
  const form=new FormData(event.target), vm=current||machines.find(item=>item.id===pending.id);
  if(form.has('verify')&&form.get('verify')!==vm.name){message('El nombre de confirmación no coincide.',true);return;}
  const payload={action:pending.action,confirm:true};
  for(const [key,value] of form) if(key!=='verify') payload[key]=value;
  if(pending.name) payload.name=pending.name;
  if(pending.action==='autostart') payload.enabled=form.has('enabled');
  if(pending.action==='share') payload.readonly=form.has('readonly');
  $('vm-confirm').disabled=true;
  try {const result=await api(`/api/vms/${pending.id}`,payload);$('vm-dialog').close();message(result.message);await refresh();}
  catch(error){$('vm-dialog').close();message(error.message,true);}
  finally{$('vm-confirm').disabled=false;}
};
if(!domain){$('vm-search').oninput=renderList;$('vm-refresh').onclick=refresh;}
else {
  $('vm-connect').onclick=()=>{
    if(rfb)return;
    rfb=new RFB($('vm-console'),`wss://${location.host}/ws/vms/${domain}/console`);
    rfb.scaleViewport=true;rfb.resizeSession=false;
    $('vm-console-state').textContent='Conectando…';
    rfb.addEventListener('connect',()=>{$('vm-console-state').textContent='Conectado';$('vm-disconnect').disabled=false;$('vm-send-key').disabled=false;$('vm-connect').disabled=true;});
    rfb.addEventListener('disconnect',()=>{rfb=null;$('vm-console-state').textContent='Consola desconectada';$('vm-disconnect').disabled=true;$('vm-send-key').disabled=true;$('vm-connect').disabled=false;});
    rfb.addEventListener('credentialsrequired',()=>{message('Esta consola requiere contraseña VNC. Configurala desde el hipervisor; no se guarda en el panel.',true);rfb.disconnect();});
  };
  $('vm-disconnect').onclick=()=>rfb?.disconnect();
  $('vm-send-key').onclick=()=>rfb?.sendCtrlAltDel();
  $('vm-fullscreen').onclick=()=>$('vm-console').requestFullscreen();
}
refresh();setInterval(refresh,15000);
fetch('/api/snapshot').then(response=>response.json()).then(data=>{if(data.system)setConnection(true,data.system.hostname,data.system.uptime_seconds);}).catch(()=>{});
window.addEventListener('beforeunload',()=>rfb?.disconnect());
