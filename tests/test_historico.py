import re

from historico import cadena, capturas, coherencia, configuracion, reedicion


def test_la_portada_da_la_version():
    assert capturas.version_de_portada("Últimas Reformas DOF 07-04-2006") == "2006-04-07"
    assert capturas.version_de_portada("Última reforma publicada DOF 30-11-2012") == "2012-11-30"
    assert capturas.version_de_portada("TEXTO VIGENTE\nNueva Ley publicada") == ""


def test_una_captura_por_contenido_y_solo_los_archivos_del_documento():
    lineas = [
        "20060813201302 http://www.diputados.gob.mx:80/LeyesBiblio/pdf/1.pdf AAA",
        "20061019143458 http://www.diputados.gob.mx:80/LeyesBiblio/pdf/1.pdf AAA",
        "20150701000000 http://www.diputados.gob.mx/LeyesBiblio/pdf/1_100715.pdf BBB",
        "20240101000000 https://www.diputados.gob.mx/LeyesBiblio/pdf/CPEUM.pdf CCC",
        "20240101000000 https://www.diputados.gob.mx/LeyesBiblio/pdf/125.pdf DDD",
        "20240101000000 https://www.diputados.gob.mx/LeyesBiblio/pdf/11.pdf EEE",
    ]
    patron = next(d["archivos"] for d in configuracion()["documentos"] if d["clave"] == "cpeum")
    assert [ts for ts, _ in capturas.filtrar(lineas, patron)] == [
        "20060813201302", "20150701000000", "20240101000000"]


def test_los_encabezados_antiguos_son_ruido_y_el_texto_no():
    patrones = [re.compile(p) for p in cadena.patrones_de_ruido(configuracion()["encabezados_antiguos"])]
    es_ruido = lambda s: any(p.match(s) for p in patrones)
    assert es_ruido("Cámara de Diputados del H. Congreso de la Unión Última Reforma DOF 07-04-2006")
    assert es_ruido("Centro de Documentación, Información y Análisis")
    assert es_ruido("Dirección General de Servicios de Documentación, Información y Análisis")
    assert not es_ruido("Centro de Documentación, Información y Análisis de la Cámara, que deberá")
    assert not es_ruido("la Cámara de Diputados del H. Congreso de la Unión")


def test_un_cambio_con_nota_de_ese_periodo_esta_explicado():
    anotadas = coherencia.fechas_anotadas("_Párrafo reformado DOF 10-06-2011, 15-09-2017_")
    assert anotadas == {"2011-06-10", "2017-09-15"}
    assert coherencia.clasificar("M", "a", "b", anotadas, "2011-05-01", "2011-06-10") == "explicado"
    assert coherencia.clasificar("M", "a", "b", anotadas, "2011-06-10", "2012-01-01") == "sin_explicar"


def test_si_solo_cambian_las_notas_no_es_una_reforma():
    antes = "# Artículo 5\n\nTexto del artículo."
    despues = "# Artículo 5\n\nTexto del artículo.\n\n_Artículo reformado DOF 31-12-1974_"
    assert coherencia.clasificar("M", antes, despues, {"1974-12-31"}, "2006-01-17", "2012-04-09") == "solo_notas"
    assert coherencia.clasificar("M", antes, despues + "\n\nMás texto.", {"1974-12-31"},
                                 "2006-01-17", "2012-04-09") == "sin_explicar"


def test_el_mensaje_lleva_la_procedencia_de_la_captura():
    doc = {"clave": "lft", "sigla": "LFT", "extractor": "federal"}
    fila = {"version": "2012-11-30", "captura": "20130101000000", "sha256": "abc",
            "url": "http://www.diputados.gob.mx/LeyesBiblio/pdf/125.pdf"}
    m = cadena.mensaje(doc, fila, "38ac6e0", {"A": ["015-a"], "M": ["002", "003"], "D": []})
    assert m.splitlines()[0] == "Versión LFT (DOF 2012-11-30)"
    assert "Articulos-Adicionados: 015-a" in m and "Articulos-Modificados: 002, 003" in m
    assert "Articulos-Retirados" not in m
    assert "Fuente: https://web.archive.org/web/20130101000000id_/http://www.diputados.gob.mx/LeyesBiblio/pdf/125.pdf" in m
    assert "Extractor: OpenCodice/fiscal-extractor@38ac6e0" in m


def test_las_mismas_palabras_en_otros_parrafos_no_son_una_reforma():
    antes = "# Artículo 7\n\nI. Uno; y II. Dos."
    despues = "# Artículo 7\n\nI. Uno; y\n\n_Fracción reformada DOF 24-04-1972_\n\nII. Dos."
    assert coherencia.clasificar("M", antes, despues, set(), "2012-11-30", "2015-06-12") == "solo_forma"
    assert coherencia.clasificar("M", antes, despues.replace("Dos", "Tres"), set(),
                                 "2012-11-30", "2015-06-12") == "sin_explicar"


