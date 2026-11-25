import argparse
import json
import pathlib
import sys

from . import RAIZ, documento
from . import cadena, capturas, coherencia, declarar, reedicion, tanda

EXTRACTOR = {"constitucion": "constitucion-extractor", "federal": "fiscal-extractor"}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="historico")
    sub = p.add_subparsers(dest="orden", required=True)

    sp = sub.add_parser("capturas", help="baja de Wayback las capturas de un documento y fecha cada una")
    sp.add_argument("clave")
    sp.add_argument("--capturas", default=RAIZ / "capturas", type=pathlib.Path)

    sp = sub.add_parser("cadena", help="reconstruye la rama del documento, un commit por versión")
    sp.add_argument("clave")
    sp.add_argument("--out", required=True, type=pathlib.Path, help="repo de datos del histórico")
    sp.add_argument("--capturas", default=RAIZ / "capturas", type=pathlib.Path)
    sp.add_argument("--extractores", default=RAIZ.parent, type=pathlib.Path,
                    help="carpeta con los clones de constitucion-extractor y fiscal-extractor")
    sp.add_argument("--desde-cero", action="store_true")
    sp.add_argument("--informe", type=pathlib.Path, help="escribe aquí lo que pasó con cada versión")

    sp = sub.add_parser("coherencia", help="compuerta: ningún artículo cambia sin causa")
    sp.add_argument("--extractores", default=RAIZ.parent, type=pathlib.Path)
    sp.add_argument("clave")
    sp.add_argument("--out", required=True, type=pathlib.Path)
    sp.add_argument("--capturas", default=RAIZ / "capturas", type=pathlib.Path)
    sp.add_argument("--json", type=pathlib.Path)

    sp = sub.add_parser("declarar", help="declara las leyes federales del registro vigente")
    sp.add_argument("--registro", required=True, type=pathlib.Path, help="fuentes.json de leyes-federales")
    sp.add_argument("--capturas", default=RAIZ / "capturas", type=pathlib.Path)

    sp = sub.add_parser("tanda", help="procesa unos cuantos documentos de punta a punta")
    sp.add_argument("--lote", type=int, default=40)
    sp.add_argument("--claves", default="", help="claves separadas por espacio; vacío = las que tocan")
    sp.add_argument("--out", required=True, type=pathlib.Path, help="clon de OpenCodice/historico")
    sp.add_argument("--capturas", default=RAIZ / "capturas", type=pathlib.Path)
    sp.add_argument("--extractores", default=RAIZ.parent, type=pathlib.Path)
    sp.add_argument("--publicar", action="store_true", help="empuja las ramas que pasen y el índice")
    sp.add_argument("--desde-cero", action="store_true")

    sp = sub.add_parser("faltantes", help="mide qué versiones le faltan a cada rama publicada")
    sp.add_argument("claves", nargs="*", help="vacío = todas las publicadas")
    sp.add_argument("--out", required=True, type=pathlib.Path, help="clon de OpenCodice/historico")

    args = p.parse_args(argv)
    if args.orden == "faltantes":
        print(tanda.medir_faltantes(args.out, args.claves or None))
        return 0
    if args.orden == "tanda":
        quedan = tanda.correr(args.lote, args.claves.split() or None,
                              args.capturas, args.out, args.extractores, args.publicar, args.desde_cero)
        print(f"pendiente={'true' if quedan else 'false'}")
        return 0
    if args.orden == "declarar":
        leyes, con_numero = declarar.declarar(args.registro, args.capturas / "_indices")
        print(f"{leyes} leyes federales declaradas; {con_numero} con el número de su PDF antiguo")
        return 0
    doc = documento(args.clave)

    if args.orden == "capturas":
        filas = capturas.descargar(doc["clave"], doc["archivos"], args.capturas / doc["clave"])
        con = capturas.versiones(doc["clave"])
        print(f"{doc['clave']}: {len(filas)} capturas, {len(con)} versiones"
              f" ({min(con, default='—')} a {max(con, default='—')}),"
              f" {sum(1 for f in filas if f['version'].startswith('ilegible'))} ilegibles")
        return 0

    if args.orden == "cadena":
        filas = cadena.construir(
            doc, args.capturas / doc["clave"], args.out,
            args.extractores / EXTRACTOR[doc["extractor"]],
            RAIZ / "_trabajo" / doc["clave"], desde_cero=args.desde_cero)
        if args.informe:
            args.informe.write_text(json.dumps(filas, ensure_ascii=False, indent=1) + "\n")
        fuera = [f for f in filas if f["estado"] != "ok"]
        print(f"{doc['clave']}: {len(filas) - len(fuera)} versiones nuevas, {len(fuera)} fuera")
        return 0

    pasos = coherencia.medir(args.out, doc["clave"], reedicion.lector(
        doc["clave"], args.capturas,
        args.extractores / EXTRACTOR["federal"] if doc["extractor"] == "federal" else None))
    if args.json:
        args.json.write_text(json.dumps(pasos, ensure_ascii=False, indent=1) + "\n")
    print(coherencia.informe(pasos))
    return 1 if any(p["sin_explicar"] for p in pasos) else 0


if __name__ == "__main__":
    sys.exit(main())
