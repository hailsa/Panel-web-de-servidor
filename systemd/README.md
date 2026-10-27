# systemd

La unidad `shc-collector.service` ejecuta el collector con privilegios limitados.

Para habilitar los controles de energía de v0.4.0, cree el grupo `shc-power`, agregue el usuario del collector e instale `shc-monitor-power.sudoers` en `/etc/sudoers.d/shc-monitor-power` con modo `0440`. Valide el archivo con `visudo -cf` antes de reiniciar el servicio.

