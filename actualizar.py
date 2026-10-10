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
import unicodedata
import urllib.request
from datetime import datetime
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
TEMPORADA_ACTUAL = True
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


def jugadas_de(m):
    try:
        return get(f"{STATS}/getJsonWithMatchMoves/{m['universallyid']}?currentSeason={str(TEMPORADA_ACTUAL).lower()}")
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


def estadisticas(num, m):
    """Acta digital del partido (None si todavía no está disponible)."""
    try:
        return get(f"{STATS}/getJsonWithMatchStats/{m['universallyid']}?currentSeason={str(TEMPORADA_ACTUAL).lower()}")
    except Exception as e:
        print(f"  J{num}: sin estadísticas ({e})")
        return None


def partido(grupo, num, m):
    local = int(m["idLocalTeam"]) == EQUIPO_ID
    gf, gc = (m["localScore"], m["visitorScore"]) if local else (m["visitorScore"], m["localScore"])
    p = {
        "grupo": grupo, "jornada": num, "fecha": m["matchDay"], "local": local,
        "rival": m["nameVisitorTeam"] if local else m["nameLocalTeam"],
        "pabellon": m["nameField"], "localidad": m["nameTown"],
        "jugado": gf is not None and gc is not None,
        "puntosEquipo": int(gf) if gf is not None else None,
        "puntosRival": int(gc) if gc is not None else None,
        "estadisticas": False,
    }
    return p


def ficha(grupo, num, m, jugadora):
    p = {**partido(grupo, num, m), "jugo": False}
    local = p["local"]
    st = estadisticas(num, m) if p["jugado"] and m.get("universallyid") else None
    if not st:
        return p
    p["estadisticas"] = True
    objetivo = normaliza(jugadora)
    jugadas = jugadas_de(m)
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


def equipo(partidos_equipo):
    """Clasificación del grupo actual y estadísticas de equipo de cada partido."""
    entero = lambda v: int(v or 0)
    clasificacion = [{"posicion": entero(s["position"]), "id": entero(s["idTeam"]), "equipo": s["teamName"],
                      "logo": s.get("entityLogo"), "pj": entero(s["matchPlayed"]), "g": entero(s["matchWin"]),
                      "p": entero(s["matchLost"]), "pf": entero(s["matchScoreFavour"]), "pc": entero(s["matchScoreAgainst"]),
                      "puntos": entero(s["standingScore"]), "racha": entero(s.get("recentStreak"))}
                     for s in datos_grupo(GRUPOS[-1])["standing"]]
    seguidas = {normaliza(n) for n in JUGADORAS}
    partidos = []
    for grupo, num, m in partidos_equipo:
        p = partido(grupo, num, m)
        st = estadisticas(num, m) if p["jugado"] and m.get("universallyid") else None
        nuestro = next((t for t in (st or {}).get("teams", []) if t.get("teamIdExtern") == EQUIPO_ID), None)
        rival = next((t for t in (st or {}).get("teams", []) if t.get("teamIdExtern") != EQUIPO_ID), None)
        if nuestro and rival:
            jugadas = jugadas_de(m)
            p.update({
                "estadisticas": True,
                "nosotras": lanzamientos(nuestro["data"]), "ellas": lanzamientos(rival["data"]),
                "cuartos": [q.get("score", 0) for q in nuestro.get("periods", [])],
                "cuartosRival": [q.get("score", 0) for q in rival.get("periods", [])],
                "jugadoras": [{"nombre": j.get("name"), "dorsal": j.get("dorsal"), "titular": bool(j.get("starting")),
                               "jugo": (j.get("timePlayed") or 0) > 0 or (j.get("gamePlayed") or 0) > 0,
                               "minutos": j.get("timePlayed") or 0, "puntos": j["data"].get("score", 0),
                               "valoracion": j["data"].get("valoration", 0), "masMenos": j.get("inOut", 0),
                               "seguida": normaliza(j.get("name")) in seguidas, **lanzamientos(j["data"]),
                               "defensa": defensa(jugadas, normaliza(j.get("name")), bool(j.get("starting")),
                                                  nuestro["teamIdIntern"]) if jugadas else None}
                              for j in nuestro.get("players", [])],
            })
        partidos.append(p)
    return {"id": EQUIPO_ID, "clasificacion": clasificacion, "partidos": partidos}


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


def main():
    clave = pide_clave()
    partidos_equipo = sorted(partidos_del_equipo(), key=lambda g: (g[2]["matchDay"] or "", g[0]))
    jugadoras = []
    for jugadora in JUGADORAS:
        print(f"\n== {jugadora}")
        partidos = []
        for grupo, num, m in partidos_equipo:
            p = ficha(grupo, num, m, jugadora)
            estado = "pendiente" if not p["jugado"] else (f"{p.get('puntos', 0)} pts" if p["jugo"] else "no jugó / sin datos")
            print(f"J{num:>2} {p['fecha'][:10]} vs {p['rival']}: {estado}")
            partidos.append(p)
        uuid = next((p["uuid"] for p in partidos if p.get("uuid")), None)
        jugadoras.append({"nombre": jugadora, "foto": foto(uuid) if uuid else None, "partidos": partidos})

    salida = {"equipo": "PONCE PUCELA BASKET B3",
              "competicion": "2ª División Cadete Femenino · Grupo C",
              "actualizado": datetime.now().strftime("%d/%m/%Y %H:%M"), "jugadoras": jugadoras,
              "equipoDatos": equipo(partidos_equipo),
              "repo": os.environ.get("GITHUB_REPOSITORY")}   # para el enlace "Actualizar datos" (solo en GitHub Actions)
    (BASE / "datos").mkdir(exist_ok=True)
    sin_fotos = {**salida, "jugadoras": [{**j, "foto": bool(j["foto"])} for j in jugadoras]}
    (BASE / "datos" / "partidos.json").write_text(json.dumps(sin_fotos, ensure_ascii=False, indent=1), encoding="utf-8")

    plantilla = (BASE / "plantilla.html").read_text(encoding="utf-8")
    html = plantilla.replace("/*__CIFRADO__*/null", json.dumps(cifra(salida, clave)))
    (BASE / "informe.html").write_text(html, encoding="utf-8")
    print(f"\nInforme generado: {BASE / 'informe.html'}")


if __name__ == "__main__":
    main()