def test_una_reedicion_de_la_camara_se_prueba_con_los_dos_pdf():
    antes = "# Artículo 30.\n\nLa nacionalidad se adquiere así.\n\nA.- Son mexicanos por nacimiento:"
    despues = "# Artículo 30.\n\nLa nacionalidad se adquiere así.\n\nA) Son mexicanos por nacimiento:"
    pdf_antes = "Artículo 30. La nacionalidad se adquiere así. A.- Son mexicanos por nacimiento: I."
    pdf_despues = "Artículo 30. La nacionalidad se adquiere así. A) Son mexicanos por nacimiento: I."
    assert reedicion.es_de_la_fuente(antes, despues, pdf_antes, pdf_despues)


def test_si_los_dos_pdf_dicen_lo_mismo_cambio_la_lectura():
    antes = "# Artículo 899-B\n\nlos contratos colectivos de trabajo o contratos- Ley que contengan"
    despues = "# Artículo 899-B\n\nlos contratos colectivos de trabajo o contratos-Ley que contengan"
    pdf = "los contratos colectivos de trabajo o contratos- Ley que contengan beneficios"
    assert not reedicion.es_de_la_fuente(antes, despues, pdf, pdf)
    assert not reedicion.es_de_la_fuente(antes, antes, pdf, pdf)


def test_el_mobiliario_de_pagina_no_corta_el_texto_del_pdf():
    cuerpos = ["uno empieza y", "sigue en la dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"]
    paginas = [f"LEY FEDERAL\nSecretaría General\n{c}\n{n} de 9" for n, c in enumerate(cuerpos, 1)]
    texto = reedicion.sin_mobiliario(paginas)
    assert "uno empieza y sigue en la dos tres" in texto
    assert "Secretaría" not in texto and "de 9" not in texto


def test_lecturas_distintas_del_mismo_contenido():
    assert coherencia.lectura_menor("o contratos- Ley que", "o contratos-Ley que") == "solo_puntuacion"
    assert coherencia.lectura_menor("81 Del codo 10%", "Del codo 81 10%") == "otro_orden"
    assert coherencia.lectura_menor("el periodo inmediato", "el período inmediato") is None


def test_una_nota_intercalada_en_el_pdf_no_impide_la_prueba():
    antes = "# Artículo 97.\n\nde algún juez o magistrado federal.\n\n(Párrafo tercero. Se deroga)\n\nLa Suprema Corte nombrará"
    despues = "# Artículo 97.\n\nde algún juez o magistrado federal.\n\n(Se deroga el párrafo tercero)\n\nLa Suprema Corte nombrará"
    pdf_antes = "de algún juez o magistrado federal. (Párrafo tercero. Se deroga) La Suprema Corte nombrará y removerá"
    pdf_despues = ("de algún juez o magistrado federal. Párrafo reformado DOF 10-06-2011 (Se deroga el párrafo tercero) "
                   "Párrafo derogado DOF 13-11-2007 La Suprema Corte nombrará y removerá")
    assert reedicion.es_de_la_fuente(antes, despues, pdf_antes, pdf_despues)
    assert not reedicion.esta("uno dos tres cuatro", "uno dos y luego mucho después tres cuatro")


def test_la_portada_dice_de_que_ley_es_la_captura():
    portada = ("LEY DEL IMPUESTO SOBRE LA RENTA\nNueva Ley publicada en el Diario Oficial de la Federación "
               "el 1º de enero de 2002\nTEXTO VIGENTE\nÚltima reforma publicada DOF 18-07-2006")
    assert capturas.origen_de_portada(portada) == "2002-01-01"
    assert capturas.version_de_portada(portada) == "2006-07-18"
    nueva = "Nueva Ley DOF 07-11-2025\nNueva Ley publicada en el Diario Oficial de la Federación el 7 de noviembre de 2025"
    assert capturas.version_de_portada(nueva) == "2025-11-07"


def test_las_capturas_de_la_ley_abrogada_no_entran_en_la_cadena(monkeypatch):
    filas = [{"version": "2006-07-18", "origen": "2002-01-01", "captura": "1"},
             {"version": "2013-12-11", "origen": "2013-12-11", "captura": "2"},
             {"version": "2016-11-30", "origen": "2013-12-11", "captura": "3"}]
    monkeypatch.setattr(capturas, "leer_manifiesto", lambda clave: filas)
    assert list(capturas.versiones("lisr")) == ["2013-12-11", "2016-11-30"]


def test_la_tanda_toma_primero_lo_nunca_intentado_y_luego_lo_mas_viejo(monkeypatch):
    from historico import tanda
    docs = [{"clave": c} for c in "abcd"]
    estados = {"a": {"fecha": "2026-11-20"}, "c": {"fecha": "2026-11-01"}}
    monkeypatch.setattr(tanda, "configuracion", lambda: {"documentos": docs})
    monkeypatch.setattr(tanda, "leer_estado", estados.get)
    assert [d["clave"] for d in tanda.elegir(5)] == ["b", "d"]
    assert [d["clave"] for d in tanda.elegir(5, ["c"])] == ["c"]
    estados |= {"b": {"fecha": "2026-11-22"}, "d": {"fecha": "2026-11-21"}}
    assert [d["clave"] for d in tanda.elegir(2)] == ["c", "a"]
