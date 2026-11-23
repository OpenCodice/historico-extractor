import argparse
import json
import pathlib
import sys

from . import RAIZ, documento
from . import cadena, capturas, coherencia

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
    sp.add_argument("clave")
    sp.add_argument("--out", required=True, type=pathlib.Path)
    sp.add_argument("--json", type=pathlib.Path)

    args = p.parse_args(argv)
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

    pasos = coherencia.medir(args.out, doc["clave"])
    if args.json:
        args.json.write_text(json.dumps(pasos, ensure_ascii=False, indent=1) + "\n")
    print(coherencia.informe(pasos))
    return 1 if any(p["sin_explicar"] for p in pasos) else 0


if __name__ == "__main__":
    sys.exit(main())
