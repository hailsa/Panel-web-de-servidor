# Actualizaciones del anfitrión

Esta función administra paquetes APT del servidor Debian de la misma distribución configurada. Incluye kernel, firmware y bibliotecas cuando se distribuyen como paquetes. No actualiza automáticamente imágenes Docker, aplicaciones internas de contenedores, software instalado manualmente ni sistemas operativos invitados.

## Consultar y revisar

La pestaña muestra paquete, descripción, arquitectura, versión instalada/candidata, repositorios, confianza del origen, descarga y retención de APT. El detalle incluye la descripción completa, prioridad de empaquetado, avisos CVE y changelog consultable. La prioridad APT no equivale a gravedad de seguridad.

Se clasifica como seguridad una versión de un repositorio autenticado Debian Security o una candidata oficial que corrige una CVE aplicable según las versiones fuente de Debian. El panel conserva la urgencia publicada (alta, media, baja, sin importancia o no informada). No deduce CVSS a partir de palabras del changelog ni considera corregida una CVE si la candidata aún no alcanza su versión corregida.

El Security Tracker puede describir vulnerabilidades todavía sin parche: se distinguen de las corregidas por la candidata. La ausencia de avisos en el detalle no certifica que un paquete esté libre de vulnerabilidades. El feed se recibe por HTTPS, se procesa por registros acotados y se guardan sólo los datos relevantes. Si no puede consultarse, el panel conserva el último conjunto disponible y muestra el error; la clasificación por repositorio sigue funcionando.

«Buscar actualizaciones» ejecuta `apt-get update` y consulta el tracker. No instala paquetes. Un timer hace esa búsqueda cada seis horas con un pequeño retraso aleatorio. Puede coincidir con apt-daily u otro gestor: si APT está ocupado, se informa el error y se conserva el último inventario correcto. Las búsquedas importantes aparecen en el centro de notificaciones mientras el panel está abierto o al volver a abrirlo; no se envían correos ni notificaciones del sistema operativo.

## Instalar con un plan revisado

1. Buscar índices recientes (la instalación requiere una consulta de menos de 24 horas).
2. Elegir «Actualizar todo» o «Sólo seguridad». Esto todavía no instala nada.
3. Revisar versiones, nuevas dependencias, descarga, espacio y servicios potencialmente afectados.
4. Confirmar que existe copia de los datos y que se aceptan posibles interrupciones de servicios.
5. Seguir la tarea y su registro. Se puede cerrar el navegador sin cancelar el trabajo.

Seguridad selecciona únicamente objetivos clasificados de seguridad, pero puede necesitar otras dependencias. Todas esas dependencias aparecen explícitamente en el plan. Las versiones candidatas pueden reunir tanto correcciones de seguridad como otros arreglos de Debian. «Todo» incluye paquetes confiables de terceros ya configurados, como agentes de conectividad, junto a los paquetes de Debian. Los paquetes retenidos quedan excluidos; si una dependencia exige cambiarlos, el plan se bloquea.

Las simulaciones expiran a los diez minutos. Se fijan versiones y arquitectura y se verifica que la simulación de `apt-get` coincida con los cambios calculados por python-apt. El worker vuelve a generar el plan y comprueba el estado de los índices y DPKG antes de instalar. Si cambian, solicita otra revisión. No permite quitar paquetes, bajar versiones, saltar autenticación de repositorios o cambiar la distribución Debian.

La instalación usa APT con `--no-remove`, conserva las configuraciones modificadas ante decisiones de DPKG y deja que los scripts normales de los paquetes actúen. `NEEDRESTART_MODE=l` evita solicitar reinicios automáticos adicionales a needrestart; los scripts de los paquetes sí pueden reiniciar sus propios servicios. No hay reinicio automático del host desde SHC. Si APT falla, el panel informa el error y el resultado de `dpkg --audit`; no intenta reparar ni repetir una transacción a ciegas.

## Riesgos y recuperación

Una actualización puede interrumpir Apache, SSH, Docker/containerd, libvirt o servicios que usan bibliotecas actualizadas. La red de administración también puede verse afectada por paquetes de conectividad. Una actualización del kernel no entra en uso hasta reiniciar el anfitrión; ese reinicio detiene las VM según su política y afecta todos los servicios del host. La lista de servicios del plan es una estimación por paquetes, no una garantía de continuidad.

