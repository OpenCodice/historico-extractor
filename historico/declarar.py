"""Declara en `documentos.json` las leyes federales del registro vigente.

Lo único que el registro vigente no dice de una ley es cómo se llamó antes su
PDF. LeyesBiblio numeraba los archivos (`125.pdf`, luego `125_120615.pdf`) y
hacia 2021 pasó a nombrarlos por sigla (`LFT.pdf`); las leyes más recientes
nacieron ya con sigla. El número sale de los índices de LeyesBiblio que
guardó Wayback: en cada fila, el enlace al PDF numerado acompaña al enlace
`ref/<sigla>.htm` o al nombre de la ley.
"""
import collections
import html
import json
import pathlib
import re
import time
import unicodedata
import urllib.request

from . import RAIZ
from .capturas import AGENTE, FALLO_DE_RED

INDICE = "http://www.diputados.gob.mx/LeyesBiblio/index.htm"
ANIOS = range(2007, 2023)
CARPETA_PDF = "/LeyesBiblio/pdf/"


def _normal(texto: str) -> str:
    sin_acentos = "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                          if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", sin_acentos).split())


def indices(cache: pathlib.Path) -> list[str]:
    """Un índice por año, de la captura más cercana al 1 de junio. Un año sin
    captura útil se salta: los demás bastan para ver cada número."""
    cache.mkdir(parents=True, exist_ok=True)
    paginas = []
    for anio in ANIOS:
        ruta = cache / f"{anio}.htm"
        if not ruta.exists():
            pedido = urllib.request.Request(
                f"https://web.archive.org/web/{anio}0601000000id_/{INDICE}", headers=AGENTE)
            try:
                datos = urllib.request.urlopen(pedido, timeout=120).read()
            except FALLO_DE_RED:
                datos = b""
            ruta.write_bytes(datos if b'href="pdf/' in datos else b"")
            time.sleep(3)
        paginas.append(ruta.read_text(encoding="latin1"))
    if sum(1 for p in paginas if p) < len(ANIOS) // 2:
        raise SystemExit("muy pocos índices de LeyesBiblio en Wayback para ligar los números")
    return paginas


def numeros(paginas: list[str], leyes: list[dict]) -> dict[str, list[str]]:
    """sigla → números que tuvo su PDF. Una fila que nombra dos leyes o dos
    números no decide nada y se ignora."""
    por_sigla = {l["sigla"].lower(): l["sigla"] for l in leyes}
    por_nombre = sorted(((_normal(l["etiqueta"]), l["sigla"]) for l in leyes),
                        key=lambda par: -len(par[0]))
    hallados = collections.defaultdict(set)
    for pagina in paginas:
        for fila in re.split(r"(?i)<tr\b", pagina):
            nums = set(re.findall(r'(?i)href="pdf/(\d+)(?:_\d{6})?\.pdf"', fila))
            if len(nums) != 1:
                continue
            refs = {r.lower() for r in re.findall(r'(?i)href="ref/([\w-]+)\.htm"', fila)}
            sigla = por_sigla.get(next(iter(refs))) if len(refs) == 1 else None
            if not sigla:
                texto = f" {_normal(html.unescape(re.sub(r'<[^>]+>', ' ', fila)))} "
                sigla = next((s for nombre, s in por_nombre if f" {nombre} " in texto), None)
            if sigla:
                hallados[sigla] |= nums
    de_quien = collections.Counter(n for nums in hallados.values() for n in nums)
    return {s: sorted(n for n in nums if de_quien[n] == 1) for s, nums in hallados.items()}


def entradas(leyes: list[dict], numeros_de: dict[str, list[str]]) -> list[dict]:
    salida = []
    for ley in leyes:
        if ley.get("estado") != "incluida" or CARPETA_PDF not in (ley.get("url") or ""):
            continue
        nombres = [re.escape(ley["url"].rsplit("/", 1)[-1][:-4])] + numeros_de.get(ley["sigla"], [])
        salida.append({
            "clave": ley["clave"], "extractor": "federal", "sigla": ley["sigla"],
            "etiqueta": ley["etiqueta"], "tipo": ley["tipo"], "url": ley["url"],
            "archivos": f"({'|'.join(nombres)})(_\\d{{6}})?\\.pdf",
        })
    return salida


def declarar(registro: pathlib.Path, cache: pathlib.Path) -> tuple[int, int]:
    """Reescribe las entradas federales de documentos.json. Devuelve (leyes, con número)."""
    leyes = json.loads(registro.read_text(encoding="utf-8"))["documentos"]
    numeros_de = numeros(indices(cache), leyes)
    nuevas = entradas(leyes, numeros_de)
    ruta = RAIZ / "documentos.json"
    config = json.loads(ruta.read_text(encoding="utf-8"))
    config["documentos"] = [d for d in config["documentos"] if d["extractor"] != "federal"] + nuevas
    ruta.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(nuevas), sum(1 for e in nuevas if e["sigla"] in numeros_de)
