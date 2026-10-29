/* Network presentation shared by the VM overview and its modal editor. */
(() => {
const {esc}=window.SHC;
const sourceNames={agent:'Guest Agent',lease:'DHCP de libvirt',arp:'ARP (caché del host)'};
const typeNames={network:'Red virtual',bridge:'Puente Linux',direct:'Red local · puente directo'};
function addressHTML(vm){
  const seen=new Set();
  const items=(vm.interfaces||[]).flatMap(net=>net.addresses||[]).filter(item=>{
    if(seen.has(item.address))return false;seen.add(item.address);return true;
  });
  return items.length?items.map(item=>`<span class="vm-ip">${esc(item.address)} <small>${esc(sourceNames[item.source]||item.source)}${item.link_local?' · enlace local':''}</small></span>`).join(''):
    `<span class="muted">${vm.state==='shut off'?'VM apagada; sin IP actual':'No detectada'}</span><small class="vm-ip-help">${vm.state==='shut off'?'Se consultará al encenderla.':'Instalá y activá QEMU Guest Agent o revisá DHCP. Una IP fija puede no aparecer sin el agente.'}</small>`;
}
function connectionLabel(net){
  return `${typeNames[net.type]||net.type} · ${net.source.network||net.source.bridge||net.source.dev||'Sin origen'}${net.type==='direct'?` (${net.source.mode||'vepa'})`:''}`;
}
function editor(vm,net,options){
  const kind=net?.type||'network';
  return `<div class="vm-network-grid">
    <label>Tipo de conexión<select name="network_type" id="vm-network-type">${Object.entries(typeNames).map(([value,label])=>`<option value="${value}" ${value===kind?'selected':''}>${label}</option>`).join('')}</select></label>
    <label>Red o interfaz del servidor<select name="source" id="vm-network-source" required></select></label>
    <p id="vm-network-help" class="vm-network-help"></p>
    <label>Modelo de placa<select name="model" id="vm-network-model">${[...new Set([net?.model||'e1000e',...options.models])].map(model=>`<option value="${esc(model)}" ${model===(net?.model||'e1000e')?'selected':''}>${esc(model)}</option>`).join('')}</select><small>VirtIO necesita controladores dentro del invitado.</small></label>
    <label>Dirección MAC<input name="mac" value="${esc(net?.mac||'')}" ${net?'required':''} maxlength="17" pattern="([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}" placeholder="Automática al agregar"><small>Conservarla evita cambiar reservas DHCP.</small></label>
    <label>Cable virtual<select name="link_state"><option value="up">Conectado</option><option value="down" ${net?.link_state==='down'?'selected':''}>Desconectado</option></select></label>
    <label>MTU<input name="mtu" id="vm-network-mtu" type="number" min="576" max="9000" value="${esc(net?.mtu||'')}" placeholder="Predeterminada"><small id="vm-network-mtu-help">Debe ser compatible con la red y el invitado.</small></label>
    <label>Colas VirtIO<input name="queues" id="vm-network-queues" type="number" min="1" max="${vm.vcpus}" value="${esc(net?.queues||'')}" placeholder="Predeterminadas"><small>Hasta ${vm.vcpus} colas; sólo para VirtIO.</small></label>
    </div><p class="vm-note">La VM tendrá una IP propia: DHCP del router en la red local o DHCP de libvirt en NAT. La IP fija, máscara, puerta de enlace y DNS se configuran dentro del sistema invitado. No reutilices la IP del servidor. Para acceder desde otras PC, habilitá el servicio y su regla de firewall dentro de la VM.</p>`;
}
function bindEditor(net,options){
  const type=document.getElementById('vm-network-type'),source=document.getElementById('vm-network-source');
  const update=()=>{
    const kind=type.value;
    const mtu=document.getElementById('vm-network-mtu');
    mtu.disabled=kind==='direct';if(mtu.disabled)mtu.value='';
    document.getElementById('vm-network-mtu-help').textContent=kind==='direct'?'El puente directo hereda la MTU de la placa física.':'Debe ser compatible con la red y el invitado.';
    const list=options[{network:'networks',bridge:'bridges',direct:'physical'}[kind]];
    const preferred=net?.type===kind?(net.source.network||net.source.bridge||net.source.dev):null;
    source.innerHTML=list.map(item=>`<option value="${esc(item.name)}" ${kind==='network'&&!item.active?'disabled':''}>${esc(item.name)} · ${kind==='network'?`${esc(item.mode)}${item.active?'':' · inactiva'}`:item.up?'Con enlace':'Sin enlace'}${kind==='bridge'&&!item.lan?' · sin puerto físico detectado':''}</option>`).join('');
    if(preferred&&list.some(item=>item.name===preferred))source.value=preferred;
    else if(preferred){const missing=document.createElement('option');missing.value=preferred;missing.textContent=`${preferred} · no disponible`;missing.disabled=true;missing.selected=true;source.append(missing);}
    else {const usable=list.find(item=>kind==='network'?item.active:item.up)||list[0];source.value=usable?.name||'';}
    if(!list.length)source.innerHTML='<option value="">No hay opciones disponibles</option>';
    document.getElementById('vm-network-help').textContent={
      network:'NAT mantiene a la VM en una subred privada. Para verla directamente desde la LAN, elegí puente directo o un puente Linux conectado a la LAN.',
      direct:'Puente directo (macvtap): conecta la VM por cable a la LAN, con su propia IP del router. Otras PC pueden acceder. El host no puede comunicarse directamente con ella por esta placa; conservá o agregá una segunda placa NAT si necesitás ese acceso. No modifica la red del servidor.',
      bridge:'Usa un puente Linux ya existente. Debe tener conexión a la LAN para recibir una IP del router. El panel no crea puentes ni mueve la IP del servidor.'
    }[kind];
  };
  type.onchange=update;update();
  const model=document.getElementById('vm-network-model'),queues=document.getElementById('vm-network-queues');
  const updateModel=()=>{queues.disabled=model.value!=='virtio';if(queues.disabled)queues.value='';};
  model.onchange=updateModel;updateModel();
}
window.SHC.vmNetwork={addressHTML,connectionLabel,editor,bindEditor,sourceNames};
})();
