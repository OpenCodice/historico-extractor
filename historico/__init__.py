"""Reconstruye las versiones anteriores de una ley desde los PDF archivados."""
import json
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent
MANIFIESTOS = RAIZ / "manifiestos"


def configuracion() -> dict:
    return json.loads((RAIZ / "documentos.json").read_text(encoding="utf-8"))


def documento(clave: str) -> dict:
    for d in configuracion()["documentos"]:
        if d["clave"] == clave:
            return d
    raise SystemExit(f"{clave}: no está declarado en documentos.json")
