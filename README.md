# SHC — Monitor de Servidor

SHC es un panel de bajo consumo para supervisar un servidor Debian doméstico. La interfaz mantiene su identidad visual oscura/cyber y limita las acciones administrativas a controles explícitos y protegidos de apagado y reinicio.

## Estado del proyecto · v0.4.0

La versión actual está pensada para publicarse mediante Apache en una URL interna como `https://monitor.example.internal/`. Incluye autenticación HTTP, métricas reales con actualización cada dos segundos, gráficos y sparklines, Top 5 de procesos, inventario de usuarios, estado detallado de hardware, discos, RAID, sensores, servicios y contenedores, collector por socket Unix, Docker aislado, HTTPS, alertas operativas y controles protegidos de energía.

El certificado debe incluir como SAN el hostname o las direcciones privadas elegidas durante el despliegue. Con un certificado autofirmado, el navegador mostrará una advertencia hasta confiar en la CA local correspondiente.

## Arquitectura elegida

```text
Cliente por LAN o red privada superpuesta
        |
        v
Apache HTTPS :443
        |
        v
127.0.0.1:8085
Dashboard en Docker (sin privileged)
        |
        v
/run/shc-monitor/collector.sock
Collector local administrado por systemd
        |
        +-- /proc y /sys
        +-- sensores y SMART
        +-- Docker y puertos
        +-- usuarios y procesos
        `-- RAID y virtualización cuando existan
```

El collector será la única pieza que inspeccione el host. El dashboard no recibirá acceso directo a dispositivos, al socket de Docker ni a los pseudo-filesystems del host.

## Tecnología

- Collector: Python, FastAPI/Uvicorn sobre socket Unix.
- Dashboard: Python, FastAPI, Jinja2 y JavaScript ligero.
- Gráficos: Chart.js servido localmente, sin CDN.
- Persistencia: SQLite para métricas, alertas y configuración de la aplicación.
- Despliegue: Docker Compose para el dashboard y systemd para el collector.
- Entrada web: Apache como reverse proxy HTTPS.

## Directorios

```text
apache/       Plantillas de configuración Apache
collector/    Collector que se ejecutará en Debian
config/       Esquema y ejemplo de configuración
dashboard/    API, persistencia y frontend del monitor
docs/         Arquitectura, seguridad y auditoría
scripts/      Instalación, backup, healthcheck y desinstalación
systemd/      Unidad del collector
tests/        Pruebas automatizadas
```

## Seguridad prevista

- Sin contenedores privilegiados.
- Dashboard publicado únicamente en `127.0.0.1:8085`.
- Collector accesible exclusivamente mediante socket Unix.
- Token interno generado durante la instalación y fuera del repositorio.
- Autenticación HTTP Basic gestionada por Apache con bcrypt y credenciales fuera del repositorio.
- Cookies `Secure`, `HttpOnly` y `SameSite=Strict`.
- Backups con timestamp antes de modificar Apache, systemd o certificados.
- Sin telemetría, analítica o dependencias web permanentes.

## Documentación

- [Arquitectura](docs/architecture.md)
- [Modelo de seguridad](docs/security.md)
- [Auditoría inicial](docs/audit-2026-09-12.md)
- [Despliegue seguro](docs/deployment.md)
- [Proceso de versiones](docs/releases/README.md)

## Operación actual

```bash
sudo systemctl status shc-collector
sudo journalctl -u shc-collector -f
cd /opt/shc-monitor && sudo docker compose ps
sudo docker logs -f shc-monitor
sudo apache2ctl configtest
```

Para cambiar la contraseña web de forma interactiva:

```bash
sudo htpasswd -B /etc/shc-monitor/htpasswd USUARIO
```
