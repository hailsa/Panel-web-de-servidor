(() => {
  const button = document.getElementById('terminal-toggle');
  const panel = document.getElementById('terminal-panel');
  const header = document.getElementById('terminal-header');
  const screen = document.getElementById('terminal-screen');
  const close = document.getElementById('terminal-close');
  const expand = document.getElementById('terminal-expand');
  const resizeHandle = document.getElementById('terminal-resize');
  const storageKey = 'shc-terminal-geometry-v1';
  let terminal;
  let socket;
  let maximized = false;
  let savedGeometry = null;
  let interaction = null;
  let resizeFrame = 0;

  const finite = (value, fallback) => Number.isFinite(value) ? value : fallback;
  const clamp = (value, minimum, maximum) => Math.min(Math.max(value, minimum), maximum);
  const rectOf = element => {
    const {left, top, width, height} = element.getBoundingClientRect();
    return {left, top, width, height};
  };
  const bounds = () => {
    const edge = window.innerWidth <= 720 ? 8 : 14;
    const main = document.querySelector('main');
    const topbar = document.querySelector('.topbar');
    const left = window.innerWidth <= 720 ? edge : Math.max(edge, Math.ceil(main.getBoundingClientRect().left) + edge);
    const top = Math.max(edge, Math.ceil(topbar.getBoundingClientRect().bottom) + edge);
    return {left, top, right:Math.max(left + 1, window.innerWidth - edge), bottom:Math.max(top + 1, window.innerHeight - edge)};
  };
  const fit = rectangle => {
    const area = bounds();
    const availableWidth = area.right - area.left;
    const availableHeight = area.bottom - area.top;
    const width = clamp(finite(rectangle.width, 820), Math.min(320, availableWidth), availableWidth);
    const height = clamp(finite(rectangle.height, 480), Math.min(220, availableHeight), availableHeight);
    return {
      left:clamp(finite(rectangle.left, area.left), area.left, area.right - width),
      top:clamp(finite(rectangle.top, area.top), area.top, area.bottom - height),
      width,
      height,
    };
  };
  const resizeTerminal = (force = false) => {
    if (!terminal) return;
    const cols = Math.max(30, Math.floor((screen.clientWidth - 16) / 8.4));
    const rows = Math.max(10, Math.floor((screen.clientHeight - 16) / 17));
    const changed = cols !== terminal.cols || rows !== terminal.rows;
    if (changed) terminal.resize(cols, rows);
    if (socket && socket.readyState === WebSocket.OPEN && (changed || force)) {
      socket.send(JSON.stringify({type:'resize', cols, rows}));
    }
  };
  const scheduleResize = () => {
    if (resizeFrame) return;
    resizeFrame = requestAnimationFrame(() => { resizeFrame = 0; resizeTerminal(); });
  };
  const setRect = rectangle => {
    panel.style.left = `${rectangle.left}px`;
    panel.style.top = `${rectangle.top}px`;
    panel.style.width = `${rectangle.width}px`;
    panel.style.height = `${rectangle.height}px`;
    panel.style.right = 'auto';
    panel.style.bottom = 'auto';
    scheduleResize();
  };
  const remember = () => {
    savedGeometry = rectOf(panel);
    try { localStorage.setItem(storageKey, JSON.stringify(savedGeometry)); } catch (_) { /* Storage may be disabled. */ }
  };
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey) || 'null');
    if (stored && ['left', 'top', 'width', 'height'].every(key => Number.isFinite(stored[key]))) savedGeometry = stored;
  } catch (_) { /* Ignore damaged or unavailable storage. */ }

  const setExpandLabel = () => {
    const label = maximized ? 'Restaurar tamaño de la consola' : 'Ampliar consola';
    expand.setAttribute('aria-label', label);
    expand.setAttribute('aria-pressed', String(maximized));
    expand.title = label;
  };
  const fitExpanded = () => {
    const area = bounds();
    setRect({left:area.left, top:area.top, width:area.right - area.left, height:area.bottom - area.top});
  };
  const toggleExpanded = () => {
    if (!maximized) {
      remember();
      maximized = true;
      panel.classList.add('maximized');
      fitExpanded();
    } else {
      maximized = false;
      panel.classList.remove('maximized');
      setRect(fit(savedGeometry || rectOf(panel)));
    }
    setExpandLabel();
    terminal?.focus();
  };
  const handleViewportChange = () => {
    if (panel.classList.contains('hidden')) return;
    if (maximized) fitExpanded();
    else setRect(fit(savedGeometry || rectOf(panel)));
  };

  const finishInteraction = () => {
    if (!interaction) return;
    const {target, pointerId} = interaction;
    interaction = null;
    window.removeEventListener('pointermove', moveInteraction);
    window.removeEventListener('pointerup', finishInteraction);
    window.removeEventListener('pointercancel', finishInteraction);
    if (target.hasPointerCapture(pointerId)) target.releasePointerCapture(pointerId);
    panel.classList.remove('is-moving');
    remember();
    scheduleResize();
  };
  const moveInteraction = event => {
    if (!interaction || event.pointerId !== interaction.pointerId) return;
    const {mode, startX, startY, startRect} = interaction;
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;
    const next = mode === 'move'
      ? {...startRect, left:startRect.left + dx, top:startRect.top + dy}
      : {...startRect, width:startRect.width + dx, height:startRect.height + dy};
    setRect(fit(next));
  };
  const startInteraction = (event, mode) => {
    if (maximized || event.button !== 0 || (mode === 'move' && event.target.closest('button'))) return;
    event.preventDefault();
    interaction = {mode, pointerId:event.pointerId, target:event.currentTarget, startX:event.clientX, startY:event.clientY, startRect:rectOf(panel)};
    event.currentTarget.setPointerCapture(event.pointerId);
    if (mode === 'move') panel.classList.add('is-moving');
    window.addEventListener('pointermove', moveInteraction);
    window.addEventListener('pointerup', finishInteraction);
    window.addEventListener('pointercancel', finishInteraction);
  };

  const hide = () => {
    finishInteraction();
    if (maximized) {
      maximized = false;
      panel.classList.remove('maximized');
      setExpandLabel();
    }
    panel.classList.add('hidden');
    button.setAttribute('aria-expanded', 'false');
    if (socket) socket.close();
    if (terminal) terminal.dispose();
    socket = null;
    terminal = null;
  };
  button.addEventListener('click', () => {
    if (!panel.classList.contains('hidden')) { hide(); return; }
    panel.classList.remove('hidden');
    button.setAttribute('aria-expanded', 'true');
    setRect(fit(savedGeometry || rectOf(panel)));
    terminal = new Terminal({cursorBlink:true, convertEol:true, fontSize:13, theme:{background:'#070d10',foreground:'#e4edef'}});
    terminal.open(screen);
    terminal.write('Conectando al servidor…\r\n');
    const connection = new WebSocket(`wss://${location.host}/ws/terminal`);
    socket = connection;
    connection.onopen = () => { if (socket !== connection) return; resizeTerminal(true); terminal.focus(); };
    connection.onmessage = event => { if (socket === connection && terminal) terminal.write(event.data); };
    connection.onclose = () => { if (socket === connection && terminal) terminal.write('\r\n[Conexión cerrada]\r\n'); };
    terminal.onData(data => { if (socket === connection && connection.readyState === WebSocket.OPEN) connection.send(JSON.stringify({type:'input', data})); });
  });
  close.addEventListener('click', hide);
  expand.addEventListener('click', toggleExpanded);
  header.addEventListener('pointerdown', event => startInteraction(event, 'move'));
  resizeHandle.addEventListener('pointerdown', event => startInteraction(event, 'resize'));
  window.addEventListener('resize', handleViewportChange);
  if (window.visualViewport) window.visualViewport.addEventListener('resize', handleViewportChange);
  if (window.ResizeObserver) {
    new ResizeObserver(scheduleResize).observe(screen);
    new ResizeObserver(handleViewportChange).observe(document.querySelector('main'));
  }
})();
