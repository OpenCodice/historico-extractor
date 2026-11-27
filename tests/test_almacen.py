import hashlib
import json

import pytest

from historico import almacen, capturas

PDF = b"%PDF-1.4 una ley"
SHA = hashlib.sha256(PDF).hexdigest()
FILA = {"archivo": "20200101000000_LEY.pdf", "captura": "20200101000000",
        "url": "http://www.diputados.gob.mx/LeyesBiblio/pdf/LEY.pdf", "sha256": SHA}


def test_asegurar_lee_del_almacen_antes_que_de_wayback(tmp_path, monkeypatch):
    monkeypatch.setattr(almacen, "_pedir", lambda ruta, *a, **k: PDF if ruta == SHA else None)
    monkeypatch.setattr(capturas, "_bajar", lambda url: pytest.fail("no debía ir a Wayback"))
    assert capturas.asegurar(FILA, tmp_path).read_bytes() == PDF


def test_lo_que_baja_de_wayback_se_guarda_en_el_almacen(tmp_path, monkeypatch):
    subidas = []
    monkeypatch.setattr(almacen, "TOKEN", "t")
    monkeypatch.setattr(almacen, "_pedir", lambda ruta, metodo="GET", datos=None, **k: subidas.append((ruta, metodo)) if datos else None)
    monkeypatch.setattr(capturas, "_bajar", lambda url: PDF)
    monkeypatch.setattr(capturas, "PAUSA", 0)
    capturas.asegurar(FILA, tmp_path)
    # Lo que el almacén entrega con otra huella no sirve: se va a Wayback.
    assert almacen.traer(SHA) is None
    assert subidas == [(SHA, "PUT")]


def test_sin_token_no_se_guarda_nada(monkeypatch):
    monkeypatch.setattr(almacen, "_pedir", lambda *a, **k: pytest.fail("no debía pedir nada"))
    assert almacen.guardar(PDF) is False


def test_copiar_lleva_solo_lo_que_falta_y_dice_lo_que_wayback_ya_no_tiene(tmp_path, monkeypatch):
    otro = b"%PDF-1.4 otra ley"
    perdido = "f" * 64
    filas = {"a": [FILA, FILA | {"archivo": "x.pdf", "sha256": hashlib.sha256(otro).hexdigest()}],
             "b": [FILA | {"archivo": "y.pdf", "sha256": perdido}]}
    guardados = {SHA: PDF}

    def pedir(ruta, metodo="GET", datos=None, **k):
        if ruta.startswith("lista"):
            return json.dumps({"huellas": sorted(guardados), "cursor": None}).encode()
        if metodo == "PUT":
            guardados[ruta] = datos
            return b"{}"
        return guardados.get(ruta)

    monkeypatch.setattr(almacen, "TOKEN", "t")
    monkeypatch.setattr(almacen, "_pedir", pedir)
    monkeypatch.setattr("historico.configuracion", lambda: {"documentos": [{"clave": "a"}, {"clave": "b"}]})
    monkeypatch.setattr(capturas, "leer_manifiesto", lambda clave: filas[clave])
    monkeypatch.setattr(capturas, "_bajar", lambda url: otro if "LEY" in url else None)
    monkeypatch.setattr(capturas, "PAUSA", 0)
    monkeypatch.setattr(capturas.time, "sleep", lambda s: None)
    r = almacen.copiar(tmp_path, 5, avisar=lambda m: None)
    assert r == {"en_el_almacen": 2, "copiadas": 1, "sin_copia_en_wayback": 1, "faltan": 0}
