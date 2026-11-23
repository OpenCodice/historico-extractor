"""Compuerta de coherencia: lo que cambia entre dos versiones debe tener causa.

Las compuertas de los extractores miran una versión contra su PDF; un defecto
que se repite igual en el PDF y en el texto (un encabezado colado, una tabla
leída de otro modo) las pasa. Esta mira la cadena: la Cámara anota cada
reforma al pie del artículo con su fecha del DOF, así que un artículo que
cambia de una versión a la siguiente sin una nota de ese periodo no fue
reformado: cambió la lectura.

Un artículo que cambia queda en una de tres clases:
  explicado   alguna versión de la cadena le anota una reforma publicada
              después de la versión anterior y a más tardar en la nueva (los
              PDF antiguos no traen notas: valen las de versiones siguientes);
  solo notas  el texto es idéntico y cambian las líneas de notas (la Cámara
              las agregó o reescribió después);
  solo forma  las mismas palabras en el mismo orden, partidas en otros
              párrafos (una nota nueva corta el párrafo donde antes seguía);
  sin explicar  lo demás.
"""
import pathlib
import re
import subprocess

NOTA = re.compile(r"DOF[^\n]*")
FECHA = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
LINEA_DE_NOTA = re.compile(r"_.*_")


def _git(repo, *args) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


def sin_notas(texto: str) -> str:
    return "\n".join(l for l in texto.splitlines()
                     if l.strip() and not LINEA_DE_NOTA.fullmatch(l.strip()))


def fechas_anotadas(texto: str) -> set[str]:
    return {f"{a}-{m}-{d}" for linea in NOTA.findall(texto) for d, m, a in FECHA.findall(linea)}


def clasificar(estado: str, antes: str, despues: str, anotadas: set[str],
               desde: str, hasta: str) -> str:
    if any(desde < f <= hasta for f in anotadas):
        return "explicado"
    if estado == "M" and sin_notas(antes) == sin_notas(despues):
        return "solo_notas"
    if estado == "M" and sin_notas(antes).split() == sin_notas(despues).split():
        return "solo_forma"
    return "sin_explicar"


def medir(repo: pathlib.Path, rama: str) -> list[dict]:
    """Un paso por cada par de versiones consecutivas de la rama."""
    commits = []
    for h in _git(repo, "rev-list", "--reverse", f"refs/heads/{rama}").split():
        cuerpo = _git(repo, "log", "-1", "--format=%B", h)
        commits.append((h, re.search(r"^Publicacion: (\S+)", cuerpo, re.M)[1]))
    anotadas: dict[str, set[str]] = {}
    for h, _ in commits:
        for ruta in _git(repo, "ls-tree", "-r", "--name-only", h).splitlines():
            if ruta.endswith(".md"):
                anotadas.setdefault(ruta, set()).update(fechas_anotadas(_git(repo, "show", f"{h}:{ruta}")))
    pasos = []
    for (ha, fa), (hb, fb) in zip(commits, commits[1:]):
        paso = {"desde": fa, "hasta": fb, "explicado": [], "solo_notas": [], "solo_forma": [], "sin_explicar": []}
        for linea in _git(repo, "diff", "--name-status", "--no-renames", ha, hb).splitlines():
            estado, ruta = linea.split("\t")
            if not ruta.endswith(".md"):
                continue
            antes = _git(repo, "show", f"{ha}:{ruta}") if estado != "A" else ""
            despues = _git(repo, "show", f"{hb}:{ruta}") if estado != "D" else ""
            clase = clasificar(estado, antes, despues, anotadas.get(ruta, set()), fa, fb)
            paso[clase].append(pathlib.Path(ruta).stem)
        pasos.append(paso)
    return pasos


def informe(pasos: list[dict]) -> str:
    total = {c: sum(len(p[c]) for p in pasos) for c in ("explicado", "solo_notas", "solo_forma", "sin_explicar")}
    limpios = sum(1 for p in pasos if not p["sin_explicar"])
    lineas = [f"pasos: {len(pasos)}  limpios: {limpios}  artículos con reforma anotada: {total['explicado']}"
              f"  solo notas: {total['solo_notas']}  solo forma: {total['solo_forma']}  sin explicar: {total['sin_explicar']}"]
    for p in pasos:
        if p["sin_explicar"]:
            muestra = " ".join(p["sin_explicar"][:14]) + (" …" if len(p["sin_explicar"]) > 14 else "")
            lineas.append(f"  {p['desde']} → {p['hasta']}: {len(p['sin_explicar'])} sin explicar: {muestra}")
    return "\n".join(lineas)
