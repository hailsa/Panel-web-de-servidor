const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function element(initial = {}) {
  const listeners = new Map();
  const classes = new Set(initial.hidden ? ['hidden'] : []);
  const attributes = new Map();
  const captured = new Set();
  return {
    style: {},
    classList: {
      add: name => classes.add(name),
      remove: name => classes.delete(name),
      contains: name => classes.has(name),
    },
    addEventListener(name, listener) { listeners.set(name, listener); },
    dispatch(name, event = {}) {
      listeners.get(name)?.({button: 0, pointerId: 1, clientX: 0, clientY: 0,
        preventDefault() {}, target: this, currentTarget: this, ...event});
    },
    setAttribute(name, value) { attributes.set(name, value); },
    getAttribute(name) { return attributes.get(name); },
    setPointerCapture(id) { captured.add(id); },
    hasPointerCapture(id) { return captured.has(id); },
    releasePointerCapture(id) { captured.delete(id); },
    closest() { return null; },
    getBoundingClientRect() {
      const rect = Object.fromEntries(['left', 'top', 'width', 'height'].map(key =>
        [key, this.style[key] ? parseFloat(this.style[key]) : (initial[key] || 0)]));
      return {...rect, right:rect.left + rect.width, bottom:rect.top + rect.height};
    },
  };
}

const nodes = {
  'terminal-toggle': element(),
  'terminal-panel': element({hidden:true, left:1060, top:360, width:820, height:480}),
  'terminal-header': element(),
  'terminal-screen': element(),
  'terminal-close': element(),
  'terminal-expand': element(),
  'terminal-resize': element(),
};
const panel = nodes['terminal-panel'];
const main = element({left:210});
const topbar = element({top:0, height:58});
const windowListeners = new Map();
const frames = [];
const storage = new Map();
const sockets = [];
const screen = nodes['terminal-screen'];
Object.defineProperty(screen, 'clientWidth', {get: () => panel.getBoundingClientRect().width - 16});
Object.defineProperty(screen, 'clientHeight', {get: () => panel.getBoundingClientRect().height - 42});
class FakeTerminal {
  constructor() { this.cols = 80; this.rows = 24; }
  open() {}
  write() {}
  clear() {}
  focus() {}
  dispose() {}
  onData() {}
  resize(cols, rows) { this.cols = cols; this.rows = rows; }
}
class FakeWebSocket {
  static OPEN = 1;
  constructor() { this.readyState = 0; this.sent = []; sockets.push(this); }
  send(data) { this.sent.push(JSON.parse(data)); }
  close() { this.readyState = 3; }
}
const viewport = {
  innerWidth: 1920,
  innerHeight: 1080,
  addEventListener(name, listener) { windowListeners.set(name, listener); },
  removeEventListener(name) { windowListeners.delete(name); },
  dispatch(name, event = {}) { windowListeners.get(name)?.(event); },
};
const context = {
  document: {
    getElementById: id => nodes[id],
    querySelector: selector => selector === 'main' ? main : topbar,
  },
  window: viewport,
  location: {host:'example.test'},
  Terminal: FakeTerminal,
  WebSocket: FakeWebSocket,
  localStorage: {
    getItem: key => storage.get(key) || null,
    setItem: (key, value) => storage.set(key, value),
  },
  requestAnimationFrame(callback) { frames.push(callback); return frames.length; },
};
const source = fs.readFileSync(path.join(__dirname, '../dashboard/app/static/js/terminal.js'), 'utf8');
vm.runInNewContext(source, context);

nodes['terminal-toggle'].dispatch('click');
assert.equal(panel.classList.contains('hidden'), false);
assert.ok(parseFloat(panel.style.top) >= 72);
assert.ok(parseFloat(panel.style.left) >= 224);
sockets[0].readyState = FakeWebSocket.OPEN;
sockets[0].onopen();
assert.ok(sockets[0].sent.some(message => message.type === 'resize'));

nodes['terminal-expand'].dispatch('click');
assert.equal(nodes['terminal-expand'].getAttribute('aria-pressed'), 'true');
assert.equal(parseFloat(panel.style.top), 72);
assert.equal(parseFloat(panel.style.left), 224);
assert.equal(parseFloat(panel.style.height), 994);
nodes['terminal-expand'].dispatch('click');
assert.equal(nodes['terminal-expand'].getAttribute('aria-pressed'), 'false');
assert.equal(parseFloat(panel.style.width), 820);

nodes['terminal-header'].dispatch('pointerdown', {clientX:1000, clientY:380});
viewport.dispatch('pointermove', {pointerId:1, clientX:-1000, clientY:-1000});
viewport.dispatch('pointerup', {pointerId:1});
assert.equal(parseFloat(panel.style.left), 224);
assert.equal(parseFloat(panel.style.top), 72);
assert.ok(storage.has('shc-terminal-geometry-v1'));

nodes['terminal-resize'].dispatch('pointerdown', {clientX:1000, clientY:500});
viewport.dispatch('pointermove', {pointerId:1, clientX:3000, clientY:3000});
viewport.dispatch('pointerup', {pointerId:1});
assert.equal(parseFloat(panel.style.width), 1682);
assert.equal(parseFloat(panel.style.height), 994);

viewport.innerWidth = 390;
viewport.innerHeight = 844;
main.style.left = '0px';
viewport.dispatch('resize');
nodes['terminal-expand'].dispatch('click');
assert.equal(parseFloat(panel.style.top), 66);
assert.equal(parseFloat(panel.style.left), 8);
assert.equal(parseFloat(panel.style.width), 374);
assert.equal(parseFloat(panel.style.height), 770);

while (frames.length) frames.shift()();
console.log('Terminal layout: desktop, drag, resize and mobile expand OK');
