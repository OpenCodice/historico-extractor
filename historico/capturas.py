"""Capturas de Wayback del PDF de un documento, cada una con la fecha de su portada.

LeyesBiblio publica cada ley en una sola URL que se sobrescribe con cada
reforma; las versiones anteriores solo sobreviven en las capturas de Wayback.
El manifiesto (`manifiestos/<clave>.tsv`) es la procedencia de cada versión:
qué captura, de qué URL, con qué sha256 y qué «Última reforma» dice su portada.
"""
import hashlib
import pathlib
import re
import time
import urllib.parse
import urllib.request

import pdfplumber

from . import MANIFIESTOS

CDX = "https://web.archive.org/cdx/search/cdx"
CARPETA_PDF = "diputados.gob.mx/LeyesBiblio/pdf/"
COLUMNAS = ("archivo", "captura", "url", "sha256", "bytes", "version", "paginas")
PORTADA = re.compile(
    r"[ÚU]ltimas?\s+[Rr]eformas?\s+(?:publicadas?\s+)?(?:en\s+el\s+)?(?:DOF|D\.O\.F\.)?"
    r"\s*:?\s*(\d{1,2})[-/](\d{1,2})[-/](\d{4})", re.S)
AGENTE = {"User-Agent": "OpenCodice-historico"}


def version_de_portada(texto: str) -> str:
    m = PORTADA.search(texto)
    return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}" if m else ""


def leer_portada(pdf: pathlib.Path) -> tuple[str, int]:
    """(versión, páginas). Wayback trunca algunas capturas a 1 MB: esas no
    abren y quedan sin versión, con el motivo en su lugar."""
    try:
        with pdfplumber.open(pdf) as doc:
            return version_de_portada(doc.pages[0].extract_text() or ""), len(doc.pages)
    except Exception as e:
        return f"ilegible: {type(e).__name__}", 0


def listar(patron: str) -> list[tuple[str, str]]:
    """(captura, url) de cada contenido distinto archivado para ese nombre de archivo."""
    consulta = urllib.parse.urlencode({
        "url": CARPETA_PDF, "matchType": "prefix", "collapse": "digest",
        "fl": "timestamp,original,digest", "filter": "statuscode:200"})
    pedido = urllib.request.Request(f"{CDX}?{consulta}", headers=AGENTE)
    lineas = urllib.request.urlopen(pedido, timeout=300).read().decode().splitlines()
    return filtrar(lineas, patron)


def filtrar(lineas: list[str], patron: str) -> list[tuple[str, str]]:
    nombre = re.compile(patron, re.I)
    vistos, capturas = set(), []
    for linea in lineas:
        partes = linea.split()
        if len(partes) != 3:
            continue
        ts, url, digest = partes
        if nombre.fullmatch(url.rsplit("/", 1)[-1]) and digest not in vistos:
            vistos.add(digest)
            capturas.append((ts, url))
    return sorted(capturas)


def leer_manifiesto(clave: str) -> list[dict]:
    ruta = MANIFIESTOS / f"{clave}.tsv"
    if not ruta.exists():
        return []
    return [dict(zip(COLUMNAS, l.split("\t"))) for l in ruta.read_text().splitlines()[1:]]


def escribir_manifiesto(clave: str, filas: list[dict]) -> None:
    filas = sorted(filas, key=lambda f: f["captura"])
    cuerpo = ["\t".join(COLUMNAS)] + ["\t".join(str(f[c]) for c in COLUMNAS) for f in filas]
    MANIFIESTOS.mkdir(exist_ok=True)
    (MANIFIESTOS / f"{clave}.tsv").write_text("\n".join(cuerpo) + "\n")


def descargar(clave: str, patron: str, destino: pathlib.Path, capturas=None) -> list[dict]:
    """Baja lo que falte y deja el manifiesto al día. Se puede relanzar."""
    destino.mkdir(parents=True, exist_ok=True)
    filas = {f["archivo"]: f for f in leer_manifiesto(clave)}
    for ts, url in capturas if capturas is not None else listar(patron):
        archivo = f"{ts}_{url.rsplit('/', 1)[-1]}"
        ruta = destino / archivo
        if not ruta.exists():
            datos = _bajar(f"https://web.archive.org/web/{ts}id_/{url}")
            if datos is None:
                continue
            ruta.write_bytes(datos)
            time.sleep(4)
        datos = ruta.read_bytes()
        version, paginas = leer_portada(ruta)
        filas[archivo] = {"archivo": archivo, "captura": ts, "url": url,
                          "sha256": hashlib.sha256(datos).hexdigest(), "bytes": len(datos),
                          "version": version, "paginas": paginas}
        escribir_manifiesto(clave, list(filas.values()))
    return list(filas.values())


def _bajar(url: str) -> bytes | None:
    for intento in range(4):
        try:
            datos = urllib.request.urlopen(
                urllib.request.Request(url, headers=AGENTE), timeout=120).read()
            if datos.startswith(b"%PDF"):
                return datos
        except OSError:
            pass
        time.sleep(30 * (intento + 1))
    return None


def versiones(clave: str) -> dict[str, dict]:
    """Versión → su captura más reciente: la Cámara corrige erratas y notas
    sin cambiar la fecha de la portada, y la última captura las trae."""
    elegidas = {}
    for f in leer_manifiesto(clave):
        if re.fullmatch(r"\d{4}-\d\d-\d\d", f["version"]):
            elegidas[f["version"]] = f
    return dict(sorted(elegidas.items()))
