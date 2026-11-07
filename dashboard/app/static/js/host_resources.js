/* Host totals stay visible while managing guests, containers or other pages. */
(() => {
const {$,size,setConnection}=window.SHC;
const container=$('host-resources');
if(!container)return;
function update(data){
  for(const [key,label,value] of [['cpu','CPU',data?.cpu?.percent],['ram','RAM',data?.memory?.percent]]){
    const available=typeof value==='number'&&Number.isFinite(value);
    const percent=available?Math.min(100,Math.max(0,value)):null;
    const text=available?`${percent.toFixed(1)}%`:'—';
    $(`host-${key}-value`).textContent=text;
    $(`host-${key}-bar`).style.width=available?`${percent}%`:'0%';
    const metric=$(`host-${key}-metric`);
    const memory=key==='ram'&&available&&Number.isFinite(data?.memory?.used)&&Number.isFinite(data?.memory?.total)?` · ${size(data.memory.used)} / ${size(data.memory.total)}`:'';
    metric.title=available?`${label} del servidor: ${text}${memory}`:`${label} del servidor: sin datos actuales`;
    metric.setAttribute('aria-label',metric.title);
    metric.classList.toggle('resource-unavailable',!available);
  }
}
window.SHC.updateHostResources=update;
const live=window.SHC.createLiveRefresh({
  load:async()=>{const response=await fetch('/api/snapshot',{cache:'no-store',signal:AbortSignal.timeout(8000)});if(!response.ok)throw new Error('Sin métricas');return response.json();},
  render:data=>{update(data);if(data.system)setConnection(true,data.system.hostname,data.system.uptime_seconds);},
  onError:()=>update(null),blocked:()=>document.hidden,interval:2000
});
live.request();
document.addEventListener('visibilitychange',()=>{if(!document.hidden)live.request();});
window.addEventListener('beforeunload',()=>live.stop());
})();
