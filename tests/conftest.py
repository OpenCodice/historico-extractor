import pytest

from historico import almacen


@pytest.fixture(autouse=True)
def _sin_almacen(monkeypatch):
    """Ninguna prueba habla con el almacén real."""
    monkeypatch.setattr(almacen, "_pedir", lambda *a, **k: None)
    monkeypatch.setattr(almacen, "TOKEN", "")
