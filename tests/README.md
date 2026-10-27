# Pruebas

`test_logout.py` comprueba que el formulario de salida funciona sin encabezado `Origin`, revoca la sesión y rechaza solicitudes sin token CSRF.

`terminal-layout.test.js` comprueba apertura, movimiento, cambio de tamaño y ampliación tanto en escritorio como en una pantalla de teléfono. Ejecutar con `node tests/terminal-layout.test.js`.

`test_collector_terminal.py` comprueba doce sesiones sucesivas y tres simultáneas contra el collector real, y que cada una recibe salida. En el servidor: `cd /opt/shc-monitor/collector && .venv/bin/python -m unittest discover -s /opt/shc-monitor/tests -p test_collector_terminal.py`.

En el servidor, después de construir la imagen del dashboard:

```bash
docker run --rm --network none -e PYTHONPATH=/app -v "$PWD/tests:/tests:ro" shc-monitor-dashboard python /tests/test_logout.py
```

Quedan pendientes las pruebas de normalización de fuentes ausentes, filtrado de sensores inválidos, deduplicación de alertas, retención de métricas y contratos API.

