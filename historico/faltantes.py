"""Qué versiones le faltan a una rama.

El histórico solo tiene las versiones del PDF que alguien archivó. La Cámara
anota al pie de cada artículo todas las fechas del DOF en que se reformó, así
que una fecha anotada que no es la de ninguna versión de la rama es una
publicación cuyo texto no se capturó: la ley cambió ese día y la rama pasa de
la versión anterior a la siguiente sin ella.
"""
import pathlib
import re
import subprocess

from . import cadena
from .coherencia import FECHA, LINEA_DE_NOTA

DOF = re.compile(r"DOF[^\n]*")


def anotadas(repo: pathlib.Path, rama: str) -> set[str]:
    """Las fechas del DOF que anota alguna nota de alguna versión de la rama.
    Solo las notas: el texto de un artículo también puede citar un DOF."""
    fechas: set[str] = set()
    for h in cadena._git(repo, "rev-list", f"refs/heads/{rama}").split():
        hallado = subprocess.run(["git", "grep", "-I", "-h", "DOF", h, "--", "*.md"],
                                 cwd=repo, capture_output=True, text=True).stdout
        for renglon in hallado.splitlines():
            if LINEA_DE_NOTA.fullmatch(renglon.strip()):
                fechas.update(f"{a}-{m}-{d}" for cita in DOF.findall(renglon) for d, m, a in FECHA.findall(cita))
    return fechas


def medir(repo: pathlib.Path, rama: str) -> dict:
    """`faltan`: las publicaciones posteriores a la primera versión que no
    tienen versión propia. `anteriores`: cuántas hubo antes de la primera."""
    versiones = {t["Publicacion"] for t in cadena._hechas(repo, rama)}
    primera = min(versiones)
    fechas = anotadas(repo, rama)
    return {"faltan": sorted(f for f in fechas if f > primera and f not in versiones),
            "anteriores": sum(f < primera for f in fechas)}
