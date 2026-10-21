#!/usr/bin/env python3
"""Descarga las estadísticas de una jugadora de la FBCyL y genera el panel HTML.

Uso:  python3 actualizar.py        (pide la contraseña, o la toma de la variable INFORME_CLAVE)
Resultado: datos/partidos.json  e  informe.html (con los datos cifrados con esa contraseña)
"""
import base64
import functools
import getpass
import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
import unicodedata
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# --- Configuración -----------------------------------------------------------
# Nombres tal como salen en el acta: uno por línea en jugadoras.txt, o separados por ";" en la variable JUGADORAS
# (fuera del código para que no queden públicos en el repositorio).
JUGADORAS = [n.strip() for n in (os.environ.get("JUGADORAS")
             or (Path(__file__).resolve().parent / "jugadoras.txt").read_text(encoding="utf-8")).replace(";", "\n").splitlines() if n.strip()]
EQUIPO_ID = 40103                     # PONCE PUCELA BASKET B3
GRUPOS = [7438]                       # 2ª Div. Cadete Fem. - Grupo C (añadir fases siguientes aquí)
CATEGORIA = 1135                      # 2ªDIV.- CAD. FEM. AUT.: la comparación con la liga usa todos sus grupos
TEMPORADA_ACTUAL = True
DURACION = timedelta(hours=1, minutes=40)   # duración estimada de un partido (modo directo)
# -----------------------------------------------------------------------------

ESB = "https://esb.optimalwayconsulting.com/fbcyl/1/jR4rgA5K6Chhh5vyfrxo9wTScdg2NT7K"
STATS = "https://msstats.optimalwayconsulting.com/v1/fbcyl"
BASE = Path(__file__).resolve().parent


@functools.lru_cache(maxsize=None)
def get(url, base64_body=False):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.fbcyl.es/"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    if base64_body:
        body = base64.b64decode(body)
    return json.loads(body)


