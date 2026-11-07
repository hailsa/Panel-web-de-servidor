(() => {
const {$,esc,size}=window.SHC;
const urgency={high:'Alta',medium:'Media',low:'Baja',unimportant:'Sin importancia','not yet assigned':'No informada'};
const phases={'queued':'En cola',checking:'Validando', 'refreshing-indexes':'Buscando paquetes', 'checking-security':'Consultando seguridad',installing:'Instalando paquetes',scanning:'Actualizando inventario',finished:'Terminada',failed:'Falló',interrupted:'Interrumpida','launch-failed':'No se pudo iniciar'};
const states={queued:'En cola',running:'En curso',succeeded:'Completada',failed:'Fallida'};
let data=null,plan=null,busy=false,selectedJob=null,lastError='',logsBusy=false,manualLog=false;
const date=value=>value?new Date(value*1000).toLocaleString('es-AR'):'Sin consulta';
const notify=(message,error=false)=>window.SHC.notify({title:'Actualizaciones del servidor',message,severity:error?'error':'info'});
async function api(body=null){
  const response=await fetch('/api/updates',{cache:'no-store',signal:AbortSignal.timeout(105000),...(body?{method:'POST',headers:{'Content-Type':'application/json','X-SHC-Action':'confirm'},body:JSON.stringify(body)}:{})});
  const result=await response.json();if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'No se pudo consultar APT.');return result;
}
function buttons(){
  const active=!!data?.active;
  $('updates-refresh').disabled=busy||active;
  $('updates-all').disabled=busy||active||!data?.available||!data?.packages.some(row=>!row.held&&row.trusted);
  $('updates-only-security').disabled=busy||active||!data?.available||!data?.packages.some(row=>row.security&&!row.held&&row.trusted);
  $('updates-apply').disabled=busy||!plan?.changes.length||!$('updates-ack').checked||Date.now()/1000>plan.expires_at;
}
function rows(){
  if(!data)return;
  const query=$('updates-search').value.toLocaleLowerCase(),filter=$('updates-filter').value;
  const visible=data.packages.filter(row=>(filter==='all'||filter==='security'&&row.security||filter==='general'&&!row.security||filter==='held'&&row.held)&&`${row.name} ${row.summary} ${row.installed} ${row.candidate} ${row.cves.map(cve=>cve.id).join(' ')}`.toLocaleLowerCase().includes(query));
  $('updates-count').textContent=`${visible.length} de ${data.packages.length}`;
  $('updates-packages').innerHTML=visible.map(row=>`<tr><td class="updates-package"><strong>${esc(row.name)}</strong><small>${esc(row.summary)}</small>${row.held?'<span class="updates-tag">Retenido por APT</span>':''}${!row.trusted?'<span class="danger">Origen no confiable · instalación bloqueada</span>':''}</td><td class="updates-version">${esc(row.installed)}<br><span class="status">→ ${esc(row.candidate)}</span></td><td>${row.security?'<span class="status">Seguridad</span>':'General'}<small>${row.security?'Urgencia: '+esc(urgency[row.urgency]||row.urgency):'Sin clasificación de seguridad'}</small><small>${row.cves.filter(cve=>cve.fixed_by_candidate).length} CVE corregidas identificadas</small></td><td class="updates-origin">${row.origins.map(origin=>`${esc(origin.label||origin.origin)} · ${esc(origin.archive)}`).join('<br>')}</td><td>${size(row.download_bytes)}</td><td><button data-update-package="${esc(row.id)}">Ver detalle</button></td></tr>`).join('')||'<tr><td colspan="6">No hay paquetes que coincidan con el filtro.</td></tr>';
}
const knownJobs=new Map();
function render(result){
  lastError='';
  data=result;
  $('updates-total').textContent=data.available?data.total_count:'—';$('updates-security').textContent=data.available?data.security_count:'—';$('updates-high').textContent=data.available?data.high_count:'—';$('updates-os').textContent=data.os||'Anfitrión Debian';$('updates-checked').textContent=date(data.checked_at);
  const notice=[];
  if(!data.available)notice.push(data.reason);
  else notice.push(`${data.total_count} paquetes pendientes · ${data.security_count} de seguridad · ${data.held_count} retenidos.`);
  if(data.checked_at&&Date.now()/1000-data.checked_at>86400)notice.push('Los índices tienen más de 24 horas. Buscá actualizaciones antes de simular.');
  if(data.reboot?.required)notice.push(`Reinicio pendiente: ${data.reboot.reason} Kernel en uso: ${data.reboot.running_kernel}.`);
  if(data.audit)notice.push(`DPKG requiere atención: ${data.audit}`);
  if(data.tracker_error)notice.push(data.tracker_error);
  else if(!data.tracker_checked_at)notice.push('La información CVE aún no se consultó. La clasificación por repositorio puede estar disponible.');
  $('updates-notice').textContent=notice.join(' ');
  $('updates-task-state').textContent=data.active?phases[data.active.phase]||data.active.phase:'Sin tarea en curso';
  const job=data.active||data.jobs[0];
  $('updates-task-copy').textContent=job?`${job.kind==='install'?'Instalación':'Búsqueda'} · ${states[job.state]||job.state} · inicio ${date(job.created_at)}${job.error?' · '+job.error:''}`:'No hay tareas registradas.';
  data.jobs.forEach(job=>{const old=knownJobs.get(job.id);if(old&&old!==job.state&&['succeeded','failed'].includes(job.state))notify(`${job.kind==='install'?'Instalación':'Búsqueda'} ${job.state==='succeeded'?'completada':`fallida: ${job.error||'revisá el registro'}`}`,job.state==='failed');knownJobs.set(job.id,job.state);});
  $('updates-jobs').innerHTML=data.jobs.map(job=>`<div class="row"><span>${job.kind==='install'?'Instalación '+(job.scope==='security'?'de seguridad':'general'):'Búsqueda'} · ${esc(date(job.created_at))} · ${esc(states[job.state]||job.state)}</span><button data-update-job="${esc(job.id)}">Ver registro</button></div>`).join('')||'<p class="muted">Sin historial.</p>';
  if(data.active&&(!manualLog||!selectedJob||!data.jobs.some(item=>item.id===selectedJob)))selectedJob=data.active.id;
  if(!selectedJob&&job)selectedJob=job.id;
  rows();buttons();if(selectedJob)loadLogs();
}
async function loadLogs(){if(!selectedJob||logsBusy)return;logsBusy=true;const jobId=selectedJob;const job=data?.jobs.find(item=>item.id===jobId);$('updates-log-label').textContent=`Registro seleccionado: ${job?date(job.created_at):jobId}`;try{const result=await api({action:'logs',job_id:jobId});if(selectedJob===jobId)$('updates-log').textContent=result.text;}catch(error){if(selectedJob===jobId)$('updates-log').textContent=error.message;}finally{logsBusy=false;}}
const live=window.SHC.createLiveRefresh({load:()=>api(),render,onError:error=>{if(lastError!==error.message)notify(error.message,true);lastError=error.message;},blocked:()=>document.hidden||$('updates-dialog').open,interval:4000});
function openDialog(title,html){$('updates-dialog-title').textContent=title;$('updates-dialog-body').innerHTML=html;$('updates-plan-confirm').classList.add('hidden');$('updates-dialog').showModal();}
function detail(id){
  const row=data.packages.find(item=>item.id===id);if(!row)return;
  plan=null;
  openDialog(row.name,`<dl><dt>Instalada</dt><dd>${esc(row.installed)}</dd><dt>Disponible</dt><dd>${esc(row.candidate)}</dd><dt>Arquitectura</dt><dd>${esc(row.architecture)}</dd><dt>Paquete fuente</dt><dd>${esc(row.source_package)}</dd><dt>Sección / prioridad APT</dt><dd>${esc(row.section)} · ${esc(row.priority)}</dd><dt>Seguridad</dt><dd>${row.security?'Sí':'No identificada'}</dd><dt>Urgencia Debian</dt><dd>${esc(urgency[row.urgency]||row.urgency)}</dd><dt>Origen de seguridad</dt><dd>${row.security_origin?'Repositorio Debian Security':'Según CVE / repositorio general'}</dd></dl><p class="updates-description">${esc(row.description)}</p><h3>Repositorios de la versión candidata</h3><p>${row.origins.map(origin=>`${esc(origin.origin)} · ${esc(origin.label)} · ${esc(origin.archive)} / ${esc(origin.component)} · ${esc(origin.site)} · ${origin.trusted?'Autenticado':'No confiable'}`).join('<br>')}</p><h3>Vulnerabilidades relacionadas</h3>${row.cves.length?row.cves.map(cve=>`<article class="updates-cve"><a href="https://security-tracker.debian.org/tracker/${encodeURIComponent(cve.id)}" target="_blank" rel="noopener noreferrer">${esc(cve.id)}</a> · urgencia ${esc(urgency[cve.urgency]||cve.urgency)} · ${cve.fixed_by_candidate?'corregida por la versión disponible':'sin corrección confirmada en la versión disponible'}<p>${esc(cve.description)}</p><small>Versión corregida: ${esc(cve.fixed_version||'No publicada')} · alcance ${esc(cve.scope)}</small></article>`).join(''):'<p class="muted">No hay CVE verificadas para mostrar. Esto no garantiza que el paquete esté libre de vulnerabilidades.</p>'}<p><a href="https://security-tracker.debian.org/tracker/source-package/${encodeURIComponent(row.source_package)}" target="_blank" rel="noopener noreferrer">Ficha del paquete fuente en Debian Security Tracker</a></p><button id="updates-changelog">Consultar historial de cambios</button><pre id="updates-changelog-text" class="docker-logs hidden"></pre>`);
  $('updates-changelog').onclick=async()=>{const button=$('updates-changelog');button.disabled=true;const box=$('updates-changelog-text');box.classList.remove('hidden');box.textContent='Consultando changelog…';try{box.textContent=(await api({action:'changelog',package:id})).text;}catch(error){box.textContent=error.message;}finally{button.disabled=false;}};
}
async function preview(scope){
  busy=true;buttons();
  try{
    plan=await api({action:'preview',scope});
    const dependencies=plan.changes.filter(row=>row.dependency).length;
    openDialog(scope==='security'?'Revisar actualizaciones de seguridad':'Revisar todas las actualizaciones',`<div class="updates-notice">${plan.changes.length} cambios · descarga ${size(plan.download_bytes)} · espacio adicional ${size(Math.max(0,plan.additional_space_bytes))} · ${dependencies} dependencias. El plan vence ${esc(date(plan.expires_at))}.</div><p>${plan.potential_services.length?'Posibles interrupciones o reinicios: '+esc(plan.potential_services.join(', '))+'.':'Los paquetes pueden ejecutar acciones de mantenimiento y reiniciar servicios.'} ${plan.kernel_update?'Se instalarán componentes de kernel; puede ser necesario reiniciar el host.':''} SHC no reinicia el servidor automáticamente.</p><p>Se respalda configuración y lista de paquetes en el servidor; los discos de VM, volúmenes y datos requieren tu propia copia. Las configuraciones modificadas se conservan cuando DPKG pide una decisión.</p><div class="table-wrap"><table><thead><tr><th>Paquete</th><th>Antes</th><th>Después</th><th>Motivo</th></tr></thead><tbody>${plan.changes.map(row=>`<tr><td>${esc(row.id)}</td><td>${esc(row.installed||'No instalado')}</td><td>${esc(row.candidate)}</td><td>${row.dependency?'Dependencia necesaria':row.security?'Seguridad':'General'}${row.new_install?' · nuevo':''}</td></tr>`).join('')||'<tr><td colspan="4">No hay cambios aplicables.</td></tr>'}</tbody></table></div><p class="muted">Retenidos que no se instalarán: ${esc(plan.held_packages.join(', ')||'Ninguno')}.</p><details><summary>Salida de la simulación de APT</summary><pre class="docker-logs">${esc(plan.simulation||'Sin cambios')}</pre></details>`);
    $('updates-ack').checked=false;$('updates-plan-confirm').classList.toggle('hidden',!plan.changes.length);
  }catch(error){notify(error.message,true);}finally{busy=false;buttons();}
}
$('updates-refresh').onclick=async()=>{busy=true;buttons();live.pause();try{const result=await api({action:'refresh',confirm:true});selectedJob=result.job_id;manualLog=false;notify('Búsqueda iniciada. Se consultarán índices de paquetes y datos de seguridad; no se instalará nada.');}catch(error){notify(error.message,true);}finally{busy=false;await live.resume();buttons();}};
$('updates-all').onclick=()=>preview('all');$('updates-only-security').onclick=()=>preview('security');
$('updates-close').onclick=()=>$('updates-dialog').close();$('updates-ack').onchange=buttons;
$('updates-apply').onclick=async()=>{
  if(busy||!plan||!$('updates-ack').checked)return;
  busy=true;buttons();live.pause();
  try{const result=await api({action:'apply',plan_id:plan.id,confirm:true,acknowledge:true});selectedJob=result.job_id;manualLog=false;$('updates-dialog').close();notify('Instalación iniciada. La tarea continuará aunque cierres esta página.');plan=null;}
  catch(error){notify(error.message,true);}finally{busy=false;await live.resume();buttons();}
};
$('updates-search').oninput=rows;$('updates-filter').onchange=rows;
document.addEventListener('click',event=>{const pkg=event.target.closest('[data-update-package]');if(pkg)detail(pkg.dataset.updatePackage);const job=event.target.closest('[data-update-job]');if(job){selectedJob=job.dataset.updateJob;manualLog=true;loadLogs();}});
$('updates-dialog').addEventListener('close',()=>live.request());
document.addEventListener('visibilitychange',()=>{if(!document.hidden)live.request();});window.addEventListener('beforeunload',()=>live.stop());live.request();
})();
