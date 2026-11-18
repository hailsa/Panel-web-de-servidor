/* Uses the existing two-second host polling on every authenticated page. */
(() => {
  const box = document.getElementById('host-network');
  if (!box) return;
  window.SHC.updateHostNetwork = data => {
    const connection = data?.network?.connection;
    const type = connection?.type;
    const wifi = type === 'wifi', ethernet = type === 'ethernet';
    const bars = wifi && Number.isInteger(connection.signal_bars) ? Math.min(3, Math.max(0, connection.signal_bars)) : null;
    const label = wifi ? 'Wi-Fi' : ethernet ? 'ETH' : type === 'disconnected' ? 'Sin red' : type === 'other' ? 'Red' : '—';
    let description = wifi ? 'Servidor conectado por Wi-Fi' : ethernet ? 'Servidor conectado por Ethernet' : type === 'disconnected' ? 'Servidor sin ruta de salida' : type === 'other' ? 'Servidor usando otra interfaz de red' : 'Conexión del servidor: sin datos actuales';
    if (connection?.interface) description += ` · ${connection.interface}`;
    if (wifi) description += bars === null ? ' · Señal no disponible' : ` · Señal ${bars}/3 · ${connection.signal_dbm} dBm · ${connection.signal_percent}% estimado`;
    box.classList.toggle('network-is-wifi', wifi);
    box.classList.toggle('network-is-ethernet', ethernet);
    box.classList.toggle('network-unknown', !wifi && !ethernet);
    box.dataset.bars = bars === null ? 'unknown' : String(bars);
    document.getElementById('host-network-label').textContent = label;
    box.title = description;
    box.setAttribute('aria-label', description);
  };
})();
