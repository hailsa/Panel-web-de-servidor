(() => {
const {$,esc}=window.SHC;
const priorities=['Emergencia','Alerta','Crítico','Error','Advertencia','Aviso','Información','Debug'];
let entries=[],cursor=null,activeQuery=null,queryUntil=null,loading=false,liveTimer=null;
const date=value=>new Date(Number(value)/1000);
const unitOf=entry=>entry._SYSTEMD_UNIT||entry._SYSTEMD_USER_UNIT||entry.SYSLOG_IDENTIFIER||entry._COMM||'Sistema';
function error(text){$('journal-error').textContent=text;$('journal-error').classList.toggle('hidden',!text);}
function toggleBusy(value){
  loading=value;$('journal-results').setAttribute('aria-busy',String(value));
  ['journal-apply','journal-refresh','journal-reset'].forEach(id=>$(id).disabled=value);
  $('journal-more').disabled=value||!cursor||entries.length>=2000;
}
function readQuery(){
  const query={range:$('journal-range').value,priority:Number($('journal-priority').value),unit:$('journal-unit').value.trim(),identifier:$('journal-identifier').value.trim(),boot:$('journal-boot').value,search:$('journal-search').value.trim(),kernel:$('journal-kernel').checked,limit:Number($('journal-limit').value)};
  if(query.range==='custom'){
    if(!$('journal-since').value||!$('journal-until').value)throw new Error('Elegí fecha y hora de inicio y fin.');
    query.since=new Date($('journal-since').value).toISOString();query.until=new Date($('journal-until').value).toISOString();
  }
  return query;
}
function highlight(value){
  const text=String(value||''),search=activeQuery?.search||'';
  if(!search)return esc(text);
  let start=0,html='',index=0;const lower=text.toLocaleLowerCase(),needle=search.toLocaleLowerCase();
  while((index=lower.indexOf(needle,start))!==-1){html+=esc(text.slice(start,index))+'<mark>'+esc(text.slice(index,index+search.length))+'</mark>';start=index+search.length;}
  return html+esc(text.slice(start));
}
function render(){
  let day='';
  $('journal-results').innerHTML=entries.map((entry,index)=>{
    const time=date(entry.__REALTIME_TIMESTAMP),label=time.toLocaleDateString('es-AR',{dateStyle:'full'});
    const separator=day!==label?`<h3 class="journal-day">${esc(label)}</h3>`:'';day=label;
    const priority=Number(entry.PRIORITY),level=Number.isInteger(priority)&&priority>=0&&priority<=7?priority:6;
    const fields=[['Servicio',entry._SYSTEMD_UNIT],['Servicio de usuario',entry._SYSTEMD_USER_UNIT],['Identificador',entry.SYSLOG_IDENTIFIER],['Proceso',entry._COMM],['PID',entry._PID],['UID',entry._UID],['GID',entry._GID],['Host',entry._HOSTNAME],['Arranque',entry._BOOT_ID],['Transporte',entry._TRANSPORT],['Ejecutable',entry._EXE],['Archivo / línea',[entry.CODE_FILE,entry.CODE_LINE].filter(Boolean).join(':')],['Función',entry.CODE_FUNC],['Facility syslog',entry.SYSLOG_FACILITY],['Cursor',entry.__CURSOR]].filter(([,value])=>value);
    return `${separator}<details class="journal-entry journal-level-${level}" data-entry="${index}"><summary><time>${esc(time.toLocaleTimeString('es-AR',{hour12:false}))}</time><span class="journal-level">${priorities[level]}</span><span class="journal-source" title="${esc(unitOf(entry))}">${esc(unitOf(entry))}</span><span class="journal-message">${highlight(entry.MESSAGE)}</span></summary><div class="journal-event-detail"><div class="journal-event-top"><strong>${esc(time.toLocaleString('es-AR'))}</strong><button type="button" data-copy-event="${index}">Copiar evento</button></div><pre>${highlight(entry.MESSAGE)}</pre><dl>${fields.map(([key,value])=>`<dt>${esc(key)}</dt><dd>${esc(value)}</dd>`).join('')}</dl></div></details>`;
  }).join('')||'<p class="empty">No hay coincidencias en esta página. Podés ajustar los filtros o continuar con registros anteriores.</p>';
  const errors=entries.filter(entry=>Number(entry.PRIORITY)<=3).length,warnings=entries.filter(entry=>Number(entry.PRIORITY)===4).length;
  $('journal-summary').textContent=`${entries.length} eventos cargados · ${errors} errores/críticos · ${warnings} advertencias`;
  $('journal-export-text').disabled=!entries.length;$('journal-export-json').disabled=!entries.length;
}
async function query(append=false){
  if(loading)return;
  try{
    if(!append){activeQuery=readQuery();cursor=null;queryUntil=null;}
    const payload={...activeQuery};
    if(append){payload.cursor=cursor;payload.until=queryUntil;}
    toggleBusy(true);error('');
    const response=await fetch('/api/journal/query',{method:'POST',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const result=await response.json();
    if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'El journal no está disponible');
    const prior=append?entries:[],known=new Set(prior.map(entry=>entry.__CURSOR));
    entries=prior.concat(result.entries.filter(entry=>!known.has(entry.__CURSOR))).slice(0,2000);
    cursor=result.next_cursor;queryUntil=result.until;
    $('journal-notice').textContent=(result.notice||'')+(entries.length>=2000?' Se alcanzó el límite de 2000 eventos cargados; afiná los filtros para continuar.':'');
    $('journal-query-caption').textContent=`Consulta hasta ${new Date(queryUntil).toLocaleString('es-AR')} · ${result.scanned} eventos revisados en la última página`;
    render();
  }catch(exc){error(exc.message);}finally{toggleBusy(false);}
}
function exportData(format){
  const text=format==='json'?JSON.stringify({query:activeQuery,until:queryUntil,exported_at:new Date().toISOString(),entries},null,2):entries.map(entry=>`${date(entry.__REALTIME_TIMESTAMP).toISOString()} [${priorities[Number(entry.PRIORITY)]||entry.PRIORITY}] ${unitOf(entry)}${entry._PID?'['+entry._PID+']':''}: ${entry.MESSAGE}`).join('\n');
  const blob=new Blob([text],{type:format==='json'?'application/json':'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=url;link.download=`shc-registros-${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.${format}`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
$('journal-filters').onsubmit=event=>{event.preventDefault();query();};
$('journal-refresh').onclick=()=>query();$('journal-more').onclick=()=>query(true);
$('journal-export-text').onclick=()=>exportData('txt');$('journal-export-json').onclick=()=>exportData('json');
$('journal-range').onchange=()=>document.querySelectorAll('.journal-custom').forEach(node=>node.classList.toggle('hidden',$('journal-range').value!=='custom'));
$('journal-reset').onclick=()=>{$('journal-filters').reset();$('journal-range').onchange();query();};
$('journal-live').onchange=()=>{
  clearInterval(liveTimer);
  if($('journal-live').checked)liveTimer=setInterval(()=>{if(!document.hidden&&!document.querySelector('.journal-entry[open]'))query();},10000);
};
document.querySelectorAll('[data-journal-preset]').forEach(button=>button.onclick=()=>{
  if(loading)return;
  $('journal-filters').reset();$('journal-range').onchange();
  const preset=button.dataset.journalPreset;
  const units={ssh:'ssh.service',docker:'docker.service',apache:'apache2.service',libvirt:'libvirtd.service',collector:'shc-collector.service'};
  if(preset==='errors')$('journal-priority').value='3';
  else if(preset==='kernel')$('journal-kernel').checked=true;
  else $('journal-unit').value=units[preset]||'';
  query();
});
$('journal-results').addEventListener('click',async event=>{
  const button=event.target.closest('[data-copy-event]');if(!button)return;
  try{await navigator.clipboard.writeText(JSON.stringify(entries[Number(button.dataset.copyEvent)],null,2));button.textContent='Copiado';}
  catch(_){error('El navegador no permitió copiar. Podés seleccionar el mensaje o exportar la consulta.');}
});
async function metadata(){
  try{
    const response=await fetch('/api/journal/metadata',{cache:'no-store'}),data=await response.json();
    if(!response.ok)throw new Error(data.detail||'No se pudieron consultar las fuentes');
    $('journal-storage').textContent=data.storage;
    $('journal-units').innerHTML=data.units.map(unit=>`<option value="${esc(unit)}"></option>`).join('');
    $('journal-identifiers').innerHTML=data.identifiers.map(identifier=>`<option value="${esc(identifier)}"></option>`).join('');
    $('journal-boot').innerHTML='<option value="">Todos los arranques</option><option value="0">Arranque actual</option><option value="-1">Arranque anterior</option>'+data.boots.map(boot=>`<option value="${esc(boot.boot_id)}">${boot.index===0?'Actual':boot.index} · ${date(boot.first_entry).toLocaleString('es-AR')}</option>`).join('');
  }catch(exc){$('journal-storage').textContent='Fuentes no disponibles';error(exc.message);}
}
metadata();query();
})();
