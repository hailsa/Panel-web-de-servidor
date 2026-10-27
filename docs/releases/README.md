# Gestión de versiones

SHC utiliza versionado semántico y tags anotados de Git.

- `v0.1.0`: primera versión operativa del dashboard.
- `v0.2.0`: navegación, inventario de usuarios y estado detallado del servidor.
- `v0.3.0`: gráficos, Top 5 de procesos, iconografía SVG y reorganización visual.
- `v0.4.0`: energía segura, notificaciones operativas, navegación adaptable y corrección del uptime.
- `v0.4.5`: página de acceso, sesiones locales, consola integrada y reparación de las acciones de energía.
- `v0.4.6`: login centrado y renovado; cierre de sesión fiable con protección CSRF e invalidación de la sesión.
- `v0.4.7`: consola movible, redimensionable y ampliable sin cubrir la barra superior.
- `v0.4.8`: corrige la consola vacía al conectar y verifica su apertura en todas las páginas del panel.
- `v0.4.9`: corrige la lectura y limpieza de sesiones de terminal; evita la espera infinita en la interfaz.
- `v0.4.10`: detección real de KVM/libvirt.
- `v0.5.0`: gestión de máquinas virtuales y consola VNC.
- `v0.5.1`: identificación de servicios en los puertos abiertos.
- `v0.6.0`: pestaña Docker y menú de acciones de VM sin recortes.
- `v0.6.1`: imágenes Docker ordenadas por uso y selector para imágenes sin etiqueta.

Para cada nueva versión:

1. Crear una rama `codex/vX.Y.Z` desde `main`.
2. Implementar y validar sin incorporar secretos ni configuración local.
3. Actualizar las notas de la versión en este directorio.
4. Crear un commit de release y el tag anotado `vX.Y.Z`.
5. Subir `main`, la rama de versión y los tags a GitHub.
6. Desplegar sólo después de crear un respaldo recuperable de la versión anterior.
