# Arquitectura de SHC

## Objetivos

SHC separa la adquisición privilegiada de datos del servidor de la aplicación web. La separación limita el impacto de una vulnerabilidad en el dashboard y permite que el contenedor funcione sin privilegios.

## Componentes

### Collector local

El collector será un servicio Python pequeño, administrado por systemd. Expondrá una API HTTP únicamente sobre `/run/shc-monitor/collector.sock` y autenticará cada petición con un token leído desde `/etc/shc-monitor/collector-token`.

Los módulos de adquisición fallarán de manera independiente. Una fuente ausente devolverá `available: false` y un motivo corto, sin impedir que el resto de la API responda.

Responsabilidades previstas:

- CPU, memoria, uptime, sistema operativo y hardware.
- Interfaces, direcciones, tráfico, errores y drops.
- Procesos, usuarios y sockets en escucha.
- Filesystems y discos físicos.
- Sensores hwmon/lm-sensors y SMART.
- Estado informativo de Docker.
- RAID MD y libvirt cuando estén disponibles.

### Dashboard

El dashboard se ejecutará en un único contenedor no privilegiado. Consultará el socket Unix del collector mediante un transporte HTTP para UDS. Será responsable de:

- Login y sesiones.
- API consumida por el navegador.
- Renderizado Jinja2 y recursos estáticos locales.
- Historial de métricas y retención.
- Persistencia, deduplicación y resolución de alertas.
- Aplicación de umbrales configurables.

El contenedor tendrá acceso de sólo lectura al directorio del socket y al archivo de configuración. Sólo su volumen de datos SQLite será escribible.

### Apache

Apache terminará TLS y enviará las peticiones a `127.0.0.1:8085`. Se creará un VirtualHost específico para SHC; el sitio predeterminado actual se conservará hasta validar el nuevo sitio.

El acceso debe limitarse a las redes privadas autorizadas. Los CIDR y nombres concretos se definen únicamente en la configuración local, nunca en el repositorio.

## Contrato del collector

La API se versionará bajo `/v1`. Endpoints planeados:

```text
GET /health
GET /v1/system
GET /v1/cpu
GET /v1/memory
GET /v1/network
GET /v1/processes
GET /v1/filesystems
GET /v1/disks
GET /v1/smart
GET /v1/raid
GET /v1/docker
GET /v1/virtual-machines
GET /v1/ports
GET /v1/users
GET /v1/sensors
```

Excepto `/health`, cada endpoint exigirá `Authorization: Bearer <token>`. Las respuestas incluirán `available`, `collected_at`, `data` y, cuando corresponda, `reason`.

## Datos y retención

Una base SQLite en `/var/lib/shc-monitor/shc.db` contendrá usuarios del panel, métricas, alertas y ajustes internos. Se habilitará WAL y una tarea de mantenimiento eliminará muestras vencidas. Los eventos se deduplicarán por `source + event_type + resource`.

## Secuencia de despliegue

1. Implementar y probar collector sin instalarlo.
2. Implementar y probar dashboard localmente.
3. Construir la imagen y probar Compose aislado.
4. Crear configuración y token en el host.
5. Instalar el collector y validar el socket.
6. Levantar el dashboard ligado a localhost.
7. Crear y validar el VirtualHost Apache con backups.
8. Habilitar HTTPS y probar por ZeroTier.
9. Aplicar hardening final y documentar recuperación.
