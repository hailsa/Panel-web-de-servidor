# Modelo de seguridad

## Límites de confianza

- El navegador sólo puede abrir una consola del usuario del collector después de autenticarse; la consola equivale a acceso de shell a ese usuario y debe tratarse como una función privilegiada.
- Apache es el único servicio web expuesto a las redes privadas autorizadas.
- El dashboard trata todas las respuestas del collector como datos no confiables.
- El collector acepta peticiones sólo por socket Unix y con token.
- Los secretos, certificados, bases y backups permanecen fuera de Git.

## Privilegios del collector

La implementación comenzará sin asumir root. Cada fuente será probada con un usuario de servicio dedicado. Si SMART u otra fuente requiere elevación, se preferirán permisos de dispositivo, capabilities o reglas sudo limitadas a comandos y argumentos concretos. Nunca se utilizará `NOPASSWD: ALL`.

El acceso al grupo `docker` equivale prácticamente a privilegios de root. Antes de usarlo se evaluará un helper limitado o un proxy local que exponga únicamente operaciones de lectura necesarias.

## Dashboard

El contenedor utilizará usuario sin privilegios, `cap_drop: ALL`, `no-new-privileges`, filesystem raíz de sólo lectura y un volumen escribible dedicado a SQLite. No montará `/dev`, `/proc`, `/sys` ni `/var/run/docker.sock` del host.

## Acceso web

La versión actual usa cuentas SQLite con scrypt y sesiones revocables en cookies `Secure`, `HttpOnly` y `SameSite=Strict`. El hash bcrypt anterior de `htpasswd` se puede importar para conservar la contraseña de `hailsa`; Apache ya no hace HTTP Basic. La consola web está restringida a sesiones autenticadas y a las redes privadas autorizadas por Apache. La cuenta de prueba `admin` debe recibir una contraseña robusta antes de ampliar el acceso.

Apache añadirá encabezados de seguridad compatibles con los recursos servidos localmente. HSTS se evaluará después de que el certificado y la ruta HTTPS estén validados.

## Operaciones reversibles

Los scripts de instalación sólo administrarán recursos con nombre SHC. Antes de tocar Apache, systemd o certificados copiarán los archivos afectados a `/var/backups/shc-monitor/<timestamp>/`. La desinstalación no eliminará paquetes compartidos ni recursos de otros proyectos.
