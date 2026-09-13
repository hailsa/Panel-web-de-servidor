# Gestión de versiones

SHC utiliza versionado semántico y tags anotados de Git.

- `v0.1.0`: primera versión operativa del dashboard.
- `v0.2.0`: navegación, inventario de usuarios y estado detallado del servidor.

Para cada nueva versión:

1. Crear una rama `codex/vX.Y.Z` desde `main`.
2. Implementar y validar sin incorporar secretos ni configuración local.
3. Actualizar las notas de la versión en este directorio.
4. Crear un commit de release y el tag anotado `vX.Y.Z`.
5. Subir `main`, la rama de versión y los tags a GitHub.
6. Desplegar sólo después de crear un respaldo recuperable de la versión anterior.
