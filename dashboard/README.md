# Dashboard

La autenticación de v0.4.5 usa `/var/lib/shc-monitor/auth/auth.sqlite3`. El directorio debe ser escribible por el usuario `shc` (UID 10001) del contenedor. Importe el hash bcrypt previo de `hailsa` con `python -m app.manage_users import-hash hailsa` y cree otras cuentas con `python -m app.manage_users set-password NOMBRE`, dentro del contenedor y sin pasar contraseñas como argumentos.

Aplicación web FastAPI/Jinja2, API del navegador, autenticación, métricas históricas y alertas persistentes. Su implementación comenzará después del collector.

