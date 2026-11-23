"""Prueba de que un cambio sin reforma viene de la fuente y no de la lectura.

La Cámara reedita sus PDF sin que medie reforma: cambia «A.-» por «A)»,
«ley» por «Ley», agrega una coma. Las dos versiones son entonces fieles, cada
una a su PDF. Se demuestra sin juzgar nada: cada tramo que cambió, con unas
palabras de contexto, debe estar literal en el PDF de su versión, y al menos
una de las dos redacciones debe faltar en el PDF de la otra. Si las dos están
en ambos PDF, o alguna no está en el suyo, lo que cambió fue la lectura y no
hay prueba.
"""
import collections
import difflib
import pathlib
import re

import pdfplumber

CONTEXTO = (3, 8, 16)
VENTANA = 12
BORDE = 6
HUECO = 600
NOTAS_INTERCALADAS = 3
ROTULO = re.compile(r"#.*")
NOTA_DOF = re.compile(r"DOF \d{2}-\d{2}-\s?\d{4}")


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


def lector(clave: str, capturas: pathlib.Path):
    """sha256 de una captura → el texto de su PDF, bajándola si hace falta."""
    from . import RAIZ
    from .capturas import asegurar, leer_manifiesto
    por_sha = {f["sha256"]: f for f in leer_manifiesto(clave)}
    textos = {}

    def texto_de(sha: str) -> str:
        if sha not in textos:
            textos[sha] = texto_del_pdf(asegurar(por_sha[sha], capturas / clave),
                                        RAIZ / "_trabajo" / "texto")
        return textos[sha]
    return texto_de


def palabras(articulo: str) -> list[str]:
    """Las palabras del cuerpo, sin el rótulo ni las notas (que se miden aparte)."""
    from .coherencia import sin_notas
    return " ".join(l for l in sin_notas(articulo).splitlines()
                    if not ROTULO.fullmatch(l.strip())).split()


def _ventanas(seq: list[str], ini: int, fin: int, contexto: int) -> list[str]:
    """El tramo [ini, fin) con su contexto, partido en trozos que quepan en una
    búsqueda literal: un tramo largo cruza saltos de página, donde el PDF
    intercala su encabezado."""
    a, b = max(0, ini - contexto), min(len(seq), fin + contexto)
    if b - a <= VENTANA:
        return [" ".join(seq[a:b])]
    return [" ".join(seq[i:i + VENTANA]) for i in range(a, b - VENTANA + 1, VENTANA // 2)]


def esta(ventana: str, pdf: str) -> bool:
    """La ventana está en el PDF, literal o con notas intercaladas: el PDF
    trae cada nota de reforma en el punto del texto que anota, y el artículo
    extraído las lleva aparte."""
    return ventana in pdf or any(
        _sigue(ventana.split(), pdf, m.end(), NOTAS_INTERCALADAS)
        for m in re.finditer(re.escape(" ".join(ventana.split()[:2])), pdf))


def _sigue(w: list[str], pdf: str, fin: int, notas: int) -> bool:
    """`w[:2]` termina en `fin`; el resto sigue ahí mismo o tras una nota."""
    resto = w[2:]
    while resto and pdf.startswith(" " + resto[0], fin):
        fin += 1 + len(resto[0])
        resto = resto[1:]
    if not resto:
        return True
    if not notas:
        return False
    cabeza = " ".join(resto[:2])
    desde = pdf.find(cabeza, fin, fin + HUECO)
    while desde != -1:
        if "DOF" in pdf[fin:desde] and _sigue(resto[-2:] if len(resto) < 2 else resto, pdf,
                                              desde + len(cabeza), notas - 1):
            return True
        desde = pdf.find(cabeza, desde + 1, fin + HUECO)
    return False


def clase(antes: str, despues: str, pdf_antes: str, pdf_despues: str) -> str | None:
    """'reedicion' si cada diferencia entre las dos versiones es de la fuente;
    'nota_en_el_cuerpo' si además alguna es texto de una nota de reforma que
    una versión dejó en el cuerpo (el texto de la ley no cambia); None si
    alguna diferencia no se puede probar."""
    v, n = palabras(antes), palabras(despues)
    notas_antes, notas_despues = _notas(antes), _notas(despues)
    tramos = [op for op in difflib.SequenceMatcher(None, v, n, autojunk=False).get_opcodes()
              if op[0] != "equal"]
    notas = 0
    for _, i1, i2, j1, j2 in tramos:
        if (_es_nota(v[i1:i2], pdf_antes, notas_despues) and _es_nota(n[j1:j2], pdf_despues, notas_antes)
                and (i2 > i1 or j2 > j1)):
            notas += 1
            continue
        if not _probado(v, i1, i2, n, j1, j2, pdf_antes, pdf_despues):
            return None
    if not tramos:
        return None
    return "nota_en_el_cuerpo" if notas else "reedicion"


def _probado(v, i1, i2, n, j1, j2, pdf_antes, pdf_despues) -> bool:
    """El tramo está literal en el PDF de su versión y alguna de las dos
    redacciones falta en el PDF ajeno. Una frase corta puede repetirse en otro
    artículo del otro PDF: entonces se prueba con más contexto y, si la frase
    entera está repetida en otro artículo, contando: la redacción vieja debe
    aparecer más veces en su PDF que en el ajeno, y la nueva también. Si no,
    los PDF no distinguen las versiones."""
    for contexto in CONTEXTO:
        viejas, nuevas = _ventanas(v, i1, i2, contexto), _ventanas(n, j1, j2, contexto)
        if not all(esta(t, pdf_antes) for t in viejas) or not all(esta(t, pdf_despues) for t in nuevas):
            return False
        if not (all(esta(t, pdf_despues) for t in viejas) and all(esta(t, pdf_antes) for t in nuevas)):
            return True
    de_mas = [any(suyo.count(t) > ajeno.count(t) for t in ventanas)
              for ventanas, suyo, ajeno, hay in ((viejas, pdf_antes, pdf_despues, i2 > i1),
                                                 (nuevas, pdf_despues, pdf_antes, j2 > j1)) if hay]
    return all(de_mas)


def _notas(articulo: str) -> str:
    """Las líneas de notas del artículo, en un solo renglón."""
    from .coherencia import LINEA_DE_NOTA
    return normalizar(" ".join(l for l in articulo.splitlines() if LINEA_DE_NOTA.fullmatch(l.strip())))


def _es_nota(tramo: list[str], pdf: str, notas_de_la_otra: str) -> bool:
    """Un tramo vacío, o texto literal del PDF que cita su reforma en el DOF
    o que la otra versión lleva entre sus notas."""
    texto = " ".join(tramo)
    return not tramo or (texto in pdf and (bool(NOTA_DOF.search(texto)) or texto in notas_de_la_otra))


def es_de_la_fuente(antes: str, despues: str, pdf_antes: str, pdf_despues: str) -> bool:
    return clase(antes, despues, pdf_antes, pdf_despues) == "reedicion"
