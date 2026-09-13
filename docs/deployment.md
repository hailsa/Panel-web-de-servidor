# Despliegue seguro

Este repositorio no contiene direcciones reales, nombres internos, credenciales, certificados, tokens ni seriales. Antes de desplegar hay que adaptar localmente los archivos de ejemplo.

## Requisitos

- Servidor Linux con Python 3, systemd, Docker y Docker Compose.
- Apache con `ssl`, `proxy`, `proxy_http` y `headers`.
- Un usuario de servicio sin acceso interactivo para el collector.
- Un hostname interno y una o más redes privadas autorizadas.

## Configuración local

1. Copiar `config/config.example.yml` como `config/config.yml` y completar los valores locales.
2. Adaptar `apache/shc-monitor.conf` con el hostname, certificado y CIDR privados.
3. Crear un token aleatorio de al menos 32 bytes en `/etc/shc-monitor/collector-token`, con permisos mínimos.
4. Crear el archivo bcrypt de Apache fuera del repositorio.
5. Ajustar el usuario y grupo de `systemd/shc-collector.service` si la cuenta local difiere de `shc-monitor`.
6. Mantener el dashboard ligado a `127.0.0.1`; Apache debe ser el único punto de entrada.

## Validación

Antes de habilitar el sitio se deben ejecutar las pruebas Python y JavaScript, `docker compose config`, `apache2ctl configtest` y los healthchecks. Toda modificación del host debe contar con un respaldo fechado y recuperable.

Los datos específicos del servidor se documentan fuera de Git o en un gestor de secretos. Los informes públicos sólo describen capacidades y resultados anonimizados.