def normaliza(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(texto.upper().split())


def tiros_de(data):
    tipos = [("shootingOfTwoSuccessfulPoint", 2, True), ("shootingOfTwoFailedPoint", 2, False),
             ("shootingOfThreeSuccessfulPoint", 3, True), ("shootingOfThreeFailedPoint", 3, False)]
    tiros = []
    for clave, tipo, anotado in tipos:
        for s in data.get(clave) or []:
            # x/y en mm respecto a la canasta (x: hacia medio campo, y: lateral)
            tiros.append({"x": s.get("x", 0), "y": s.get("y", 0), "tipo": tipo, "anotado": anotado,
                          "cuarto": s.get("period"), "min": s.get("min")})
    return tiros


def segundo(j):
    """Segundo absoluto de partido (cuartos de 10 min, prórrogas de 5)."""
    cuarto, resta = j.get("period") or 1, (j.get("min") or 0) * 60 + (j.get("sec") or 0)
    if cuarto <= 4:
        return (cuarto - 1) * 600 + 600 - resta
    return 2400 + (cuarto - 5) * 300 + 300 - resta


def marcador(j, local):
    try:
        a, b = (int(x) for x in (j.get("score") or "").split("-"))
    except ValueError:
        return None
    return a - b if local else b - a


def tramos(jugadas, objetivo, titular, local):
    """Tramos en pista de la jugadora y sus acciones, a partir del jugada a jugada."""
    fin = max([segundo(j) for j in jugadas if j.get("move") == "Fin de período"] or [2400])
    diff_final = next((marcador(j, local) for j in reversed(jugadas) if j.get("score")), None)
    lista, entrada, diff_entrada, acciones = [], (0 if titular else None), (0 if titular else None), []
    for j in jugadas:
        if normaliza(j.get("actorName")) != objetivo:
            continue
        mov, t = j.get("move") or "", segundo(j)
        if mov == "Entra al campo" and entrada is None:
            entrada, diff_entrada = t, marcador(j, local)
        elif mov == "Sale del campo" and entrada is not None:
            lista.append({"desde": entrada, "hasta": t, "parcial": _resta(marcador(j, local), diff_entrada)})
            entrada = None
        elif mov.startswith(("Canasta", "Intento fallado")) or "falta" in mov.lower():
            acciones.append({"t": t, "accion": mov})
    if entrada is not None:
        lista.append({"desde": entrada, "hasta": fin, "parcial": _resta(diff_final, diff_entrada)})
    return {"tramos": lista, "acciones": acciones, "duracion": fin}


def _resta(a, b):
    return a - b if a is not None and b is not None else None


def defensa(jugadas, objetivo, titular, nuestro):
    """Puntos y tiros de campo del rival con la jugadora en pista y en el banquillo (jugada a jugada)."""
    fin = max([segundo(j) for j in jugadas if j.get("move") == "Fin de período"] or [2400])
    d = dict.fromkeys(("segPista", "ptsPista", "tcaPista", "tciPista", "ptsBanco", "tcaBanco", "tciBanco"), 0)
    en_pista, desde = titular, 0
    for j in jugadas:
        mov = j.get("move") or ""
        if j.get("idTeam") == nuestro:
            if normaliza(j.get("actorName")) == objetivo:
                if mov == "Entra al campo" and not en_pista:
                    en_pista, desde = True, segundo(j)
                elif mov == "Sale del campo" and en_pista:
                    en_pista, d["segPista"] = False, d["segPista"] + segundo(j) - desde
            continue
        if not mov.startswith(("Canasta de", "Intento fallado de")):
            continue
        lado, valor, anotado = "Pista" if en_pista else "Banco", int(mov[-1]) if mov[-1].isdigit() else 0, mov.startswith("Canasta")
        d["pts" + lado] += valor if anotado else 0
        if valor in (2, 3):
            d["tci" + lado] += 1
            d["tca" + lado] += anotado
    if en_pista:
        d["segPista"] += fin - desde
    d["segBanco"] = fin - d["segPista"]
    return d


def jugadas_de(uuid):
    try:
        return get(f"{STATS}/getJsonWithMatchMoves/{uuid}?currentSeason={str(TEMPORADA_ACTUAL).lower()}")
    except Exception:
        return []


def id_interno(st):
    return next((t["teamIdIntern"] for t in st.get("teams", []) if t.get("teamIdExtern") == EQUIPO_ID), None)


def saltos(jugadas, st, objetivo):
    """Salto inicial y saltos entre dos a partir del jugada a jugada."""
    nuestro = id_interno(st)
    por_momento = {}
    for j in jugadas:
        if (j.get("move") or "").startswith("Salto "):
            por_momento.setdefault((j.get("period"), j.get("min"), j.get("sec"), j.get("timestamp")), []).append(j)
    lista = []
    for (cuarto, minuto, seg, _), grupo in sorted(por_momento.items(), key=lambda kv: kv[0][3] or ""):
        propia = next((j for j in grupo if j.get("idTeam") == nuestro), None)
        contraria = next((j for j in grupo if j.get("idTeam") != nuestro), None)
        if not propia:
            continue
        lista.append({"cuarto": cuarto, "reloj": f"{minuto}:{seg:02d}" if minuto is not None and seg is not None else "",
                      "saltadora": propia.get("actorName"), "dorsal": propia.get("actorShirtNumber"),
                      "ganado": propia.get("move") == "Salto ganado",
                      "rival": contraria.get("actorName") if contraria else None,
                      "rivalDorsal": contraria.get("actorShirtNumber") if contraria else None,
                      "esElla": normaliza(propia.get("actorName")) == objetivo})
    return {"saltoInicial": lista[0] if lista else None, "saltos": lista}


def datos_grupo(grupo):
    return get(f"{ESB}/FCBQWeb/getAllGamesByGrupWithMatchRecords/{grupo}", base64_body=True)["messageData"]


def partidos_del_equipo():
    for grupo in GRUPOS:
        for num, jornada in datos_grupo(grupo)["rounds"].items():
            for m in jornada["matches"].values():
                if EQUIPO_ID in (int(m["idLocalTeam"] or 0), int(m["idVisitorTeam"] or 0)):
                    yield grupo, int(num), m


def lanzamientos(d):
    return {"t1a": d.get("shotsOfOneSuccessful", 0), "t1i": d.get("shotsOfOneAttempted", 0),
            "t2a": d.get("shotsOfTwoSuccessful", 0), "t2i": d.get("shotsOfTwoAttempted", 0),
            "t3a": d.get("shotsOfThreeSuccessful", 0), "t3i": d.get("shotsOfThreeAttempted", 0),
            "faltas": d.get("faults", 0)}


def estadisticas(num, uuid):
    """Acta digital del partido (None si todavía no está disponible)."""
    try:
        return get(f"{STATS}/getJsonWithMatchStats/{uuid}?currentSeason={str(TEMPORADA_ACTUAL).lower()}")
    except Exception as e:
        print(f"  J{num}: sin estadísticas ({e})")
        return None


def partido(grupo, num, m):
    local = int(m["idLocalTeam"]) == EQUIPO_ID
    gf, gc = (m["localScore"], m["visitorScore"]) if local else (m["visitorScore"], m["localScore"])
    p = {
        "grupo": grupo, "jornada": num, "fecha": m["matchDay"], "local": local,
        "rival": m["nameVisitorTeam"] if local else m["nameLocalTeam"],
        "idRival": m["idVisitorTeam"] if local else m["idLocalTeam"],
        "pabellon": m["nameField"], "localidad": m["nameTown"],
        "logoRival": m.get("logoVisitant") if local else m.get("logoLocal"),
        "jugado": gf is not None and gc is not None,
        "puntosEquipo": int(gf) if gf is not None else None,
        "puntosRival": int(gc) if gc is not None else None,
        # El universallyid no aparece hasta que se cierra el acta; el idMatchCall está desde antes
        # del partido y la API de estadísticas lo acepta igual, también en directo
        "estadisticas": False, "uuidPartido": m.get("idMatchCall") or m.get("universallyid"),
        # Página del partido en la web de la federación (carga el acta con cualquiera de los dos identificadores)
        "fbcyl": f"https://www.fbcyl.es/estadisticas/partido/{m.get('season')}/{m.get('universallyid') or m.get('idMatchCall')}"
                 if m.get("season") and (m.get("universallyid") or m.get("idMatchCall")) else None,
    }
    return p


def equipos(st):
    """(nuestro equipo, rival) en el acta."""
    teams = (st or {}).get("teams", [])
    return (next((t for t in teams if t.get("teamIdExtern") == EQUIPO_ID), None),
            next((t for t in teams if t.get("teamIdExtern") != EQUIPO_ID), None))


def en_horario(fecha, ahora):
    try:
        inicio = datetime.strptime(fecha, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return False
    return inicio <= ahora < inicio + DURACION


def en_directo(p):
    """Marca el partido que se está jugando y, si el calendario aún no tiene resultado, toma el marcador del acta en vivo."""
    if not p.get("uuidPartido") or not en_horario(p["fecha"], datetime.now()):
        return p
    p["enJuego"] = True
    if not p["jugado"]:
        nuestro, rival = equipos(estadisticas(p["jornada"], p["uuidPartido"]))
        if nuestro and rival:
            p.update(jugado=True, puntosEquipo=nuestro["data"].get("score", 0), puntosRival=rival["data"].get("score", 0))
    return p


def ficha(base, jugadora):
    p = {**base, "jugo": False}
    local = p["local"]
    st = estadisticas(p["jornada"], p["uuidPartido"]) if p["jugado"] and p.get("uuidPartido") else None
    if not st:
        return p
    p["estadisticas"] = True
    objetivo = normaliza(jugadora)
    jugadas = jugadas_de(p["uuidPartido"])
    if jugadas:
        p.update(saltos(jugadas, st, objetivo))
    for equipo in st.get("teams", []):
        for j in equipo.get("players", []):
            if normaliza(j.get("name")) != objetivo:
                continue
            d = j["data"]
            p.update({
                "jugo": (j.get("timePlayed") or 0) > 0 or (j.get("gamePlayed") or 0) > 0,
                "uuid": j.get("uuid"),
                "dorsal": j.get("dorsal"), "titular": bool(j.get("starting")),
                "minutos": j.get("timePlayed") or 0,
                "puntos": d.get("score", 0), "valoracion": d.get("valoration", 0),
                "masMenos": j.get("inOut", 0), **lanzamientos(d), "faltasRecibidas": d.get("faultReceived", 0),
                "rebotes": d.get("rebounds", 0), "asistencias": d.get("assists", 0),
                "robos": d.get("steals", 0), "perdidas": d.get("lost", 0), "tapones": d.get("block", 0),
                "puntosCuartos": [q.get("score", 0) for q in j.get("periods", [])],
                "tiros": tiros_de(d),
            })
            if jugadas:
                p.update(tramos(jugadas, objetivo, bool(j.get("starting")), local))
                p["defensa"] = defensa(jugadas, objetivo, bool(j.get("starting")), id_interno(st))
    return p


def racha(valor):
    """Racha actual: +N victorias o -N derrotas seguidas.

    La federación la da como un número ("1") o como resultados por jornada separados por ";"
    ("1;0;-1": 1 victoria, -1 derrota, 0 sin partido), del más antiguo al más reciente.
    """
    resultados = [r for r in (int(x) for x in str(valor or "0").split(";") if x.strip().lstrip("-").isdigit()) if r]
    if len(resultados) <= 1:
        return resultados[0] if resultados else 0
    signo, n = (1 if resultados[-1] > 0 else -1), 0
    for r in reversed(resultados):
        if (r > 0) != (signo > 0):
            break
        n += 1
    return signo * n


def clasificacion():
    """Clasificación del grupo actual (vacía si la federación devuelve algo inesperado)."""
    try:
        return _clasificacion()
    except Exception as e:
        print(f"Sin clasificación ({e!r})")
        return []


def _clasificacion():
    entero = lambda v: int(v or 0)
    return [{"posicion": entero(s["position"]), "id": entero(s["idTeam"]), "equipo": s["teamName"],
                      "logo": s.get("entityLogo"), "pj": entero(s["matchPlayed"]), "g": entero(s["matchWin"]),
                      "p": entero(s["matchLost"]), "pf": entero(s["matchScoreFavour"]), "pc": entero(s["matchScoreAgainst"]),
                      "puntos": entero(s["standingScore"]), "racha": racha(s.get("recentStreak"))}
                     for s in datos_grupo(GRUPOS[-1])["standing"]]


def grupos_categoria():
    """Grupos de la categoría en la temporada actual (de todas las fases), según el buscador de fbcyl.es."""
    try:
        req = urllib.request.Request(f"https://www.fbcyl.es/ajax/combo_competicions2/{CATEGORIA}/F/1",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
        grupos = [(int(v), n.strip()) for v, n in re.findall(r'<option value="(\d+)">([^<]+)', html) if v != "0"]
        if grupos:
            return grupos
    except Exception as e:
        print(f"No se pudo leer la lista de grupos ({e}); solo los de GRUPOS")
    return [(g, f"Grupo {g}") for g in GRUPOS]


def liga():
    """Totales de la temporada de todas las jugadoras de la categoría, sumando las actas de todos sus grupos."""
    partidos = []
    grupos = []
    for id_grupo, nombre in grupos_categoria():
        try:
            d = datos_grupo(id_grupo)
        except Exception as e:
            print(f"  grupo {id_grupo}: sin datos ({e})")
            continue
        # "1ª FASE - LIGA REGULAR 2ªDIV CAD FEM-GRUPO A" -> "Grupo A"
        corto = (d.get("group") or {}).get("nameGroup") or nombre.rsplit("-", 1)[-1]
        grupos.append({"id": id_grupo, "nombre": corto.strip().title()})
        for ronda in d["rounds"].values():
            for m in ronda["matches"].values():
                ident = m.get("universallyid") or m.get("idMatchCall")
                if ident and m.get("localScore") is not None:
                    partidos.append((grupos[-1]["nombre"], ident))

    def acta(p):
        try:
            return p[0], get(f"{STATS}/getJsonWithMatchStats/{p[1]}?currentSeason={str(TEMPORADA_ACTUAL).lower()}")
        except Exception:
            return p[0], None

    jugadoras = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        actas = list(ex.map(acta, partidos))
    for grupo, st in actas:
        for t in (st or {}).get("teams") or []:
            for j in t.get("players") or []:
                if not ((j.get("timePlayed") or 0) > 0 or (j.get("gamePlayed") or 0) > 0):
                    continue
                d = j.get("data") or {}
                a = jugadoras.setdefault(j.get("uuid") or normaliza(j.get("name")), {
                    "nombre": j.get("name"), "uuid": j.get("uuid"), "equipo": t.get("name"), "idEquipo": t.get("teamIdExtern"),
                    "grupo": grupo, "pj": 0, "min": 0, "pts": 0, "val": 0, "mm": 0,
                    "t1a": 0, "t1i": 0, "t2a": 0, "t2i": 0, "t3a": 0, "t3i": 0, "faltas": 0})
                a["pj"] += 1
                a["min"] += j.get("timePlayed") or 0
                a["pts"] += d.get("score", 0)
                a["val"] += d.get("valoration", 0)
                a["mm"] += j.get("inOut", 0)
                for k, v in lanzamientos(d).items():
                    a[k] += v
    con_acta = sum(1 for _, st in actas if st and st.get("teams"))
    print(f"Liga: {len(grupos)} grupos, {con_acta} actas, {len(jugadoras)} jugadoras")
    return {"grupos": grupos, "actas": con_acta, "jugadoras": list(jugadoras.values())}


def evolucion(jugadas, duracion, local):
    """Marcador tras cada canasta: [minuto de juego, nuestros puntos, puntos del rival]."""
    def minuto(j):
        periodo = j.get("period") or 1
        previos = sum(duracion if k <= 4 else 5 for k in range(1, periodo))
        return previos + (duracion if periodo <= 4 else 5) - (j.get("min") or 0) - (j.get("sec") or 0) / 60
    # En el orden en que se apuntan en la mesa (el reloj de algunas jugadas sale desordenado); el minuto nunca retrocede
    puntos, ultimo, t = [[0, 0, 0]], (0, 0), 0
    for j in sorted(jugadas, key=lambda j: j.get("timestamp") or ""):
        try:
            l, v = (int(x) for x in (j.get("score") or "").split("-"))
        except ValueError:
            continue
        if (l, v) != ultimo:
            ultimo, t = (l, v), max(t, minuto(j))
            puntos.append([round(t, 2), *((l, v) if local else (v, l))])
    return puntos


def partido_equipo(base, seguidas):
    """Estadísticas de equipo de un partido: tiros, cuartos y líneas de todas las jugadoras."""
    p = dict(base)
    st = estadisticas(p["jornada"], p["uuidPartido"]) if p["jugado"] and p.get("uuidPartido") else None
    nuestro, rival = equipos(st)
    if nuestro and rival:
        jugadas = jugadas_de(p["uuidPartido"])
        p.update({
            "estadisticas": True,
            "nosotras": lanzamientos(nuestro["data"]), "ellas": lanzamientos(rival["data"]),
            "cuartos": [q.get("score", 0) for q in nuestro.get("periods", [])],
            "cuartosRival": [q.get("score", 0) for q in rival.get("periods", [])],
            "jugadoras": [{"nombre": j.get("name"), "uuid": j.get("uuid"), "dorsal": j.get("dorsal"), "titular": bool(j.get("starting")),
                           "jugo": (j.get("timePlayed") or 0) > 0 or (j.get("gamePlayed") or 0) > 0,
                           "minutos": j.get("timePlayed") or 0, "puntos": j["data"].get("score", 0),
                           "valoracion": j["data"].get("valoration", 0), "masMenos": j.get("inOut", 0),
                           "seguida": normaliza(j.get("name")) in seguidas, **lanzamientos(j["data"]),
                           "defensa": defensa(jugadas, normaliza(j.get("name")), bool(j.get("starting")),
                                              nuestro["teamIdIntern"]) if jugadas else None}
                          for j in nuestro.get("players", [])],
            "rivalJugadoras": [{"nombre": j.get("name"), "uuid": j.get("uuid"), "dorsal": j.get("dorsal"), "minutos": j.get("timePlayed") or 0,
                                "puntos": j["data"].get("score", 0), **lanzamientos(j["data"])}
                               for j in rival.get("players", [])
                               if (j.get("timePlayed") or 0) > 0 or (j.get("gamePlayed") or 0) > 0],
            "evolucion": evolucion(jugadas, st.get("periodDuration") or 10, p["local"]) if jugadas else [],
        })
    return p


def foto(uuid):
    """Descarga la foto de la federada y la devuelve como data URI (con caché en datos/fotos)."""
    carpeta = BASE / "datos" / "fotos"
    carpeta.mkdir(parents=True, exist_ok=True)
    guardada = next(carpeta.glob(f"{uuid}.*"), None)
    if not guardada:
        try:
            info = get(f"{ESB}/Federateds/getPhotobyUuidFederat/{uuid}", base64_body=True)["messageData"]
            url = next((x["photoUrl"] for x in info if x.get("photoUrl")), None)
            if not url:
                return None
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                guardada = carpeta / f"{uuid}{Path(url).suffix or '.jpg'}"
                guardada.write_bytes(r.read())
        except Exception as e:
            print(f"  sin foto para {uuid} ({e})")
            return None
    tipo = "image/png" if guardada.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{tipo};base64,{base64.b64encode(guardada.read_bytes()).decode()}"


def cifra(datos, clave, iteraciones=600_000):
    """Cifra los datos con AES-GCM usando una clave derivada de la contraseña (PBKDF2-SHA256)."""
    # Sal fija por equipo: así la clave guardada en la pestaña sigue valiendo tras cada actualización.
    sal, iv = hashlib.sha256(f"estadisticas-{EQUIPO_ID}".encode()).digest()[:16], os.urandom(12)
    llave = PBKDF2HMAC(hashes.SHA256(), 32, sal, iteraciones).derive(clave.encode())
    b64 = lambda b: base64.b64encode(b).decode()
    return {"sal": b64(sal), "iv": b64(iv), "iteraciones": iteraciones,
            "datos": b64(AESGCM(llave).encrypt(iv, json.dumps(datos, ensure_ascii=False).encode(), None))}


def pide_clave():
    clave = os.environ.get("INFORME_CLAVE")
    while not clave:
        clave = getpass.getpass("Contraseña para el informe: ")
        if clave and clave != getpass.getpass("Repítela: "):
            print("No coinciden.")
            clave = None
    return clave


def descifra(cifrado, clave):
    b64 = base64.b64decode
    llave = PBKDF2HMAC(hashes.SHA256(), 32, b64(cifrado["sal"]), cifrado["iteraciones"]).derive(clave.encode())
    return json.loads(AESGCM(llave).decrypt(b64(cifrado["iv"]), b64(cifrado["datos"]), None))


def pagina_publicada(clave):
    """Datos de la página ya publicada en GitHub Pages (descifrados), o None si no se puede."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    url = os.environ.get("PAGINA") or (f"https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}/" if "/" in repo else None)
    if not url:
        return None
    try:
        req = urllib.request.Request(f"{url}?t={int(time.time())}", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8")
        return descifra(json.loads(re.search(r"const CIFRADO = (\{.*?\});", html).group(1)), clave)
    except Exception as e:
        print(f"No se pudo leer la página publicada ({e})")
        return None


def actualizacion_completa():
    partidos_equipo = sorted(partidos_del_equipo(), key=lambda g: (g[2]["matchDay"] or "", g[0]))
    bases = [en_directo(partido(grupo, num, m)) for grupo, num, m in partidos_equipo]
    jugadoras = []
    for jugadora in JUGADORAS:
        print(f"\n== {jugadora}")
        partidos = []
        for base in bases:
            p = ficha(base, jugadora)
            estado = "pendiente" if not p["jugado"] else (f"{p.get('puntos', 0)} pts" if p["jugo"] else "no jugó / sin datos")
            print(f"J{p['jornada']:>2} {p['fecha'][:10]} vs {p['rival']}: {estado}")
            partidos.append(p)
        uuid = next((p["uuid"] for p in partidos if p.get("uuid")), None)
        jugadoras.append({"nombre": jugadora, "foto": foto(uuid) if uuid else None, "partidos": partidos})
    seguidas = {normaliza(n) for n in JUGADORAS}
    # Identificadores para enlazar a las páginas del equipo, el club y el grupo en la web de la federación
    m = next((m for _, _, m in reversed(partidos_equipo) if m.get("season")), {})
    club = m.get("idLocalClub") if str(m.get("idLocalTeam")) == str(EQUIPO_ID) else m.get("idVisitorClub")
    return {"equipo": "PONCE PUCELA BASKET B3",
            "competicion": "2ª División Cadete Femenino · Grupo C",
            "jugadoras": jugadoras,
            "liga": liga(),
            "equipoDatos": {"id": EQUIPO_ID, "club": club, "grupo": GRUPOS[-1], "temporada": m.get("season"),
                            "clasificacion": clasificacion(),
                            "partidos": [partido_equipo(b, seguidas) for b in bases]}}


def solo_partido_en_curso(clave):
    """Modo directo: parte de la página publicada y solo descarga el partido que se está jugando.

    Devuelve None si no se puede (página antigua o ilegible, o ningún partido en juego): entonces se hace la completa.
    """
    anterior = pagina_publicada(clave)
    if not anterior or "equipoDatos" not in anterior:
        return None
    ahora = datetime.now()
    actual = next((p for p in anterior["equipoDatos"]["partidos"]
                   if p.get("uuidPartido") and en_horario(p["fecha"], ahora)), None)
    if not actual:
        print("Ningún partido en juego ahora mismo.")
        return None
    claves = ("grupo", "jornada", "fecha", "local", "rival", "pabellon", "localidad",
              "jugado", "puntosEquipo", "puntosRival", "uuidPartido", "fbcyl", "logoRival", "idRival")
    base = en_directo({**{k: actual.get(k) for k in claves}, "estadisticas": False})
    print(f"Directo J{base['jornada']} vs {base['rival']}: {base['puntosEquipo']}-{base['puntosRival']}")
    mismo = lambda p: (p["grupo"], p["jornada"]) == (base["grupo"], base["jornada"])
    for j in anterior["jugadoras"]:
        j["partidos"] = [ficha(base, j["nombre"]) if mismo(p) else p for p in j["partidos"]]
    seguidas = {normaliza(j["nombre"]) for j in anterior["jugadoras"]}
    anterior["equipoDatos"]["partidos"] = [partido_equipo(base, seguidas) if mismo(p) else p
                                           for p in anterior["equipoDatos"]["partidos"]]
    return anterior


def main():
    clave = pide_clave()
    salida = (os.environ.get("DIRECTO") == "true" and solo_partido_en_curso(clave)) or actualizacion_completa()
    salida.update(actualizado=datetime.now().strftime("%d/%m/%Y %H:%M"),
                  repo=os.environ.get("GITHUB_REPOSITORY"))   # para el enlace "Actualizar datos" (solo en GitHub Actions)
    jugadoras = salida["jugadoras"]
    (BASE / "datos").mkdir(exist_ok=True)
    sin_fotos = {**salida, "jugadoras": [{**j, "foto": bool(j["foto"])} for j in jugadoras]}
    (BASE / "datos" / "partidos.json").write_text(json.dumps(sin_fotos, ensure_ascii=False, indent=1), encoding="utf-8")

    plantilla = (BASE / "plantilla.html").read_text(encoding="utf-8")
    html = plantilla.replace("/*__CIFRADO__*/null", json.dumps(cifra(salida, clave)))
    (BASE / "informe.html").write_text(html, encoding="utf-8")
    print(f"\nInforme generado: {BASE / 'informe.html'}")


if __name__ == "__main__":
    main()
