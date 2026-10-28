(() => {
const {$,size,esc,setConnection}=window.SHC;
let options=null,payload=null,busy=false,requestId=crypto.randomUUID();
function error(message){$('create-error').textContent=message;$('create-error').classList.toggle('hidden',!message);}
async function api(operation,data){
  const response=await fetch('/api/vm-creation/'+operation,{cache:'no-store',...(data?{method:'POST',headers:{'Content-Type':'application/json','X-SHC-Action':'confirm'},body:JSON.stringify(data)}:{})});
  const result=await response.json();if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'No se pudo completar la operación');return result;
}
function help(){
  if(!options)return;
  const pool=options.pools.find(item=>item.id===$('create-pool').value);
  $('create-pool-help').textContent=pool?`${pool.path} · libres ${size(pool.free_bytes)}`:'No hay pools disponibles para crear discos.';
  const net=options.networks.find(item=>item.id===$('create-network').value);
  $('create-network-help').textContent=net?`${net.name} · ${net.mode==='nat'?'NAT: salida a la red mediante el host':net.mode}`:'No se conectará ninguna interfaz de red.';
  const uefi=$('create-firmware').value==='uefi';
  $('create-tpm').disabled=!uefi||!options.tpm;$('create-secureboot').disabled=!uefi;
  if(!uefi){$('create-tpm').checked=false;$('create-secureboot').checked=false;}
}
function read(){return {request_id:requestId,name:$('create-name').value.trim(),profile:$('create-profile').value,firmware:$('create-firmware').value,cpus:Number($('create-cpus').value),memory_mib:Number($('create-memory').value),disk_gib:Number($('create-disk').value),pool:$('create-pool').value,network:$('create-network').value,iso:$('create-iso').value,drivers_iso:$('create-drivers').value,agent:$('create-agent').checked,tpm:$('create-tpm').checked,secure_boot:$('create-secureboot').checked,autostart:$('create-autostart').checked,start:$('create-start').checked};}
function step(which){
  ['config','review','done'].forEach(name=>$('create-step-'+name).classList.toggle('active',which===name));
  $('vm-create-form').classList.toggle('hidden',which!=='config');$('create-review-panel').classList.toggle('hidden',which!=='review');$('create-success').classList.toggle('hidden',which!=='done');
}
$('vm-create-form').onsubmit=async event=>{
  event.preventDefault();if(busy)return;busy=true;error('');$('create-review').disabled=true;
  try{
    payload=read();const result=await api('preview',payload),plan=result.plan;
    const fields=[['Nombre',plan.name],['Perfil',plan.profile],['CPU',`${plan.cpus} vCPU`],['RAM',`${plan.memory_mib} MiB`],['Disco nuevo',`${plan.disk_gib} GiB · qcow2 · ${plan.disk_bus}`],['Ubicación',result.disk_path],['ISO',plan.iso||'Sin medio'],['ISO de controladores',plan.drivers_iso||'Ninguna'],['Red',plan.network?`${plan.network.name} (${plan.network.mode})`:'Sin red'],['Firmware',plan.firmware.toUpperCase()],['TPM / Secure Boot',`${plan.tpm?'Sí':'No'} / ${plan.secure_boot?'Sí':'No'}`],['Guest Agent',plan.agent?'Canal preparado':'No'],['Autoinicio',plan.autostart?'Sí':'No'],['Al finalizar',plan.start?'Encender':'Dejar apagada']];
    $('create-summary').innerHTML=fields.map(([label,value])=>`<dt>${esc(label)}</dt><dd>${esc(value)}</dd>`).join('');
    $('create-warnings').innerHTML=result.warnings.map(warning=>`<p>${esc(warning)}</p>`).join('');
    $('create-confirm-check').checked=false;$('create-submit').disabled=true;step('review');
  }catch(exc){error(exc.message);}finally{busy=false;$('create-review').disabled=false;}
};
$('create-back').onclick=()=>{if(!busy)step('config');};
$('create-confirm-check').onchange=()=>$('create-submit').disabled=!$('create-confirm-check').checked||busy;
$('create-submit').onclick=async()=>{
  if(busy||!$('create-confirm-check').checked)return;busy=true;error('');$('create-submit').disabled=true;$('create-back').disabled=true;$('create-submit').textContent='Creando…';
  try{
    const result=await api('create',{...payload,confirm:true});
    $('create-success-copy').textContent=`${result.name} se creó ${result.started?'y está encendida':'y quedó apagada'}.`;
    $('create-success-warnings').innerHTML=result.warnings.map(warning=>`<p>${esc(warning)}</p>`).join('');
    $('create-open').href='/maquinas-virtuales/'+result.id;step('done');
  }catch(exc){error(exc.message);}finally{busy=false;$('create-back').disabled=false;$('create-submit').textContent='Crear máquina virtual';$('create-submit').disabled=!$('create-confirm-check').checked;}
};
$('create-profile').onchange=()=>{
  const windows=$('create-profile').value==='windows';
  $('create-memory').value=windows?4096:2048;$('create-disk').value=windows?64:32;
  $('create-profile-help').textContent=windows?'Windows usa disco SATA y red e1000e para instalar sin exigir drivers VirtIO. El sistema operativo se instala desde VNC.':'Linux usa almacenamiento y red VirtIO. La instalación se realiza después desde VNC.';
};
['create-pool','create-network','create-firmware'].forEach(id=>$(id).onchange=help);
async function load(){
  try{
    options=await api('options');
    $('create-capacity').textContent=`Host: ${options.cpus} CPU · ${size(options.memory_total_mib*1048576)} RAM total · ${size(options.memory_available_mib*1048576)} disponible ahora`;
    $('create-memory-help').textContent=`Asignación máxima: ${options.memory_total_mib-options.reserve_mib} MiB. Al encender se verifica la RAM disponible.`;
    $('create-cpus').max=options.cpus;$('create-memory').max=options.memory_total_mib-options.reserve_mib;$('create-cpus').value=Math.min(2,options.cpus);
    $('create-pool').innerHTML=options.pools.map(pool=>`<option value="${esc(pool.id)}">${esc(pool.name)} · ${size(pool.free_bytes)} libres</option>`).join('');
    for(const id of ['create-iso','create-drivers'])$(id).insertAdjacentHTML('beforeend',options.isos.map(iso=>`<option value="${esc(iso.path)}">${esc(iso.name)} · ${size(iso.size_bytes)} · ${esc(iso.path)}</option>`).join(''));
    $('create-iso-help').textContent=options.isos.length?`${options.isos.length} ISO disponibles. Elegí la del sistema que quieras instalar.`:'No se encontraron ISO. Podés crear la VM apagada sin medio, o colocar una ISO en la biblioteca del host.';
    $('create-network').insertAdjacentHTML('beforeend',options.networks.map(net=>`<option value="${esc(net.id)}">${esc(net.name)} · ${esc(net.mode)}</option>`).join(''));
    const nat=options.networks.find(net=>net.mode==='nat');if(nat)$('create-network').value=nat.id;
    if(!options.uefi)$('create-firmware').value='bios';
    $('create-firmware').querySelector('[value=uefi]').disabled=!options.uefi;
    $('create-fields').disabled=!options.ready;help();
    if(!options.ready)throw new Error('El host todavía no ofrece almacenamiento seguro y virt-install para crear VM.');
  }catch(exc){error(exc.message);}
}
load();
fetch('/api/snapshot').then(response=>response.json()).then(data=>{if(data.system)setConnection(true,data.system.hostname,data.system.uptime_seconds);}).catch(()=>{});
})();
