# Pruebas

`test_logout.py` comprueba que el formulario de salida funciona sin encabezado `Origin`, revoca la sesión y rechaza solicitudes sin token CSRF.

En el servidor, después de construir la imagen del dashboard:

```bash
docker run --rm --network none -e PYTHONPATH=/app -v "$PWD/tests:/tests:ro" shc-monitor-dashboard python /tests/test_logout.py
```

Quedan pendientes las pruebas de normalización de fuentes ausentes, filtrado de sensores inválidos, deduplicación de alertas, retención de métricas y contratos API.

