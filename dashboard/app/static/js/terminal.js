(() => {
  const button = document.getElementById('terminal-toggle');
  const panel = document.getElementById('terminal-panel');
  const close = document.getElementById('terminal-close');
  let terminal;
  let socket;
  const resize = () => {
    if (!terminal || !socket || socket.readyState !== WebSocket.OPEN) return;
    const target = document.getElementById('terminal-screen');
    const cols = Math.max(40, Math.floor(target.clientWidth / 8.4));
    const rows = Math.max(12, Math.floor(target.clientHeight / 17));
    terminal.resize(cols, rows);
    socket.send(JSON.stringify({type:'resize', cols, rows}));
  };
  const hide = () => {
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
    terminal = new Terminal({cursorBlink:true, convertEol:true, fontSize:13, theme:{background:'#070d10',foreground:'#e4edef'}});
    terminal.open(document.getElementById('terminal-screen'));
    terminal.write('Conectando al servidor…\r\n');
    socket = new WebSocket(`wss://${location.host}/ws/terminal`);
    socket.onopen = () => { terminal.clear(); resize(); terminal.focus(); };
    socket.onmessage = event => terminal.write(event.data);
    socket.onclose = () => { if (terminal) terminal.write('\r\n[Conexión cerrada]\r\n'); };
    terminal.onData(data => { if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({type:'input',data})); });
  });
  close.addEventListener('click', hide);
  window.addEventListener('resize', resize);
})();
