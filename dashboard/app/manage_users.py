"""Offline account setup; passwords are never passed as command arguments."""

from __future__ import annotations

import getpass
import sys

from . import auth


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Uso: python -m app.manage_users import-hash|set-password USUARIO")
    action, username = sys.argv[1:]
    if action == "import-hash":
        encoded = sys.stdin.read().strip()
        if not encoded.startswith("$2"):
            raise SystemExit("Se esperaba un hash bcrypt de htpasswd")
        auth.import_htpasswd(username, encoded)
    elif action == "set-password":
        auth.set_user(username, getpass.getpass("Contraseña: "))
    else:
        raise SystemExit("Acción no válida")


if __name__ == "__main__":
    main()
