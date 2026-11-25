"""Una tanda: unos cuantos documentos, de las capturas a la rama publicada.

Lo que pasó con cada documento queda en `estado/<clave>.json`. De ahí sale
qué toca en la tanda siguiente: primero los documentos que nunca se han
intentado y, cuando ya no quedan, los que llevan más tiempo sin revisarse (por
si Wayback guardó una versión nueva).
"""
import datetime
import json
import os
import pathlib
import re
import subprocess
import time

from . import RAIZ, configuracion
from . import cadena, capturas, coherencia, faltantes, reedicion

ESTADO = RAIZ / "estado"
INFORMES = RAIZ / "coherencia"
EXTRACTOR = {"constitucion": "constitucion-extractor", "federal": "fiscal-extractor"}
MARCA = ("<!-- ramas -->", "<!-- /ramas -->")
MINUTOS_DE_REVISION = 240


def leer_estado(clave: str) -> dict | None:
    ruta = ESTADO / f"{clave}.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def sin_intentar() -> list[dict]:
    return [d for d in configuracion()["documentos"] if leer_estado(d["clave"]) is None]


def elegir(lote: int, claves: list[str] | None = None) -> list[dict]:
    documentos = configuracion()["documentos"]
    if claves:
        return [d for d in documentos if d["clave"] in claves]
    nuevos = sin_intentar()
    if nuevos:
        return nuevos[:lote]
    # Revisión: todos, del que lleva más tiempo sin verse al más reciente;
    # `correr` se detiene al agotar su tiempo.
    return sorted(documentos, key=lambda d: leer_estado(d["clave"])["fecha"])


def procesar(doc: dict, carpeta_capturas: pathlib.Path, repo: pathlib.Path,
             extractores: pathlib.Path, publicar: bool, desde_cero: bool = False) -> dict:
    """Capturas, cadena, coherencia y, si pasa, la rama publicada."""
    clave = doc["clave"]
    previo = leer_estado(clave) or {}
    estado = {"fecha": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
              "configuracion": cadena.sello_de_configuracion(clave), "publicada": False}
    try:
        filas = capturas.descargar(clave, doc["archivos"], carpeta_capturas / clave, movil=doc.get("movil"))
        plan = capturas.versiones(clave)
        estado |= {"capturas": len(filas), "versiones_archivadas": len(plan)}
        if not plan:
            return estado | {"motivo": "sin capturas con fecha de versión"}
        # Una rama publicada sin capturas nuevas ni cambios en lo declarado
        # sigue siendo la misma: no hay nada que rehacer.
        if (previo.get("publicada") and publicar and not desde_cero
                and all(previo.get(k) == estado[k] for k in ("configuracion", "capturas", "versiones_archivadas"))):
            return previo | {"fecha": estado["fecha"]}
        # Lo que ya falló solo se salta si nada de lo declarado cambió.
        fuera = previo.get("fuera", []) if previo.get("configuracion") == estado["configuracion"] else []
        if publicar:
            cadena._correr("git", "fetch", "-q", "origin", f"+refs/heads/{clave}:refs/heads/{clave}", cwd=repo)
        nuevas = cadena.construir(
            doc, carpeta_capturas / clave, repo, extractores / EXTRACTOR[doc["extractor"]],
            RAIZ / "_trabajo" / clave, desde_cero=desde_cero,
            fuera_conocidas={(f["version"], plan[f["version"]]["sha256"]) for f in fuera
                             if f["version"] in plan and plan[f["version"]]["sha256"] == f["sha256"]})
        fuera = [f for f in fuera if f["version"] in plan and plan[f["version"]]["sha256"] == f["sha256"]
                 and not desde_cero]
        fuera += [{"version": f["version"], "sha256": plan[f["version"]]["sha256"], "motivo": f["motivo"]}
                  for f in nuevas if f["estado"] != "ok"
                  and f["version"] not in {x["version"] for x in fuera}]
        estado["fuera"] = fuera
        if cadena._correr("git", "rev-parse", "-q", "--verify", f"refs/heads/{clave}", cwd=repo)[0]:
            return estado | {"motivo": "ninguna versión pasó las compuertas del extractor"}
        pasos = coherencia.medir(repo, clave, reedicion.lector(
            clave, carpeta_capturas,
            extractores / EXTRACTOR["federal"] if doc["extractor"] == "federal" else None))
        INFORMES.mkdir(exist_ok=True)
        (INFORMES / f"{clave}.json").write_text(json.dumps(pasos, ensure_ascii=False, indent=1) + "\n")
        fechas = [t["Publicacion"] for t in cadena._hechas(repo, clave)]
        estado |= {"versiones": len(fechas), "desde": min(fechas), "hasta": max(fechas),
                   "sin_explicar": sum(len(p["sin_explicar"]) for p in pasos)}
        estado |= faltantes.medir(repo, clave)
        if estado["sin_explicar"]:
            return estado | {"motivo": "la coherencia deja artículos sin explicar"}
        if publicar:
            cadena._git(repo, "push", "-q", "--force", "origin", f"refs/heads/{clave}:refs/heads/{clave}")
        estado["publicada"] = publicar
    except Exception as e:
        estado["motivo"] = f"{type(e).__name__}: {e}"[:300]
    return estado


