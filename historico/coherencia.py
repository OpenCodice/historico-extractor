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
  reedición   cambió sin reforma, y cada diferencia está literal en el PDF
              de su versión y falta en el de la otra: lo cambió la Cámara
              (ver reedicion.py);
  solo puntuación  las mismas letras y cifras; cambian espacios o signos
              (un guion de fin de renglón, un punto junto al salto de página);
  otro orden  las mismas palabras en otro orden (las celdas de una tabla);
  juzgado     un agente comparó las dos versiones contra sus dos PDF y dejó
              en `verificaciones/<clave>.json` que el cambio es de la fuente;
  sin explicar  lo demás.

Solo la última clase detiene la publicación. «Solo puntuación» y «otro orden»
son lecturas distintas del mismo contenido: pasan, y quedan a la vista en el
informe (`coherencia/<clave>.json`).
"""
import hashlib
import json
import pathlib
import re
import subprocess

from . import RAIZ

from .reedicion import es_de_la_fuente

NOTA = re.compile(r"DOF[^\n]*")
FECHA = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
LINEA_DE_NOTA = re.compile(r"_.*_")
ALFANUMERICO = re.compile(r"[^\W_]")
CLASES = ("explicado", "solo_notas", "solo_forma", "reedicion", "solo_puntuacion", "otro_orden",
          "juzgado", "sin_explicar")


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


def lectura_menor(antes: str, despues: str) -> str | None:
    a, b = sin_notas(antes), sin_notas(despues)
    if ALFANUMERICO.findall(a) == ALFANUMERICO.findall(b):
        return "solo_puntuacion"
    if sorted(a.split()) == sorted(b.split()):
        return "otro_orden"
    return None


def blob(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()[:16]


def veredictos(clave: str) -> dict[tuple[str, str], str]:
    """(antes, después) → veredicto, por el contenido exacto de las dos
    versiones del artículo: si cambia la extracción, el juicio ya no aplica."""
    ruta = RAIZ / "verificaciones" / f"{clave}.json"
    if not ruta.exists():
        return {}
    return {(v["antes"], v["despues"]): v["veredicto"] for v in json.loads(ruta.read_text())}


def medir(repo: pathlib.Path, rama: str, texto_de=None) -> list[dict]:
    """Un paso por cada par de versiones consecutivas de la rama. `texto_de`
    da el texto del PDF de una versión por su sha256; sin él no se buscan
    reediciones."""
    commits, fuente = [], {}
    for h in _git(repo, "rev-list", "--reverse", f"refs/heads/{rama}").split():
        cuerpo = _git(repo, "log", "-1", "--format=%B", h)
        commits.append((h, re.search(r"^Publicacion: (\S+)", cuerpo, re.M)[1]))
        fuente[h] = re.search(r"^Fuente-Sha256: (\S+)", cuerpo, re.M)[1]
    anotadas: dict[str, set[str]] = {}
    for h, _ in commits:
        for ruta in _git(repo, "ls-tree", "-r", "--name-only", h).splitlines():
            if ruta.endswith(".md"):
                anotadas.setdefault(ruta, set()).update(fechas_anotadas(_git(repo, "show", f"{h}:{ruta}")))
    juicios = veredictos(rama)
    pasos = []
    for (ha, fa), (hb, fb) in zip(commits, commits[1:]):
        paso = {"desde": fa, "hasta": fb, "fuente_antes": fuente[ha], "fuente_despues": fuente[hb],
                "pendientes": []} | {c: [] for c in CLASES}
        for linea in _git(repo, "diff", "--name-status", "--no-renames", ha, hb).splitlines():
            estado, ruta = linea.split("\t")
            if not ruta.endswith(".md"):
                continue
            antes = _git(repo, "show", f"{ha}:{ruta}") if estado != "A" else ""
            despues = _git(repo, "show", f"{hb}:{ruta}") if estado != "D" else ""
            clase = clasificar(estado, antes, despues, anotadas.get(ruta, set()), fa, fb)
            if clase == "sin_explicar" and estado == "M" and texto_de and es_de_la_fuente(
                    antes, despues, texto_de(fuente[ha]), texto_de(fuente[hb])):
                clase = "reedicion"
            if clase == "sin_explicar" and estado == "M":
                clase = lectura_menor(antes, despues) or clase
            if clase == "sin_explicar" and juicios.get((blob(antes), blob(despues))) == "fuente":
                clase = "juzgado"
            paso[clase].append(pathlib.Path(ruta).stem)
            if clase == "sin_explicar":
                paso["pendientes"].append({"articulo": pathlib.Path(ruta).stem,
                                           "antes": blob(antes), "despues": blob(despues)})
        pasos.append(paso)
    return pasos


def informe(pasos: list[dict]) -> str:
    total = {c: sum(len(p[c]) for p in pasos) for c in CLASES}
    limpios = sum(1 for p in pasos if not p["sin_explicar"])
    lineas = [f"pasos: {len(pasos)}  limpios: {limpios}  "
              + "  ".join(f"{c.replace('_', ' ')}: {total[c]}" for c in CLASES)]
    for p in pasos:
        if p["sin_explicar"]:
            muestra = " ".join(p["sin_explicar"][:14]) + (" …" if len(p["sin_explicar"]) > 14 else "")
            lineas.append(f"  {p['desde']} → {p['hasta']}: {len(p['sin_explicar'])} sin explicar: {muestra}")
    return "\n".join(lineas)
