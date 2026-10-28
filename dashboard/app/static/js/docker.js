(() => {
const {$,size,esc,row,setConnection,showError}=window.SHC;
const containerId=document.querySelector('.docker-page').dataset.containerId;
const stateNames={running:'En ejecución',exited:'Detenido',paused:'Pausado',created:'Creado',restarting:'Reiniciando',dead:'Falló',removing:'Eliminándose'};
let inventory=null, current=null, pending=null, actionBusy=false,lastRefreshError='';
const observedContainers=new Map();
let dockerBaselineReady=false;
const nameOf=state=>stateNames[state]||state;
const date=value=>value&&!value.startsWith('0001')?new Date(value).toLocaleString('es-AR'):'—';
const portText=port=>port.bindings.length?port.bindings.map(binding=>`${binding.HostIp||'*'}:${binding.HostPort} → ${port.destination}`).join(' · '):`${port.destination} (interno)`;
function controls(item){
  if(item.protected)return '<span class="muted">Panel protegido</span>';
  const b=(action,label,danger=false)=>`<button data-id="${item.id}" data-docker-action="${action}" class="${danger?'danger':''}">${label}</button>`;
  let html='';
  if(['exited','created'].includes(item.state))html+=b('start','Iniciar');
  if(item.state==='running')html+=b('stop','Detener')+b('restart','Reiniciar')+b('pause','Pausar');
  if(item.state==='paused')html+=b('unpause','Reanudar');
  if(['running','paused'].includes(item.state))html+=b('kill','Forzar detención',true);
  return html;
}
async function request(path,payload){
  const response=await fetch(path,{cache:'no-store',...(payload?{method:'POST',headers:{'Content-Type':'application/json','X-SHC-Action':'confirm'},body:JSON.stringify(payload)}:{})});
  const result=await response.json();
  if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'Docker no respondió correctamente');
  return result;
}
function message(text,error=false){window.SHC.notify({title:error?'No se pudo completar la acción':'Docker',message:text,severity:error?'error':'info'});}
function observeContainers(items){
  const present=new Set(items.map(item=>item.id));
  for(const [id,old] of observedContainers){if(!present.has(id)){window.SHC.notify({title:`Docker · ${old.name}`,message:'El contenedor ya no aparece en el inventario.',severity:'info'});observedContainers.delete(id);}}
  items.forEach(item=>{
    const before=observedContainers.get(item.id);
    const signature=JSON.stringify([item.health,item.restart_policy,item.restart_count,item.started_at]);
    if(!before&&dockerBaselineReady)window.SHC.notify({title:`Docker · ${item.name}`,message:`Contenedor detectado · ${nameOf(item.state)}`,severity:'info'});
    else if(before&&before.state!==item.state)window.SHC.notify({title:`Docker · ${item.name}`,message:`Estado: ${nameOf(before.state)} → ${nameOf(item.state)}`,severity:item.state==='dead'?'error':'success'});
    else if(before&&before.signature!==signature)window.SHC.notify({title:`Docker · ${item.name}`,message:`Estado: ${nameOf(item.state)} · salud: ${item.health} · política: ${item.restart_policy}`,severity:item.health==='unhealthy'?'warning':'success'});
    observedContainers.set(item.id,{name:item.name,state:item.state,signature});
  });
  dockerBaselineReady=true;
}
function renderInventory(){
  const query=$('docker-search').value.toLocaleLowerCase(),state=$('docker-state').value;
  $('docker-total').textContent=inventory.containers.length;
  $('docker-running').textContent=inventory.containers.filter(item=>item.state==='running').length;
  const taggedImages=inventory.images.filter(image=>image.tagged);
  $('docker-images-count').textContent=taggedImages.length;
  $('docker-volumes-count').textContent=inventory.volumes.length;
  $('docker-engine').textContent=`Docker Engine ${inventory.engine.version} · ${inventory.engine.cpus} CPU · ${size(inventory.engine.memory_bytes)} · ${inventory.engine.driver}`;
  $('docker-containers').innerHTML=inventory.containers.filter(item=>(state==='all'||item.state===state)&&`${item.name} ${item.image} ${item.compose_project||''}`.toLocaleLowerCase().includes(query)).map(item=>`<tr><td><a class="vm-name-link" href="/docker/${item.id}">${esc(item.name)}</a><small class="vm-provider docker-image-name">${esc(item.image)}</small>${item.compose_project?`<small class="vm-provider">Compose: ${esc(item.compose_project)}</small>`:''}</td><td><span class="badge ${item.state==='running'?'online-badge':'neutral'}">${esc(nameOf(item.state))}</span><small class="vm-provider">${esc(item.health)}</small></td><td>${esc(item.stats.CPUPerc||'—')}</td><td>${esc(item.stats.MemUsage||'—')}</td><td class="docker-port-cell">${item.ports.map(port=>esc(portText(port))).join('<br>')||'Sin puertos publicados'}</td><td><div class="vm-actions">${controls(item)}</div></td></tr>`).join('')||'<tr><td colspan="6" class="empty">Sin coincidencias.</td></tr>';
  const showUntagged=$('docker-show-untagged').checked;
  const visibleImages=inventory.images.filter(image=>image.tagged||image.in_use||showUntagged).sort((a,b)=>Number(b.in_use)-Number(a.in_use)||a.Repository.localeCompare(b.Repository));
  const hiddenCount=inventory.images.length-visibleImages.length;
  $('docker-image-summary').textContent=`${visibleImages.length} visibles${hiddenCount?` · ${hiddenCount} sin etiqueta ocultas`:''}`;
  $('docker-images').innerHTML=visibleImages.map(image=>`<tr><td>${esc(image.Repository==='<none>'?'Sin etiqueta':image.Repository)}</td><td>${esc(image.Tag==='<none>'?'—':image.Tag)}</td><td>${esc(image.Size)}</td><td><span class="${image.in_use?'status':'muted'}">${image.in_use?'En uso':'Disponible'}</span></td></tr>`).join('')||'<tr><td colspan="4">Sin imágenes etiquetadas</td></tr>';
  $('docker-networks').innerHTML=inventory.networks.map(network=>row(network.Name,`${network.Driver} · ${network.Scope}`)).join('')||'<p class="muted">Sin redes</p>';
  $('docker-volumes').innerHTML=inventory.volumes.map(volume=>row(volume.Name,volume.Driver)).join('')||'<p class="muted">Sin volúmenes con nombre</p>';
}
function renderDetail(item){
  current=item;
  $('docker-name').textContent=item.name;$('docker-subtitle').textContent=`${nameOf(item.state)} · ${item.image}`;
  $('docker-actions').innerHTML=controls(item);
  $('docker-cpu').textContent=item.stats.CPUPerc||'—';$('docker-memory').textContent=item.stats.MemUsage||'—';
  $('docker-network').textContent=item.stats.NetIO||'—';$('docker-pids').textContent=item.stats.PIDs||'—';
  $('docker-info').innerHTML=`<dt>Estado</dt><dd>${esc(nameOf(item.state))}</dd><dt>Salud</dt><dd>${esc(item.health)}</dd><dt>Creado</dt><dd>${esc(date(item.created_at))}</dd><dt>Iniciado</dt><dd>${esc(date(item.started_at))}</dd><dt>Reinicios</dt><dd>${item.restart_count}</dd><dt>Autorreinicio</dt><dd>${esc(item.restart_policy)}</dd><dt>Compose</dt><dd>${esc([item.compose_project,item.compose_service].filter(Boolean).join(' / ')||'Sin proyecto')}</dd><dt>Salida / OOM</dt><dd>${item.exit_code} / ${item.oom_killed?'Sí':'No'}</dd>`;
  $('docker-limits').innerHTML=`<dt>Límite CPU</dt><dd>${item.cpu_limit||'Sin límite'}</dd><dt>Límite RAM</dt><dd>${item.memory_limit?size(item.memory_limit):'Sin límite'}</dd><dt>Usuario</dt><dd>${esc(item.user)}</dd><dt>Privilegiado</dt><dd>${item.privileged?'Sí':'No'}</dd><dt>Raíz sólo lectura</dt><dd>${item.readonly_rootfs?'Sí':'No'}</dd><dt>Modo de red</dt><dd>${esc(item.network_mode)}</dd>`;
  $('docker-policy').disabled=item.protected;
  $('docker-env').innerHTML=item.environment_keys.map(key=>`<span class="badge">${esc(key)}</span>`).join('')||'<span class="muted">Sin variables</span>';
  $('docker-ports').innerHTML=item.ports.map(port=>row('Puerto',portText(port))).join('')||'<p class="muted">Sin puertos configurados</p>';
  $('docker-container-networks').innerHTML=item.networks.map(net=>row(net.name,[net.IPAddress,net.GlobalIPv6Address,net.Gateway,net.MacAddress].filter(Boolean).join(' · '))).join('');
  $('docker-mounts').innerHTML=item.mounts.map(mount=>`<tr><td>${esc(mount.Type)}</td><td class="vm-source" title="${esc(mount.Source)}">${esc(mount.Name||mount.Source)}</td><td>${esc(mount.Destination)}</td><td>${mount.RW?'Lectura / escritura':'Sólo lectura'}</td></tr>`).join('')||'<tr><td colspan="4">Sin montajes</td></tr>';
  $('docker-processes').innerHTML=item.processes.map(process=>row(process[0],process[1]||'')).join('')||`<p class="muted">${esc(item.processes_reason)}</p>`;
}
const live=window.SHC.createLiveRefresh({load:()=>request(containerId?`/api/docker/${containerId}`:'/api/docker'),
  render:data=>{observeContainers(containerId?[data]:data.containers);if(containerId)renderDetail(data);else{inventory=data;renderInventory();}showError(false);setConnection(true);lastRefreshError='';},
  blocked:()=>document.hidden||$('docker-dialog').open,
  onError:error=>{showError(true);if(lastRefreshError!==error.message)message(error.message,true);lastRefreshError=error.message;},interval:3000});
function refresh(){return live.request(true);}
function selectAction(id,action){
  const item=current||inventory.containers.find(container=>container.id===id);
  pending={id,action,name:item.name};
  const copy={start:'Iniciar este contenedor.',stop:'Solicitar detención ordenada. Docker puede forzar la detención si no responde dentro de su tiempo de espera.',restart:'Reiniciar este contenedor. El servicio tendrá una interrupción.',pause:'Congelar sus procesos hasta reanudarlo.',unpause:'Reanudar los procesos.',kill:'Detener inmediatamente sus procesos. Puede perder datos sin guardar.', 'restart-policy':'Cambiar la política de reinicio automático de este contenedor.'};
  $('docker-dialog-copy').textContent=`${item.name}: ${copy[action]}`;
  $('docker-dialog-fields').innerHTML=action==='restart-policy'?`<label>Política<select name="policy">${['no','always','unless-stopped','on-failure'].map(policy=>`<option ${item.restart_policy===policy?'selected':''}>${policy}</option>`).join('')}</select></label>`:action==='kill'?'<label>Escribí el nombre del contenedor<input name="verify" required autocomplete="off"></label>':'';
  $('docker-confirm').disabled=false;$('docker-dialog').showModal();
}
document.addEventListener('click',event=>{const button=event.target.closest('[data-docker-action]');if(button)selectAction(button.dataset.id,button.dataset.dockerAction);});
$('docker-cancel').onclick=()=>$('docker-dialog').close();
$('docker-action-form').onsubmit=async event=>{
  event.preventDefault();if(actionBusy)return;const fields=new FormData(event.target),payload={action:pending.action,confirm:true};
  for(const [key,value] of fields)payload[key]=value;
  if(pending.action==='kill'&&payload.verify!==pending.name){message('El nombre de confirmación no coincide.',true);return;}
  $('docker-confirm').disabled=true;
  actionBusy=true;live.pause();
  try{const result=await request(`/api/docker/${pending.id}`,payload);$('docker-dialog').close();message(`${pending.name}: ${result.message}`);}
  catch(error){$('docker-dialog').close();message(error.message,true);}finally{actionBusy=false;$('docker-confirm').disabled=false;await live.resume();}
};
if(containerId){
  $('docker-policy').onclick=()=>selectAction(containerId,'restart-policy');
  $('docker-logs-refresh').onclick=async()=>{const button=$('docker-logs-refresh');button.disabled=true;try{const logs=await request(`/api/docker/${containerId}/logs`);$('docker-logs').textContent=logs.text||'No hay logs recientes.';}catch(error){message(error.message,true);}finally{button.disabled=false;}};
  $('docker-logs-clear').onclick=()=>$('docker-logs').textContent='Vista de logs limpiada.';
}else{$('docker-search').oninput=renderInventory;$('docker-state').onchange=renderInventory;$('docker-refresh').onclick=refresh;$('docker-show-untagged').onchange=renderInventory;}
refresh();document.addEventListener('visibilitychange',()=>{if(!document.hidden)live.request();});
window.addEventListener('beforeunload',()=>live.stop());
fetch('/api/snapshot').then(response=>response.json()).then(data=>{if(data.system)setConnection(true,data.system.hostname,data.system.uptime_seconds);}).catch(()=>{});
})();
