#!/usr/bin/env python3
"""Quién puede entrar en la web: cuentas de Google (pueden escribir) y enlaces de invitación (solo leer).

    python3 invitar.py                          lista quién tiene acceso
    python3 invitar.py ana@gmail.com ...        da acceso a una o varias cuentas de Google
    python3 invitar.py Abuela                   crea un enlace de invitación (para quien no tiene Google)
    python3 invitar.py --anular ana@gmail.com   quita el acceso a una cuenta
    python3 invitar.py --anular Abuela          anula el enlace (y la sesión de quien entró con él)

Las listas se guardan en autorizados.txt e invitaciones.txt (nunca van al repositorio) y se suben a los
secretos AUTORIZADOS e INVITACIONES de GitHub; después se lanza una publicación para que el cambio llegue a la web.
GitHub no deja leer los secretos, así que autorizados.txt tiene que tener SIEMPRE la lista completa: lo que no
esté en el archivo pierde el acceso al subirlo.
"""
import re
import secrets
import subprocess
import sys
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
AUTORIZADOS = CARPETA / "autorizados.txt"
INVITACIONES = CARPETA / "invitaciones.txt"
REPO = "nefestofeles-repo/estadisticas"
WEB = "https://estadisticas-baloncesto.pages.dev"
CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def lee_correos():
    if not AUTORIZADOS.exists():
        return None
    texto = AUTORIZADOS.read_text(encoding="utf-8")
    return sorted({c.lower() for c in re.split(r"[\s,;]+", texto) if "@" in c})


def lee_invitaciones():
    if not INVITACIONES.exists():
        return {}
    lineas = (l.partition("=") for l in INVITACIONES.read_text(encoding="utf-8").splitlines())
    return {nombre.strip(): codigo.strip() for nombre, _, codigo in lineas if nombre.strip() and codigo.strip()}


def sube(secreto, texto):
    subprocess.run(["gh", "secret", "set", secreto, "-R", REPO], input=texto or " ", text=True, check=True)


def publica():
    subprocess.run(["gh", "workflow", "run", "publicar.yml", "-R", REPO], check=True)
    print("Publicando: el cambio llega a la web en unos 2 minutos.")


def guarda_correos(correos):
    texto = "".join(f"{c}\n" for c in correos)
    AUTORIZADOS.write_text(texto, encoding="utf-8")
    sube("AUTORIZADOS", texto)


def guarda_invitaciones(invitaciones):
    texto = "".join(f"{nombre} = {codigo}\n" for nombre, codigo in invitaciones.items())
    INVITACIONES.write_text(texto, encoding="utf-8")
    sube("INVITACIONES", texto)


def necesita_lista():
    sys.exit(f"Falta {AUTORIZADOS.name}. GitHub no deja leer el secreto AUTORIZADOS, así que créalo primero con\n"
             f"los correos que ya tienen acceso (uno por línea); si no, al subirlo perderían el acceso:\n"
             f"    nano {AUTORIZADOS}")


def main():
    args = sys.argv[1:]
    correos, invitaciones = lee_correos(), lee_invitaciones()

    if not args:
        print("Cuentas de Google (leen y escriben):")
        if correos is None:
            print(f"  (sin {AUTORIZADOS.name}: la lista solo está en el secreto de GitHub)")
        for c in correos or []:
            print(f"  {c}")
        print("\nEnlaces de invitación (solo leen):")
        for nombre, codigo in invitaciones.items():
            print(f"  {nombre}: {WEB}/_acceso/invitacion/{codigo}")
        if not invitaciones:
            print("  ninguno")
        return

    if args[0] == "--anular":
        quien = " ".join(args[1:]).strip()
        if "@" in quien:
            if correos is None:
                necesita_lista()
            if quien.lower() not in correos:
                sys.exit(f"{quien} no está en {AUTORIZADOS.name}.")
            guarda_correos([c for c in correos if c != quien.lower()])
            print(f"Quitado el acceso a {quien}.")
        else:
            if invitaciones.pop(quien, None) is None:
                sys.exit(f"No hay ninguna invitación para «{quien}».")
            guarda_invitaciones(invitaciones)
            print(f"Anulada la invitación de {quien}.")
        publica()
        return

    if all("@" in a for a in args):
        malos = [a for a in args if not CORREO.match(a)]
        if malos:
            sys.exit(f"No parecen correos: {', '.join(malos)}")
        if correos is None:
            necesita_lista()
        nuevos = [a.lower() for a in args if a.lower() not in correos]
        if not nuevos:
            sys.exit("Ya tenían acceso todos.")
        guarda_correos(sorted({*correos, *nuevos}))
        publica()
        print("Ya pueden entrar con su cuenta de Google en", WEB)
        for c in nuevos:
            print(f"  {c}")
        return

    nombre = " ".join(args).strip()
    if "=" in nombre or "@" in nombre:
        sys.exit("El nombre de una invitación no puede llevar «=» ni «@» (para correos, pon solo correos).")
    if nombre in invitaciones:
        sys.exit(f"{nombre} ya tiene invitación: {WEB}/_acceso/invitacion/{invitaciones[nombre]}")
    invitaciones[nombre] = secrets.token_urlsafe(24)
    guarda_invitaciones(invitaciones)
    publica()
    print(f"Enlace para {nombre} (solo lectura):\n{WEB}/_acceso/invitacion/{invitaciones[nombre]}")


if __name__ == "__main__":
    main()
