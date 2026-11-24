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
  nota en el cuerpo  lo que cambia es texto de una nota de reforma que una
              versión dejó como texto del artículo; la ley no cambia;
  solo puntuación  las mismas letras y cifras; cambian espacios o signos
              (un guion de fin de renglón, un punto junto al salto de página);
  otro orden  las mismas palabras en otro orden (las celdas de una tabla);
  fórmula     lo que cambia es una fórmula o una tabla: la marca que la
              sustituye apunta a otra página, una versión la lee como texto
              y la otra deja la marca, o cambian restos sueltos de ella (un
              subíndice);
  juzgado     un agente comparó las dos versiones contra sus dos PDF y dejó
              en `verificaciones/<clave>.json` que el cambio es de la fuente;
  sin explicar  lo demás.

Solo la última clase detiene la publicación. «Nota en el cuerpo», «solo
puntuación», «otro orden» y «fórmula»
son lecturas distintas del mismo contenido: pasan, y quedan a la vista en el
informe (`coherencia/<clave>.json`).
"""
import difflib
import hashlib
import json
import pathlib
import re
import subprocess

from . import RAIZ

from . import reedicion

NOTA = re.compile(r"DOF[^\n]*")
FECHA = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
LINEA_DE_NOTA = re.compile(r"_.*_")
ALFANUMERICO = re.compile(r"[^\W_]")
MARCA_DE_FORMULA = re.compile(r"\[(?:Fórmula|Tabla): consultar el PDF oficial, página \d+\]")
FORMULA = "⟦fórmula⟧"
PALABRAS_DE_FORMULA = 40
CLASES = ("explicado", "solo_notas", "solo_forma", "reedicion", "nota_en_el_cuerpo", "solo_puntuacion",
          "otro_orden", "formula",
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
    if solo_formulas(a, b):
        return "formula"
    return None


def solo_formulas(a: str, b: str) -> bool:
    """Cada diferencia es de una fórmula: toca su marca (la misma con otra
    página, o la marca frente a las pocas palabras con que la otra versión
    leyó la fórmula) o son restos sueltos de ella («k», «j=1 i,t−j−1»)."""
    marcada = MARCA_DE_FORMULA.search(a) or MARCA_DE_FORMULA.search(b)
    if not marcada and not ("órmula" in a and "órmula" in b):
        return False
    v, n = (MARCA_DE_FORMULA.sub(f" {FORMULA} ", t).split() for t in (a, b))
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, v, n, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        lados = v[i1:i2], n[j1:j2]
        if any(len(l) > PALABRAS_DE_FORMULA for l in lados):
            return False
        if not any(FORMULA in l for l in lados) and not all(_resto_de_formula(p) for l in lados for p in l):
            return False
    return True


def _resto_de_formula(palabra: str) -> bool:
    """Una variable o un subíndice: una letra suelta que no es palabra, o algo
    con cifras o signos. Nunca una palabra: «no», «o» e «y» cambian lo que
    dice la ley."""
    return (len(palabra) == 1 and palabra.lower() not in "aeouy") or not palabra.isalpha()


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
        # Una sola búsqueda por versión: «<commit>:<ruta>:<renglón con DOF>».
        hallado = subprocess.run(["git", "grep", "-I", "DOF", h, "--", "*.md"],
                                 cwd=repo, capture_output=True, text=True).stdout
        for linea in hallado.splitlines():
            _, ruta, renglon = linea.split(":", 2)
            anotadas.setdefault(ruta, set()).update(fechas_anotadas(renglon))
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
            menor = lectura_menor(antes, despues) if clase == "sin_explicar" and estado == "M" else None
            # El orden de las celdas de una tabla también varía en el texto
            # crudo de cada PDF: ahí la prueba de reedición no distingue nada.
            if menor == "otro_orden":
                clase = menor
            elif clase == "sin_explicar" and texto_de:
                clase = reedicion.clase(antes, despues, texto_de(fuente[ha]),
                                        texto_de(fuente[hb])) or menor or clase
            elif menor:
                clase = menor
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
