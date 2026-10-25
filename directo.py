#!/usr/bin/env python3
"""Actualización en directo durante los partidos del equipo.

Busca en el calendario los partidos de hoy y, mientras dura cada uno (hora de inicio + 2 h 30 min),
lanza el workflow de publicación cada 2 minutos en modo directo (solo descarga ese partido;
el resto lo toma de la página ya publicada, ver actualizar.solo_partido_en_curso). Un trabajo de GitHub Actions no puede durar más
de 6 horas, así que si falta mucho para el partido espera un rato y se vuelve a lanzar a sí mismo.

Uso:  python3 directo.py                                (en GitHub Actions, con GH_TOKEN y TZ=Europe/Madrid)
      python3 directo.py --simulacro "2026-10-17 10:00" (solo muestra qué haría a esa hora)
"""
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

os.environ.setdefault("JUGADORAS", "-")   # para leer el calendario no hacen falta los nombres
import actualizar  # noqa: E402

DURACION = actualizar.DURACION                # duración estimada de un partido
INTERVALO = 120                             # segundos entre actualizaciones durante el partido
ESPERA_MAX = timedelta(hours=3, minutes=15) # espera + partido debe caber en las 6 h de un trabajo


def partidos_pendientes_hoy(ahora):
    """Partidos de hoy que aún no han terminado, por hora de inicio."""
    hoy = []
    for _, num, m in actualizar.partidos_del_equipo():
        try:
            inicio = datetime.strptime(m["matchDay"], "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            continue
        if inicio.date() == ahora.date() and inicio + DURACION > ahora:
            local = int(m["idLocalTeam"]) == actualizar.EQUIPO_ID
            hoy.append((inicio, num, m["nameVisitorTeam"] if local else m["nameLocalTeam"]))
    return sorted(hoy)


def lanzar(workflow, simulacro, *opciones):
    orden = ["gh", "workflow", "run", workflow, *opciones, "--repo", os.environ.get("GITHUB_REPOSITORY", "")]
    if simulacro:
        print("  [simulacro]", " ".join(orden[:-2]))
    else:
        subprocess.run(orden, check=False)


def main():
    simulacro = "--simulacro" in sys.argv
    ahora = datetime.strptime(sys.argv[-1], "%Y-%m-%d %H:%M") if simulacro else datetime.now()
    pendientes = partidos_pendientes_hoy(ahora)
    if not pendientes:
        print("Hoy no quedan partidos.")
        return
    inicio, num, rival = pendientes[0]
    fin = inicio + DURACION
    print(f"J{num} vs {rival}: de {inicio:%H:%M} a {fin:%H:%M}")

    if inicio - ahora > ESPERA_MAX:
        print(f"Faltan {inicio - ahora}; espero {ESPERA_MAX} y me vuelvo a lanzar.")
        if not simulacro:
            time.sleep(ESPERA_MAX.total_seconds())
        lanzar("partido.yml", simulacro)
        return

    if inicio > ahora:
        print(f"Espero hasta las {inicio:%H:%M}.")
        if not simulacro:
            time.sleep((inicio - ahora).total_seconds())
    print(f"Partido en juego: actualizo cada {INTERVALO} s hasta las {fin:%H:%M}.")
    if simulacro:
        lanzar("publicar.yml", simulacro, "-f", "directo=true")
    else:
        while datetime.now() < fin:
            lanzar("publicar.yml", simulacro, "-f", "directo=true")
            time.sleep(INTERVALO)

    # Al terminar, una actualización completa con el resultado y la clasificación
    lanzar("publicar.yml", simulacro)
    # Si hay otro partido hoy, lo atiende un trabajo nuevo (con sus 6 h completas)
    if len(pendientes) > 1:
        lanzar("partido.yml", simulacro)


if __name__ == "__main__":
    main()
