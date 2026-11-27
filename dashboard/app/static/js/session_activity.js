(() => {
  async function session(activity = false) {
    try {
      const response = await fetch(activity ? '/api/session/activity' : '/api/session/status', {
        cache: 'no-store',
        ...(activity ? {method: 'POST', headers: {'X-SHC-Action': 'confirm'}} : {})
      });
      if (response.status === 401) location.replace('/login');
    } catch (_) { /* A transient network failure does not log the user out. */ }
  }
  let last = 0;
  function record(event) {
    if (!event.isTrusted || document.hidden || Date.now() - last < 2000) return;
    last = Date.now();
    session(true);
  }
  for (const name of ['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart']) {
    addEventListener(name, record, {capture: true, passive: true});
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) session(); });
  setInterval(session, 2000);
})();
