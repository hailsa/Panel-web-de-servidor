/* Single-flight polling: stale responses cannot overwrite action results. */
(() => {
function createLiveRefresh({load,render,onError=()=>{},blocked=()=>false,interval=3000}) {
  let generation=0,paused=0,running=null,queued=false,stopped=false;
  async function request(force=false) {
    if(stopped||paused||(!force&&blocked()))return false;
    if(running){queued=true;return running;}
    running=(async()=>{
      do {
        queued=false;
        const ticket=generation;
        try {const data=await load();if(!stopped&&!paused&&ticket===generation&&!blocked())render(data);}
        catch(error){if(!stopped&&!paused&&ticket===generation)onError(error);}
      } while(queued&&!stopped&&!paused);
    })();
    try {await running;}finally{running=null;}
    return true;
  }
  const timer=setInterval(()=>request(),interval);
  return {request,pause(){paused++;generation++;queued=false;},
    resume(){paused=Math.max(0,paused-1);return request(true);},
    stop(){stopped=true;generation++;clearInterval(timer);}};
}
window.SHC.createLiveRefresh=createLiveRefresh;
})();
