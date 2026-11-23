"""Prueba de que un cambio sin reforma viene de la fuente y no de la lectura.

La Cámara reedita sus PDF sin que medie reforma: cambia «A.-» por «A)»,
«ley» por «Ley», agrega una coma. Las dos versiones son entonces fieles, cada
una a su PDF. Se demuestra sin juzgar nada: cada tramo que cambió, con unas
palabras de contexto, debe estar literal en el PDF de su versión y no estar
en el de la otra. Si el tramo está en ambos PDF, o en ninguno, lo que cambió
fue la lectura y no hay prueba.
"""
import collections
import difflib
import pathlib
import re

import pdfplumber

CONTEXTO = 3
VENTANA = 12
BORDE = 6
ROTULO = re.compile(r"#.*")


def normalizar(texto: str) -> str:
    return " ".join(texto.split())


def sin_mobiliario(paginas: list[str]) -> str:
    """El texto corrido, sin lo que se repite en el borde de las páginas
    (membrete, título, «N de M»): ahí es donde un párrafo que cruza de página
    deja de ser literal."""
    def forma(linea: str) -> str:
        return re.sub(r"\d+", "#", linea.strip())

    renglones = [[l for l in p.splitlines() if l.strip()] for p in paginas]
    borde = lambda r: r[:BORDE] + r[-BORDE:]
    veces = collections.Counter(f for r in renglones for f in {forma(l) for l in borde(r)})
    repetidas = {f for f, n in veces.items() if n >= max(3, len(paginas) // 4)}
    limpio = []
    for r in renglones:
        limpio += [l for i, l in enumerate(r)
                   if not ((i < BORDE or i >= len(r) - BORDE) and forma(l) in repetidas)]
    return normalizar(" ".join(limpio))


def texto_del_pdf(pdf: pathlib.Path, cache: pathlib.Path) -> str:
    """El texto del PDF en una sola línea. Tarda; se guarda por nombre de captura."""
    guardado = cache / f"{pdf.stem}.txt"
    if guardado.exists():
        return guardado.read_text()
    with pdfplumber.open(pdf) as doc:
        texto = sin_mobiliario([p.extract_text() or "" for p in doc.pages])
    cache.mkdir(parents=True, exist_ok=True)
    guardado.write_text(texto)
    return texto


def palabras(articulo: str) -> list[str]:
    """Las palabras del cuerpo, sin el rótulo ni las notas (que se miden aparte)."""
    from .coherencia import sin_notas
    return " ".join(l for l in sin_notas(articulo).splitlines()
                    if not ROTULO.fullmatch(l.strip())).split()


def _ventanas(seq: list[str], ini: int, fin: int) -> list[str]:
    """El tramo [ini, fin) con su contexto, partido en trozos que quepan en una
    búsqueda literal: un tramo largo cruza saltos de página, donde el PDF
    intercala su encabezado."""
    a, b = max(0, ini - CONTEXTO), min(len(seq), fin + CONTEXTO)
    if b - a <= VENTANA:
        return [" ".join(seq[a:b])]
    return [" ".join(seq[i:i + VENTANA]) for i in range(a, b - VENTANA + 1, VENTANA // 2)]


def es_de_la_fuente(antes: str, despues: str, pdf_antes: str, pdf_despues: str) -> bool:
    """Cierto si cada diferencia entre las dos versiones está, literal, en su
    propio PDF y falta en el otro."""
    v, n = palabras(antes), palabras(despues)
    tramos = [op for op in difflib.SequenceMatcher(None, v, n, autojunk=False).get_opcodes()
              if op[0] != "equal"]
    if not tramos:
        return False
    for _, i1, i2, j1, j2 in tramos:
        viejas, nuevas = _ventanas(v, i1, i2), _ventanas(n, j1, j2)
        if not all(t in pdf_antes for t in viejas) or not all(t in pdf_despues for t in nuevas):
            return False
        if all(t in pdf_despues for t in viejas) or all(t in pdf_antes for t in nuevas):
            return False
    return True