Antes de cada instalación se guarda en `/var/lib/shc-monitor-updates/backups/<tarea>/`:

- Plan exacto y lista de paquetes/versiones.
- Archivo privado con `/etc/apt`, `/etc/apache2`, `/etc/libvirt`, `/etc/ssh`, `/etc/default`, estado de DPKG y marcas automáticas de APT, cuando existen.

Ese archivo puede contener claves de configuración: permanece en un directorio root 0700 y no se publica en GitHub ni se ofrece como descarga web. **No contiene los discos de las VM, bases de datos, volúmenes Docker ni datos de aplicaciones.** Esas copias deben prepararse aparte. Tampoco garantiza volver a una versión anterior: puede que Debian ya no publique los mismos binarios, y algunos cambios de datos no se revierten desinstalando un paquete. Para recuperación completa conviene una copia consistente del sistema y datos o una instantánea del almacenamiento disponible.

## Ejecución y permisos

El dashboard se comunica con el collector por su socket autenticado. El collector sólo puede invocar `/usr/local/libexec/shc-updates-helper` sin argumentos mediante la regla sudo dedicada. El helper recibe acciones JSON fijas; el navegador nunca aporta comandos ni listas de paquetes para instalar. Sólo se acepta un ID de plan creado y guardado por root.

Los workers se ejecutan en unidades transitorias `shc-updates-<UUID>.service`, de modo que sobreviven al cierre de sesión, a la recreación del dashboard y al reinicio del collector. APT/DPKG se ejecuta fuera del espacio de archivos de sólo lectura del collector. El collector sólo obtiene escritura adicional en los directorios privados de estado y caché de SHC. Se mantienen los bloqueos nativos de APT/DPKG y se impide iniciar dos tareas SHC simultáneamente. No se impone un timeout de instalación que pueda matar DPKG a mitad de trabajo.

## Instalación del componente

- Instalar `scripts/shc-updates-helper.py` como `/usr/local/libexec/shc-updates-helper`, root:root 0755.
- Instalar `scripts/shc_updates.py` a su lado, root:root 0644. Utiliza el Python del sistema y `python3-apt`, disponible en Debian.
- Validar e instalar `systemd/shc-updates.sudoers` como `/etc/sudoers.d/shc-updates`, root:root 0440. La cadena vacía en la regla restringe los argumentos de sudo.
- Instalar `shc-updates.conf` como drop-in del collector y `shc-updates.tmpfiles` en `/etc/tmpfiles.d/shc-updates.conf`; ejecutar systemd-tmpfiles para crear estado, planes, tareas, respaldos y caché con permisos root 0700.
- Instalar el servicio/timer `shc-updates-check`, ejecutar daemon-reload, reiniciar el collector y habilitar el timer. La unidad programada busca metadatos, nunca instala paquetes.
- Mantener los respaldos y registros privados según la política de almacenamiento del administrador. No incluirlos en exportaciones del código ni en Git.

## Actualizar VM desde el panel

Es posible, pero requiere administrar **dentro del invitado** y debe desarrollarse como una función separada. Linux puede usar SSH con claves dedicadas o QEMU Guest Agent; Windows puede usar WinRM por HTTPS o Guest Agent con PowerShell. Es necesario que el canal esté configurado y operativo, que existan permisos adecuados y que cada tarea valide la identidad de la VM, simule cambios, registre resultados y confirme sus reinicios. Un canal Guest Agent definido en el XML no implica que el agente esté instalado o conectado.

Esta versión no envía actualizaciones ni comandos de instalación a las VM. KVM administra sus recursos y dispositivos, pero no descubre por sí solo el catálogo de Windows Update o APT de cada invitado. Las credenciales o claves de esa futura integración deben permanecer fuera del repositorio.

Referencias: [APT apt-get](https://manpages.debian.org/trixie/apt/apt-get.8.en.html), [python-apt](https://apt-team.pages.debian.net/python-apt/library/apt.cache.html), [Debian Security Tracker](https://security-tracker.debian.org/), [actualizaciones periódicas de Debian](https://wiki.debian.org/PeriodicUpdates).
