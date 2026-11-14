#!/usr/bin/env python3
"""Enlaces de invitación para entrar en la web sin cuenta de Google.

    python3 invitar.py                 lista las invitaciones
    python3 invitar.py Abuela          crea una invitación y muestra su enlace
    python3 invitar.py --anular Abuela anula la invitación (y la sesión de quien entró con ella)

La lista se guarda en invitaciones.txt (nunca va al repositorio) y se sube al secreto INVITACIONES de GitHub;
después se lanza una publicación para que el cambio llegue a la web.
"""
import secrets
import subprocess
import sys
from pathlib import Path

ARCHIVO = Path(__file__).resolve().parent / "invitaciones.txt"
REPO = "nefestofeles-repo/estadisticas"
WEB = "https://estadisticas-baloncesto.pages.dev"


def lee():
    if not ARCHIVO.exists():
        return {}
    lineas = (l.partition("=") for l in ARCHIVO.read_text(encoding="utf-8").splitlines())
    return {nombre.strip(): codigo.strip() for nombre, _, codigo in lineas if nombre.strip() and codigo.strip()}


def guarda_y_publica(invitaciones):
    texto = "".join(f"{nombre} = {codigo}\n" for nombre, codigo in invitaciones.items())
    ARCHIVO.write_text(texto, encoding="utf-8")
    subprocess.run(["gh", "secret", "set", "INVITACIONES", "-R", REPO], input=texto or " ", text=True, check=True)
    subprocess.run(["gh", "workflow", "run", "publicar.yml", "-R", REPO], check=True)
    print("Publicando: el cambio llega a la web en unos 2 minutos.")


def main():
    invitaciones = lee()
    args = sys.argv[1:]
    if not args:
        for nombre, codigo in invitaciones.items():
            print(f"{nombre}: {WEB}/_acceso/invitacion/{codigo}")
        print(f"{len(invitaciones)} invitación(es).")
    elif args[0] == "--anular":
        nombre = " ".join(args[1:])
        if invitaciones.pop(nombre, None) is None:
            sys.exit(f"No hay ninguna invitación para «{nombre}».")
        guarda_y_publica(invitaciones)
        print(f"Anulada la invitación de {nombre}.")
    else:
        nombre = " ".join(args)
        if "=" in nombre:
            sys.exit("El nombre no puede llevar «=».")
        if nombre in invitaciones:
            sys.exit(f"{nombre} ya tiene invitación: {WEB}/_acceso/invitacion/{invitaciones[nombre]}")
        invitaciones[nombre] = secrets.token_urlsafe(24)
        guarda_y_publica(invitaciones)
        print(f"Enlace para {nombre}:\n{WEB}/_acceso/invitacion/{invitaciones[nombre]}")


if __name__ == "__main__":
    main()
