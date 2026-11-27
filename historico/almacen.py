"""La copia propia de los PDF archivados (el Worker `almacen/`, sobre R2).

Cada PDF se guarda por su sha256, el del manifiesto. Leer es público;
guardar pide `HISTORICO_ALMACEN_TOKEN`, y sin él esta parte no hace nada: una
corrida local sigue leyendo del almacén y bajando de Wayback lo que falte.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import pathlib
import time
import urllib.error
import urllib.request

URL = os.environ.get("HISTORICO_ALMACEN", "https://historico-capturas.danielcardeenas.workers.dev")
TOKEN = os.environ.get("HISTORICO_ALMACEN_TOKEN", "")
AGENTE = {"User-Agent": "OpenCodice-historico"}
FALLO_DE_RED = (OSError, http.client.HTTPException)


def _pedir(ruta: str, metodo: str = "GET", datos: bytes | None = None, espera: int = 120) -> bytes | None:
    cabeceras = dict(AGENTE)
    if datos is not None:
        cabeceras |= {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/pdf"}
    pedido = urllib.request.Request(f"{URL}/{ruta}", data=datos, method=metodo, headers=cabeceras)
    try:
        return urllib.request.urlopen(pedido, timeout=espera).read()
    except FALLO_DE_RED:
        return None


def traer(sha256: str) -> bytes | None:
    """El PDF con esa huella, si el almacén lo tiene y entrega justo ese."""
    datos = _pedir(sha256)
    return datos if datos is not None and hashlib.sha256(datos).hexdigest() == sha256 else None


def guardar(datos: bytes) -> bool:
    """Guarda un PDF bajo su huella. Sin token no hace nada. Que el almacén no
    responda no detiene nada: la copia se reintenta en otra corrida."""
    if not TOKEN:
        return False
    return _pedir(hashlib.sha256(datos).hexdigest(), "PUT", datos) is not None


def guardadas() -> set[str]:
    """Las huellas que el almacén ya tiene."""
    huellas, cursor = set(), ""
    while True:
        cuerpo = _pedir(f"lista?cursor={cursor}" if cursor else "lista")
        if cuerpo is None:
            raise RuntimeError("el almacén no entregó su lista")
        pagina = json.loads(cuerpo)
        huellas.update(pagina["huellas"])
        cursor = pagina.get("cursor")
        if not cursor:
            return huellas


def copiar(carpeta: pathlib.Path, minutos: int, avisar=print) -> dict:
    """Lleva al almacén las capturas de todos los manifiestos que aún no tiene,
    del disco o de Wayback, hasta agotar el tiempo. Se puede relanzar."""
    from . import capturas, configuracion

    if not TOKEN:
        raise RuntimeError("falta HISTORICO_ALMACEN_TOKEN")
    limite = time.monotonic() + minutos * 60
    ya = guardadas()
    copiadas = perdidas = faltan = 0
    for clave in (d["clave"] for d in configuracion()["documentos"]):
        for fila in capturas.leer_manifiesto(clave):
            sha = fila.get("sha256")
            if not sha or sha in ya:
                continue
            if time.monotonic() > limite:
                faltan += 1
                continue
            try:
                datos = capturas.asegurar(fila, carpeta / clave).read_bytes()
            except RuntimeError as e:
                perdidas += 1
                avisar(f"{clave}: {e}")
                continue
            if guardar(datos):
                ya.add(sha)
                copiadas += 1
            else:
                faltan += 1
    return {"en_el_almacen": len(ya), "copiadas": copiadas, "sin_copia_en_wayback": perdidas, "faltan": faltan}
