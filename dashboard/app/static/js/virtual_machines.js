import RFB from '/static/vendor/novnc/core/rfb.js';
const {$, size, esc, row, setConnection, showError} = window.SHC;
const domain = document.querySelector('.vm-page').dataset.vmId;
const states = {running:'En ejecución', 'shut off':'Apagada', paused:'Pausada', 'in shutdown':'Apagándose', crashed:'Falló', pmsuspended:'Suspendida'};
let machines = [], current = null, pending = null, rfb = null, previousStats = null, actionBusy=false,lastRefreshError='';
const observedVMs=new Map();
let vmBaselineReady=false;
const stateLabel = state => states[state] || state;
const button = (id, action, label, danger=false) => `<button data-id="${esc(id)}" data-action="${action}" class="${danger?'danger':''}">${label}</button>`;
function actions(vm) {
  let html = '';
  if(vm.state==='shut off') html += button(vm.id, 'start', '▶ Encender');
  if(vm.state==='running') html += button(vm.id,'shutdown','Apagar') + button(vm.id,'reboot','Reiniciar') + button(vm.id,'pause','Pausar');
  if(vm.state==='paused') html += button(vm.id,'resume','Reanudar');
  if(['running','paused'].includes(vm.state)) html += `<button type="button" popovertarget="vm-more-${vm.id}" aria-label="Más acciones de ${esc(vm.name)}">Más ⋮</button><div popover id="vm-more-${vm.id}" class="vm-action-popover">${button(vm.id,'force-off','Forzar apagado',true)}${vm.state==='running'?button(vm.id,'reset','Forzar reinicio',true):''}</div>`;
  return html;
}
async function api(path, payload) {
  const response = await fetch(path,{cache:'no-store',...(payload?{method:'POST',headers:{'Content-Type':'application/json','X-SHC-Action':'confirm'},body:JSON.stringify(payload)}:{})});
  const data = await response.json();
  if(!response.ok) throw new Error(typeof data.detail==='string'?data.detail:'No se pudo completar la operación');
  return data;
}
function message(text, error=false) {
  window.SHC.notify({title:error?'No se pudo completar la acción':'Máquinas virtuales',message:text,severity:error?'error':'info'});
}
function observeVMs(items){
  const present=new Set(items.map(vm=>vm.id));
  for(const [id,old] of observedVMs){if(!present.has(id)){window.SHC.notify({title:`VM · ${old.name}`,message:'La máquina ya no aparece en el inventario de libvirt.',severity:'info'});observedVMs.delete(id);}}
  items.forEach(vm=>{
    const before=observedVMs.get(vm.id);
    const signature=JSON.stringify([vm.autostart,vm.vcpus,vm.memory_bytes,vm.agent_configured,vm.vsock,vm.watchdog,vm.shares,vm.snapshots,vm.interfaces?.map(({addresses,target,...config})=>config)]);
    if(!before&&vmBaselineReady)window.SHC.notify({title:`VM · ${vm.name}`,message:`Máquina detectada · ${stateLabel(vm.state)}`,severity:'info'});
    else if(before&&before.state!==vm.state)window.SHC.notify({title:`VM · ${vm.name}`,message:`Estado: ${stateLabel(before.state)} → ${stateLabel(vm.state)}`,severity:vm.state==='crashed'?'error':'success'});
    else if(before&&before.signature!==signature)window.SHC.notify({title:`VM · ${vm.name}`,message:'La configuración se actualizó correctamente.',severity:'success'});
    observedVMs.set(vm.id,{name:vm.name,state:vm.state,signature});
  });
  vmBaselineReady=true;
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
  $('vm-overview').innerHTML=`<dt>Estado</dt><dd class="${vm.state==='running'?'status':'muted'}">${esc(stateLabel(vm.state))}</dd><dt>Direcciones IP</dt><dd class="vm-overview-ips">${window.SHC.vmNetwork.addressHTML(vm)}</dd><dt>Procesador</dt><dd>${vm.vcpus} vCPU · ${esc(vm.cpu_mode)}</dd><dt>Memoria asignada</dt><dd>${size(vm.memory_bytes)}</dd><dt>Arquitectura</dt><dd>${esc(vm.architecture)}</dd><dt>Máquina emulada</dt><dd>${esc(vm.machine)}</dd><dt>Firmware</dt><dd>${esc(vm.firmware)}</dd><dt>Autoinicio</dt><dd>${vm.autostart?'Activado':'Desactivado'}</dd>`;
  const stamp=Date.now(), cpu=Number(vm.stats['cpu.time']), rss=Number(vm.stats['balloon.rss'])*1024;
  const percent=previousStats&&stamp>previousStats.t?Math.max(0,Math.min(100,(cpu-previousStats.cpu)/((stamp-previousStats.t)*1e6*vm.vcpus)*100)):null;
  previousStats={t:stamp,cpu};
  $('vm-usage').innerHTML=row('CPU (respecto de sus vCPU)',Number.isFinite(percent)?`${percent.toFixed(1)}%`:'Tomando muestra…','status')+row('RAM residente (host)',Number.isFinite(rss)&&rss>0?size(rss):'No disponible');
  $('vm-disks').innerHTML=vm.disks.map(disk=>`<tr><td>${esc(disk.target)} · ${esc(disk.device)}</td><td>${disk.capacity==null?'—':size(disk.capacity)}</td><td>${disk.allocation==null?'—':size(disk.allocation)}</td><td>${esc(disk.bus)}</td><td>${esc(disk.format)}</td><td>${disk.readonly?'Sólo lectura':'Lectura / escritura'}</td><td class="vm-source">${esc(disk.source||'Sin medio')}</td></tr>`).join('');
  $('vm-interfaces').innerHTML=vm.interfaces.map((net,index)=>`<tr><td class="vm-network-connection">${esc(window.SHC.vmNetwork.connectionLabel(net))}</td><td>${esc(net.model)}${net.mtu?`<small class="vm-provider">MTU ${esc(net.mtu)}</small>`:''}${net.queues?`<small class="vm-provider">${esc(net.queues)} colas</small>`:''}</td><td>${esc(net.mac)}</td><td>${window.SHC.vmNetwork.addressHTML({...vm,interfaces:[net]})}</td><td>${net.link_state==='down'?'Desconectado':'Conectado'}</td><td><button data-network-index="${index}" ${net.editable?'':'disabled'}>Editar</button></td></tr>`).join('')||'<tr><td colspan="6">Sin interfaces. Agregá una para conectar esta VM.</td></tr>';
  $('vm-devices').innerHTML=row('QEMU Guest Agent',vm.agent_configured?'Canal configurado':'Sin canal',vm.agent_configured?'status':'muted')+row('Watchdog',vm.watchdog.map(item=>`${item.model} · ${item.action}`).join(', ')||'No configurado')+row('Vsock',vm.vsock?'Configurado':'No configurado')+row('Gráficos VNC',vm.vnc?'Configurados':'No configurados');
  $('vm-snapshots').innerHTML=vm.snapshots.map(snapshot=>`<div class="row"><span>${esc(snapshot.name)}</span><div class="vm-actions"><button data-snapshot="${esc(snapshot.name)}" data-config="snapshot-revert">Restaurar</button><button class="danger" data-snapshot="${esc(snapshot.name)}" data-config="snapshot-delete">Eliminar</button></div></div>`).join('')||'<p class="muted">Todavía no hay instantáneas.</p>';
  $('vm-shares').innerHTML=vm.shares.map(share=>row(share.target,`${share.source} · ${share.readonly?'Sólo lectura':'Lectura / escritura'}`)).join('')||'<p class="muted">No hay directorios compartidos.</p>';
  $('vm-guest-services').innerHTML=vm.guest_services.length?vm.guest_services.map(service=>row(service.Name,service.DisplayName,'status')).join(''):`<p class="muted">${esc(vm.guest_services_reason)}</p>`;
  updateAvailability();
  if(rfb&&!['running','paused'].includes(vm.state))rfb.disconnect();
}
function updateAvailability(){
  if(!current)return;
  const vm=current,offline=vm.state!=='shut off'?'Apagá la VM para modificar sus dispositivos o recursos.':'';
  const unavailable=window.SHC.setUnavailable;
  unavailable(document.querySelector('[data-config="agent"]'),vm.agent_configured?'Esta VM ya tiene configurado el canal QEMU Guest Agent. No se puede agregar otro. El servicio del agente debe instalarse y activarse dentro del invitado.':offline);
  unavailable(document.querySelector('[data-config="watchdog"]'),vm.watchdog.length?'Esta VM ya tiene un watchdog configurado. No se puede agregar un segundo desde el panel.':offline);
  unavailable(document.querySelector('[data-config="vsock"]'),vm.vsock?'Esta VM ya tiene un dispositivo vsock configurado.':offline);
  for(const action of ['resources','share'])unavailable(document.querySelector(`[data-config="${action}"]`),offline);
  unavailable($('vm-connect'),!vm.vnc?'Esta VM no tiene gráficos VNC configurados.':rfb?'La consola VNC ya está conectada o conectándose.':vm.state!=='running'?'Encendé la VM para conectar la consola VNC.':'');
  const connected=!!rfb&&$('vm-console-state').textContent==='Conectado';
  unavailable($('vm-disconnect'),!rfb?'No hay una conexión VNC activa para desconectar.':connected?'':'La consola todavía se está conectando.');
  unavailable($('vm-send-key'),connected?'':'Conectá la consola VNC antes de enviar Ctrl + Alt + Supr.');
  document.querySelectorAll('[data-network-index]').forEach(button=>unavailable(button,current.interfaces[Number(button.dataset.networkIndex)]?.editable?'':'Este tipo de interfaz no admite edición desde el panel. Configurala desde el hipervisor.'));
}
const live=window.SHC.createLiveRefresh({
  load:()=>api(domain?`/api/vms/${domain}`:'/api/vms'),
  render:data=>{observeVMs(domain?[data]:data.machines);if(domain)renderDetail(data);else{machines=data.machines;renderList();}setConnection(true);showError(false);lastRefreshError='';},
  blocked:()=>document.hidden||!!document.querySelector('.vm-action-popover:popover-open')||$('vm-dialog').open,
  onError:error=>{showError(true);if(lastRefreshError!==error.message)message(error.message,true);lastRefreshError=error.message;},interval:3000
});
function refresh(){return live.request(true);}
const descriptions={start:'Encender la máquina virtual.',shutdown:'Solicitar apagado ordenado al sistema invitado. Puede tardar unos minutos.',reboot:'Solicitar reinicio ordenado del invitado.',pause:'Pausar la ejecución. La memoria permanece reservada en el host.',resume:'Reanudar la ejecución de la máquina.', 'force-off':'Cortar la energía de la VM. Puede perder datos sin guardar o dañar su sistema de archivos.',reset:'Reiniciar inmediatamente la VM. Puede perder datos sin guardar.',autostart:'Cambiar si esta VM se enciende cuando arranca el host.',watchdog:'Agregar watchdog itco con acción reset. Requiere VM apagada y soporte del invitado; se respalda su XML.',vsock:'Agregar VirtIO vsock con CID automático. Requiere VM apagada y controladores compatibles.',agent:'Agregar canal VirtIO de QEMU Guest Agent. Requiere VM apagada. Luego instalá el agente dentro de Windows.',share:'Compartir con Virtiofs un directorio ya preparado en /srv/shc-shares. Requiere VM apagada, virtiofsd en el host y soporte dentro del invitado.',resources:'Cambiar CPU y memoria asignadas. Requiere VM apagada; se respalda su configuración.', 'snapshot-create':'Crear una instantánea de discos qcow2 con la VM apagada. No incluye RAM.', 'snapshot-revert':'Restaurar el estado del disco guardado. Se perderán los cambios posteriores a la instantánea. La VM debe estar apagada.', 'snapshot-delete':'Eliminar esta instantánea guardada. Esta operación no se puede deshacer.'};
function openAction(id,action,name) {
  window.SHC.setUnavailable?.($('vm-confirm'),'');
  $('vm-dialog').classList.remove('vm-network-dialog');
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
async function openNetwork(index=null){
  if(!current||actionBusy)return;
  const vm=current,net=index===null?null:vm.interfaces[index];
  if(index!==null&&!net?.editable)return;
  pending={id:domain,action:net?'network-edit':'network-add',interface_mac:net?.mac};
  $('vm-dialog').classList.add('vm-network-dialog');
  $('vm-dialog-title').textContent=net?'Editar interfaz de red':'Agregar interfaz de red';
  $('vm-dialog-copy').textContent=`${vm.name} · ${vm.state==='shut off'?'Los cambios se guardan para el próximo encendido. Se respalda el XML de la VM.':'Podés revisar las opciones; apagá la VM y volvé a abrir este menú para guardar cambios.'}`;
  $('vm-dialog-fields').textContent='Consultando redes e interfaces disponibles…';
  window.SHC.setUnavailable($('vm-confirm'),'Esperá a que se carguen las redes disponibles.');
  const operation=pending;
  $('vm-dialog').showModal();
  try {
    const options=await api('/api/vm-network-options');
    if(!$('vm-dialog').open||pending!==operation)return;
    $('vm-dialog-fields').innerHTML=window.SHC.vmNetwork.editor(vm,net,options);
    window.SHC.vmNetwork.bindEditor(net,options);
    window.SHC.setUnavailable($('vm-confirm'),vm.state!=='shut off'?'Apagá la VM y volvé a abrir el editor para guardar los cambios de red.':'');
  }catch(error){if($('vm-dialog').open&&pending===operation){$('vm-dialog-fields').textContent=error.message;window.SHC.setUnavailable($('vm-confirm'),'No se pudieron cargar las opciones de red. Cerrá el editor y volvé a intentarlo.');}message(error.message,true);}
}
document.addEventListener('click',event=>{
  const network=event.target.closest('[data-network-index]');
  if(network&&!network.disabled)openNetwork(Number(network.dataset.networkIndex));
  const trigger=event.target.closest('[popovertarget]');
  if(trigger){
    const menu=$(trigger.getAttribute('popovertarget')), rect=trigger.getBoundingClientRect();
    menu.style.left=`${Math.max(8,Math.min(innerWidth-238,rect.right-230))}px`;
    menu.style.top=`${rect.bottom+130>innerHeight?Math.max(8,rect.top-115):rect.bottom+6}px`;
  }
  const action=event.target.closest('[data-action]');
  if(action){document.querySelectorAll('.vm-action-popover:popover-open').forEach(menu=>menu.hidePopover());openAction(action.dataset.id,action.dataset.action);}
  const config=event.target.closest('[data-config]');
  if(config&&!config.disabled) openAction(domain,config.dataset.config,config.dataset.snapshot);
});
$('vm-cancel').onclick=()=>$('vm-dialog').close();
$('vm-action-form').onsubmit=async event=>{
  event.preventDefault();
  if(actionBusy)return;
  const form=new FormData(event.target), vm=current||machines.find(item=>item.id===pending.id);
  if(form.has('verify')&&form.get('verify')!==vm.name){message('El nombre de confirmación no coincide.',true);return;}
  const payload={action:pending.action,confirm:true};
  for(const [key,value] of form) if(key!=='verify') payload[key]=value;
  if(pending.name) payload.name=pending.name;
  if(pending.action==='autostart') payload.enabled=form.has('enabled');
  if(pending.action==='share') payload.readonly=form.has('readonly');
  if(pending.action.startsWith('network-')){payload.interface_mac=pending.interface_mac;payload.direct_bridge=true;}
  $('vm-confirm').disabled=true;
  actionBusy=true;live.pause();
  try {await api(`/api/vms/${pending.id}`,payload);$('vm-dialog').close();message(`${vm.name}: solicitud enviada. El estado se confirmará automáticamente.`);}
  catch(error){$('vm-dialog').close();message(error.message,true);}
  finally{actionBusy=false;$('vm-confirm').disabled=false;await live.resume();}
};
if(!domain){$('vm-search').oninput=renderList;$('vm-refresh').onclick=refresh;}
else {
  $('vm-add-network').onclick=()=>openNetwork();
  $('vm-connect').onclick=()=>{
    if(rfb)return;
    rfb=new RFB($('vm-console'),`wss://${location.host}/ws/vms/${domain}/console`);
    rfb.scaleViewport=true;rfb.resizeSession=false;
    $('vm-console-state').textContent='Conectando…';
    updateAvailability();
    rfb.addEventListener('connect',()=>{$('vm-console-state').textContent='Conectado';updateAvailability();});
    rfb.addEventListener('disconnect',()=>{rfb=null;$('vm-console-state').textContent='Consola desconectada';updateAvailability();});
    rfb.addEventListener('credentialsrequired',()=>{message('Esta consola requiere contraseña VNC. Configurala desde el hipervisor; no se guarda en el panel.',true);rfb.disconnect();});
  };
  $('vm-disconnect').onclick=()=>rfb?.disconnect();
  $('vm-send-key').onclick=()=>rfb?.sendCtrlAltDel();
  $('vm-fullscreen').onclick=()=>$('vm-console').requestFullscreen();
}
refresh();
document.addEventListener('visibilitychange',()=>{if(!document.hidden)live.request();});
fetch('/api/snapshot').then(response=>response.json()).then(data=>{if(data.system)setConnection(true,data.system.hostname,data.system.uptime_seconds);}).catch(()=>{});
window.addEventListener('beforeunload',()=>{live.stop();rfb?.disconnect();});
