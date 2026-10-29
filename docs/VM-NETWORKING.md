# Redes de máquinas virtuales

En **Máquinas virtuales → nombre de la VM**, la visión general y la tabla de interfaces muestran IPv4/IPv6 y la fuente de detección. Se consulta Guest Agent cuando el canal existe, DHCP de libvirt y ARP del host, en ese orden. Se eliminan duplicados por placa e IP. ARP puede contener caché; una IP detectada no garantiza que un servicio esté accesible. Una VM apagada no presenta una concesión antigua como IP actual. Si no hay datos, el panel lo indica: no estima una IP a partir de la subred.

Para mejorar la detección de IP fijas, agregá el canal QEMU Guest Agent con la VM apagada e instalá/activá el agente dentro del invitado. El canal por sí solo no instala el servicio de Windows o Linux.

Desde v0.9.2 se usa también un muestreo pasivo y acotado de cabeceras ARP/IPv4/IPv6, asociadas a la MAC de origen de cada placa de la VM. Esto permite detectar IP fijas con macvtap aunque el host no pueda comunicarse directamente con el invitado. Generar tráfico desde la VM, o hacer ping desde otra PC de la LAN mientras el detalle está abierto, permite observarla. Si la VM está silenciosa, no se garantiza descubrimiento inmediato; Guest Agent sigue siendo la fuente preferida. Las observaciones muestran fecha, se conservan hasta una hora y caducan al cambiar la conexión o la instancia de ejecución. Una IP observada no equivale a confirmar la configuración del invitado ni su máscara. No se guardan paquetes ni contenido de aplicaciones.

## Editar o agregar una placa

En **Interfaces de red → Editar**, o **Agregar interfaz**, se abre un diálogo sobre la página con:

- Tipo de conexión y origen existente en el servidor.
- Modelo e1000e, e1000, rtl8139 o VirtIO (requiere controladores).
- MAC unicast, conservada al editar o generada al agregar; se rechazan duplicados entre VM.
- Cable virtual conectado/desconectado, MTU opcional y número de colas VirtIO, limitado por las vCPU.

En puente directo, la MTU se hereda de la placa física y el campo queda deshabilitado. El editor no cambia la MTU del servidor.

Se pueden consultar las opciones con la VM encendida, pero para guardar es necesario apagarla y volver a abrir el editor. El panel nunca la apaga automáticamente. La configuración anterior se guarda en `/var/backups/shc-monitor/vm-config` con permisos privados. `virsh define --validate` comprueba la definición; la nueva placa se aplica al próximo encendido. Los discos y demás dispositivos se conservan. No se admite reemplazar conexiones con políticas avanzadas que el editor no representa.

## Elegir una conexión

| Tipo | Uso | Dirección IP |
| --- | --- | --- |
| Red virtual | Red activa de libvirt, por ejemplo NAT o aislada | DHCP de esa red o configuración del invitado |
| Red local · puente directo | macvtap sobre una placa Ethernet física disponible, en modo bridge | DHCP del router LAN o IP fija válida de esa LAN |
| Puente Linux | Puente ya preparado en el host y conectado a la LAN | DHCP del router LAN o IP fija válida de esa LAN |

La VM necesita **su propia IP**, distinta de la del host. Para cambiar desde NAT, seleccioná puente directo y la placa Ethernet que tenga enlace. Conservá la MAC y el modelo si no necesitás cambiarlos. Tras encender, usá DHCP dentro del invitado o adaptá su IP fija, máscara, puerta de enlace y DNS a la LAN. Habilitá los servicios que necesites y sus reglas de firewall en el invitado. La red física debe permitir varias MAC en ese puerto; aislamiento Wi-Fi, VLAN o políticas del switch/router pueden impedir el acceso entre equipos.

macvtap permite comunicación desde otras PC de la LAN, pero no comunicación directa entre la VM y el host por esa misma placa. Para esto último se puede conservar una segunda placa NAT o utilizar un puente Linux correctamente configurado. El editor no crea puentes, no modifica la IP del servidor y no reconfigura sus interfaces físicas. Wi-Fi, placas esclavas de un puente y puentes de Docker no se ofrecen como destinos físicos de macvtap. Los puentes administrados por libvirt se seleccionan mediante su red virtual.

Cambiar una placa puede modificar el perfil de red que ve Windows y sus reglas de firewall. La consola VNC sigue disponible para configurar el invitado aunque todavía no tenga conectividad IP.

Referencias: [formato de interfaces de libvirt](https://libvirt.org/formatdomain.html#network-interfaces), [detección de direcciones con virsh](https://libvirt.org/manpages/virsh.html#domifaddr), [limitación host/invitado de macvtap](https://wiki.libvirt.org/TroubleshootMacvtapHostFail.html).

## Instalación

El helper necesita `scripts/shc_vm_network.py` instalado como `/usr/local/libexec/shc_vm_network.py`, junto a `shc-vm-helper` y `shc_vm_create.py`. El archivo debe pertenecer a root y no permitir escritura al usuario del collector (`root:root`, modo 0644). No se agrega ninguna regla sudo ni se cambia el alcance de permisos del helper.

El drop-in `systemd/shc-vm-create.conf` permite escribir en el directorio privado de respaldo de XML; `systemd/shc-vm-create.tmpfiles` lo prepara como root. Se mantiene `ProtectSystem=strict` y no se habilita escritura general en `/var/backups`.

La detección pasiva requiere además `scripts/shc_vm_discovery.py` junto al helper, con propietario root y modo 0644. El directorio temporal `/run/shc-vm-network` se prepara como root con modo 0700 mediante los mismos archivos de systemd/tmpfiles. El helper privilegiado existente realiza el muestreo; el dashboard no obtiene sockets de red sin procesar ni permisos adicionales.
