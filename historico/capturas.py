"""Capturas de Wayback del PDF de un documento, cada una con la fecha de su portada.

LeyesBiblio publica cada ley en una sola URL que se sobrescribe con cada
reforma; las versiones anteriores solo sobreviven en las capturas de Wayback.
El manifiesto (`manifiestos/<clave>.tsv`) es la procedencia de cada versión:
qué captura, de qué URL, con qué sha256 y qué «Última reforma» dice su portada.
"""
import hashlib
import http.client
import pathlib
import re
import time
import urllib.parse
import urllib.request

import pdfplumber

from . import MANIFIESTOS, configuracion

CDX = "https://web.archive.org/cdx/search/cdx"
CARPETA_PDF = "diputados.gob.mx/LeyesBiblio/pdf/"
COLUMNAS = ("archivo", "captura", "url", "sha256", "bytes", "version", "paginas", "origen")
PORTADA = re.compile(
    r"[ÚU]ltimas?\s+[Rr]eformas?\s+(?:publicadas?\s+)?(?:en\s+el\s+)?(?:DOF|D\.O\.F\.)?"
    r"\s*:?\s*(\d{1,2})[-/](\d{1,2})[-/](\d{4})", re.S)
AGENTE = {"User-Agent": "OpenCodice-historico"}
PAUSA = 4
FALLO_DE_RED = (OSError, http.client.HTTPException)


MESES = {m: n for n, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), 1)}
ORIGEN = re.compile(
    r"publicad[oa]s?\s+en\s+el\s+Diario\s+Oficial\s+de\s+la\s+Federación\s+(?:el\s+(?:día\s+)?)?"
    r"(\d{1,2})\s*[º°o]?\.?\s+de\s+([a-z]+)\s+de\s+(\d{4})", re.I)


def version_de_portada(texto: str) -> str:
    """La fecha de la última reforma; una ley sin reformas está en la versión
    de su publicación."""
    m = PORTADA.search(texto)
    return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}" if m else origen_de_portada(texto)


def origen_de_portada(texto: str) -> str:
    """Cuándo se publicó la ley. Distingue a una ley de la que abrogó con el
    mismo nombre y, a veces, el mismo archivo (la LISR de 2002 y la de 2013)."""
    m = ORIGEN.search(texto)
    if not m or m[2].lower() not in MESES:
        return ""
    return f"{m[3]}-{MESES[m[2].lower()]:02d}-{int(m[1]):02d}"


def leer_portada(pdf: pathlib.Path) -> tuple[str, int, str]:
    """(versión, páginas, origen). Wayback trunca algunas capturas a 1 MB: esas
    no abren y quedan sin versión, con el motivo en su lugar."""
    try:
        with pdfplumber.open(pdf) as doc:
            portada = doc.pages[0].extract_text() or ""
            return version_de_portada(portada), len(doc.pages), origen_de_portada(portada)
    except Exception as e:
        return f"ilegible: {type(e).__name__}", 0, ""


def listar(patron: str, cache: pathlib.Path | None = None) -> list[tuple[str, str]]:
    """(captura, url) de cada contenido distinto archivado para ese nombre de
    archivo. El listado es el de toda la carpeta de PDF de LeyesBiblio; con
    `cache` se pide una vez al día y sirve para todos los documentos."""
    if cache and cache.exists() and time.time() - cache.stat().st_mtime < 86400:
        return filtrar(cache.read_text().splitlines(), patron)
    consulta = urllib.parse.urlencode({
        "url": CARPETA_PDF, "matchType": "prefix", "collapse": "digest",
        "fl": "timestamp,original,digest", "filter": "statuscode:200"})
    pedido = urllib.request.Request(f"{CDX}?{consulta}", headers=AGENTE)
    for intento in range(4):
        try:
            texto = urllib.request.urlopen(pedido, timeout=300).read().decode()
            break
        except FALLO_DE_RED:
            if intento == 3:
                raise
            time.sleep(30 * (intento + 1))
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(texto)
    return filtrar(texto.splitlines(), patron)


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
    cuerpo = ["\t".join(COLUMNAS)] + ["\t".join(str(f.get(c, "")) for c in COLUMNAS) for f in filas]
    MANIFIESTOS.mkdir(exist_ok=True)
    (MANIFIESTOS / f"{clave}.tsv").write_text("\n".join(cuerpo) + "\n")


def descargar(clave: str, patron: str, destino: pathlib.Path, capturas=None) -> list[dict]:
    """Deja el manifiesto al día: baja y fecha las capturas que aún no están
    en él. Las ya registradas no se vuelven a pedir (`asegurar` las trae si
    hacen falta). Se puede relanzar."""
    destino.mkdir(parents=True, exist_ok=True)
    filas = {f["archivo"]: f for f in leer_manifiesto(clave)}
    for ts, url in capturas if capturas is not None else listar(patron, destino.parent / "_cdx.txt"):
        archivo = f"{ts}_{url.rsplit('/', 1)[-1]}"
        ruta = destino / archivo
        if archivo in filas and "origen" in filas[archivo]:
            continue
        if not ruta.exists():
            datos = _bajar(f"https://web.archive.org/web/{ts}id_/{url}")
            if datos is None:
                continue
            ruta.write_bytes(datos)
            time.sleep(PAUSA)
        datos = ruta.read_bytes()
        version, paginas, origen = leer_portada(ruta)
        filas[archivo] = {"archivo": archivo, "captura": ts, "url": url,
                          "sha256": hashlib.sha256(datos).hexdigest(), "bytes": len(datos),
                          "version": version, "paginas": paginas, "origen": origen}
        escribir_manifiesto(clave, list(filas.values()))
    return list(filas.values())


def asegurar(fila: dict, destino: pathlib.Path) -> pathlib.Path:
    """El PDF de una captura del manifiesto, bajándolo si no está en disco.
    Tiene que ser el mismo que se fechó: se comprueba su sha256."""
    ruta = destino / fila["archivo"]
    if not ruta.exists():
        datos = _bajar(f"https://web.archive.org/web/{fila['captura']}id_/{fila['url']}")
        if datos is None or hashlib.sha256(datos).hexdigest() != fila["sha256"]:
            raise RuntimeError(f"{fila['archivo']}: Wayback ya no entrega la captura registrada")
        destino.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(datos)
        time.sleep(PAUSA)
    return ruta


def _bajar(url: str) -> bytes | None:
    for intento in range(4):
        try:
            datos = urllib.request.urlopen(
                urllib.request.Request(url, headers=AGENTE), timeout=120).read()
            if datos.startswith(b"%PDF"):
                return datos
        except FALLO_DE_RED:
            pass
        time.sleep(30 * (intento + 1))
    return None


def versiones(clave: str) -> dict[str, dict]:
    """Versión → su captura más reciente: la Cámara corrige erratas y notas
    sin cambiar la fecha de la portada, y la última captura las trae. Solo
    cuentan las capturas de la ley vigente: las de otra con otro día de
    publicación son de la ley que esta abrogó. Las versiones declaradas en
    `versiones_fuera` no entran: su lectura no es fiel al PDF."""
    filas = [f for f in leer_manifiesto(clave) if re.fullmatch(r"\d{4}-\d\d-\d\d", f["version"])]
    vigente = next((f["origen"] for f in reversed(filas) if f.get("origen")), "")
    elegidas = {}
    for f in filas:
        if f.get("origen", "") in ("", vigente):
            elegidas[f["version"]] = f
    fuera = configuracion().get("versiones_fuera", {}).get(clave, {})
    return dict(sorted((v, f) for v, f in elegidas.items() if v not in fuera))