def guardar_estado(clave: str, estado: dict) -> None:
    ESTADO.mkdir(exist_ok=True)
    (ESTADO / f"{clave}.json").write_text(json.dumps(estado, ensure_ascii=False, indent=1) + "\n")


def tabla_de_ramas() -> str:
    """Una fila por rama publicada. «Faltan» son las publicaciones del periodo
    que anotan los artículos y de las que nadie archivó el PDF."""
    filas = ["| Rama | Ley | Versiones | Periodo | Faltan |", "|---|---|---|---|---|"]
    for doc in configuracion()["documentos"]:
        e = leer_estado(doc["clave"])
        if e and e.get("publicada"):
            nombre = doc.get("etiqueta", "Constitución Política de los Estados Unidos Mexicanos")
            faltan = len(e["faltan"]) if "faltan" in e else ""
            filas.append(f"| [`{doc['clave']}`](../../tree/{doc['clave']}) | {nombre} | "
                         f"{e['versiones']} | {e['desde']} a {e['hasta']} | {faltan} |")
    return "\n".join(filas)


def medir_faltantes(repo: pathlib.Path, claves: list[str] | None = None) -> str:
    """Mide las ramas ya publicadas y lo deja en su estado: una rama sin
    capturas nuevas no se rehace, y no pasaría por `procesar`."""
    ramas = versiones = faltan = anteriores = 0
    for doc in configuracion()["documentos"]:
        clave, e = doc["clave"], leer_estado(doc["clave"])
        if not e or not e.get("publicada") or (claves and clave not in claves):
            continue
        cadena._correr("git", "fetch", "-q", "origin", f"+refs/heads/{clave}:refs/heads/{clave}", cwd=repo)
        e |= faltantes.medir(repo, clave)
        guardar_estado(clave, e)
        ramas, versiones = ramas + 1, versiones + e["versiones"]
        faltan, anteriores = faltan + len(e["faltan"]), anteriores + e["anteriores"]
    return (f"{ramas} ramas, {versiones} versiones; faltan {faltan} publicaciones del periodo "
            f"y hubo {anteriores} antes de la primera versión")


def publicar_indice(repo: pathlib.Path) -> bool:
    """Pone en el README de `main` la tabla de las ramas publicadas."""
    cadena._git(repo, "fetch", "-q", "origin", "+refs/heads/main:refs/heads/main")
    cadena._git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    cadena._git(repo, "reset", "-q", "--hard")
    cadena._git(repo, "clean", "-qfd")
    readme = repo / "README.md"
    texto = readme.read_text(encoding="utf-8")
    patron = re.compile(re.escape(MARCA[0]) + r".*?" + re.escape(MARCA[1]), re.S)
    nuevo = patron.sub(f"{MARCA[0]}\n{tabla_de_ramas()}\n{MARCA[1]}", texto)
    if nuevo == texto:
        return False
    readme.write_text(nuevo, encoding="utf-8")
    cadena._git(repo, "add", "README.md")
    subprocess.run(["git", "commit", "-q", "-m", "Índice de ramas"], cwd=repo, check=True,
                   env={**os.environ, **cadena.FIRMA})
    cadena._git(repo, "push", "-q", "origin", "refs/heads/main:refs/heads/main")
    return True


def correr(lote: int, claves: list[str] | None, carpeta_capturas: pathlib.Path, repo: pathlib.Path,
           extractores: pathlib.Path, publicar: bool, desde_cero: bool = False, avisar=print) -> bool:
    """Procesa una tanda. Devuelve si queda otra igual por hacer: documentos
    sin intentar, cuando la tanda no fue de claves dadas (repetirla con las
    mismas claves no avanzaría nada)."""
    limite = time.monotonic() + MINUTOS_DE_REVISION * 60
    for doc in elegir(lote, claves):
        if time.monotonic() > limite:
            break
        estado = procesar(doc, carpeta_capturas, repo, extractores, publicar, desde_cero)
        guardar_estado(doc["clave"], estado)
        avisar(f"{doc['clave']}: " + (f"publicada, {estado['versiones']} versiones" if estado["publicada"]
                                      else estado.get("motivo", "lista, sin publicar")))
    if publicar:
        publicar_indice(repo)
    return not claves and bool(sin_intentar())
