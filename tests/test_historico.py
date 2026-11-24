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
    assert [d["clave"] for d in tanda.elegir(2)] == ["c", "a", "d", "b"]


def test_un_articulo_adicionado_sin_nota_se_prueba_con_los_dos_pdf():
    nuevo = "# Artículo 133-B\n\nEl recurso de revocación podrá tramitarse conforme al procedimiento especializado."
    pdf_antes = "Artículo 133-A. Las autoridades demandadas. Artículo 134. Las notificaciones se harán"
    pdf_despues = ("Artículo 133-A. Las autoridades demandadas. Artículo 133-B. El recurso de revocación podrá "
                   "tramitarse conforme al procedimiento especializado. Artículo 134. Las notificaciones se harán")
    assert reedicion.clase("", nuevo, pdf_antes, pdf_despues) == "reedicion"
    assert reedicion.clase(nuevo, "", pdf_despues, pdf_antes) == "reedicion"
    assert reedicion.clase("", nuevo, pdf_despues, pdf_despues) is None


def test_una_frase_repetida_en_otro_articulo_se_prueba_contando():
    antes = "# Artículo 40-A\n\nhasta por el monto conforme a la Ley de la materia y las aportaciones voluntarias"
    despues = antes.replace("la Ley de", "la ley de")
    otro = "Artículo 156-Bis. hasta por el monto conforme a la {} de la materia y las aportaciones voluntarias"
    cuerpo = "Artículo 40-A. hasta por el monto conforme a la {} de la materia y las aportaciones voluntarias "
    pdf_antes = cuerpo.format("Ley") + otro.format("ley")
    pdf_despues = cuerpo.format("ley") + otro.format("ley")
    assert reedicion.es_de_la_fuente(antes, despues, pdf_antes, pdf_despues)
    assert not reedicion.es_de_la_fuente(antes, despues, pdf_antes, pdf_antes)


def test_texto_que_la_otra_version_lleva_como_nota():
    antes = "# Artículo 467 Bis\n\nse aplicará de 7 a 15 años de prisión.\n\n_Artículo adicionado DOF 04-12-2013_\n\n(En la porción normativa que remite a la fracción IV)"
    despues = "# Artículo 467 Bis\n\nse aplicará de 7 a 15 años de prisión.\n\n_Artículo adicionado DOF 04-12-2013 (En la porción normativa que remite a la fracción IV)_"
    pdf = "se aplicará de 7 a 15 años de prisión. Artículo adicionado DOF 04-12-2013 (En la porción normativa que remite a la fracción IV) Artículo 468"
    assert reedicion.clase(antes, despues, pdf, pdf) == "nota_en_el_cuerpo"


def test_una_version_declarada_fuera_no_entra_al_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(capturas, "MANIFIESTOS", tmp_path)
    monkeypatch.setattr(capturas, "configuracion", lambda: {"versiones_fuera": {"x": {"2021-11-22": "motivo"}}})
    capturas.escribir_manifiesto("x", [
        {"archivo": f"{n}_X.pdf", "captura": str(n), "url": "u", "sha256": "s", "bytes": 1, "version": v,
         "paginas": 1, "origen": "2000-01-01"} for n, v in ((1, "2021-10-14"), (2, "2021-11-22"))])
    assert list(capturas.versiones("x")) == ["2021-10-14"]


def test_una_rama_publicada_sin_capturas_nuevas_no_se_rehace(tmp_path, monkeypatch):
    from historico import tanda
    monkeypatch.setattr(tanda.capturas, "descargar", lambda *a: [{}] * 3)
    monkeypatch.setattr(tanda.capturas, "versiones", lambda clave: {"2020-01-01": {}, "2021-01-01": {}})
    monkeypatch.setattr(tanda.cadena, "sello_de_configuracion", lambda clave: "abc")
    monkeypatch.setattr(tanda.cadena, "construir", lambda *a, **k: 1 / 0)
    previo = {"fecha": "2026-11-01", "configuracion": "abc", "capturas": 3, "versiones_archivadas": 2,
              "publicada": True, "versiones": 2}
    monkeypatch.setattr(tanda, "leer_estado", lambda clave: previo)
    doc = {"clave": "x", "archivos": "X.pdf", "extractor": "federal"}
    estado = tanda.procesar(doc, tmp_path, tmp_path, tmp_path, publicar=True)
    assert estado["publicada"] and estado["versiones"] == 2 and estado["fecha"] > "2026-11-01"
    previo["capturas"] = 2
    assert "ZeroDivisionError" in tanda.procesar(doc, tmp_path, tmp_path, tmp_path, publicar=True)["motivo"]


def test_una_formula_leida_de_otro_modo_no_es_un_cambio_de_la_ley():
    marca = "[Fórmula: consultar el PDF oficial, página {}]"
    antes = f"se calculará así:\n\n{marca.format(58)}\n\ndonde ME = Margen de error."
    assert coherencia.lectura_menor(antes, antes.replace("58", "63")) == "formula"
    texto = "se calculará así:\n\nCE ¡Error! Marcador no definido.ME 100 CE CDV donde ME = Margen de error."
    assert coherencia.lectura_menor(texto, antes) == "formula"
    assert coherencia.lectura_menor(antes, antes.replace("Margen", "Rango").replace("58", "63")) is None
    suelto = antes + "\n\ndonde k es el coeficiente"
    assert coherencia.lectura_menor(suelto, suelto.replace("donde k", "donde j=1 i,t−j−1 k")) == "formula"
    assert coherencia.lectura_menor(suelto, suelto.replace("donde k", "donde no k")) is None
    literal = "I. Fórmula:\n\nIGPj = Pj1 + Pj2\n\nla participación (PE ) que se asignará a cada Estado."
    assert coherencia.lectura_menor(literal, literal.replace("que se", "que k se")) == "formula"
    assert coherencia.lectura_menor(literal, literal.replace("que se", "que no se")) is None


def test_un_rotulo_reeditado_se_prueba_con_los_dos_pdf():
    antes = "# Artículo 420 Quater\n\nSe impondrá pena de uno a cuatro años."
    despues = antes.replace("Quater", "Quáter")
    pdf = "ambiental Artículo 420 {}.- Se impondrá pena de uno a cuatro años. Artículo 421"
    assert reedicion.es_de_la_fuente(antes, despues, pdf.format("Quater"), pdf.format("Quáter"))
    assert not reedicion.es_de_la_fuente(antes, despues, pdf.format("Quater"), pdf.format("Quater"))


def test_la_ventana_que_empieza_antes_de_una_nota_se_prueba_con_mas_contexto():
    antes = "# Artículo 386\n\ncuando el valor no exceda de diez veces el salario;\n\nII.- Con prisión de 6 meses a 3 años"
    despues = antes.replace("prisión", "Prisión")
    pdf_antes = "cuando el valor no exceda de diez veces el salario; II.- Con prisión de 6 meses a 3 años y multa"
    pdf_despues = ("cuando el valor no exceda de diez veces el salario; Fracción reformada DOF 30-12-1991 "
                   "II.- Con Prisión de 6 meses a 3 años y multa")
    assert reedicion.es_de_la_fuente(antes, despues, pdf_antes, pdf_despues)


def test_un_articulo_que_una_errata_del_rotulo_tenia_dentro_del_anterior():
    nuevo = "# Artículo 291.\n\nEl comisionista deberá observar lo establecido en las leyes."
    pdf_antes = "sin demora. Artículo 29l.- El comisionista deberá observar lo establecido en las leyes. Artículo 292"
    pdf_despues = pdf_antes.replace("29l", "291")
    assert reedicion.clase("", nuevo, pdf_antes, pdf_despues) == "reedicion"
    assert reedicion.clase("", nuevo, pdf_despues, pdf_despues) is None


def test_la_version_por_notas_no_pasa_del_dia_de_la_captura(tmp_path, monkeypatch):
    class Pagina:
        def __init__(self, t): self.t = t
        def extract_text(self): return self.t
    class Pdf:
        pages = [Pagina("CÓDIGO Última Reforma DOF 28-03-2018"), Pagina("Cantidad actualizada DOF 31-12-2018"),
                 Pagina("Cantidad actualizada DOF 24-12-2020")]
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setattr(capturas.pdfplumber, "open", lambda ruta: Pdf())
    assert capturas.leer_portada(tmp_path)[0] == "2018-03-28"
    assert capturas.leer_portada(tmp_path, True, "2019-02-14")[0] == "2018-12-31"
    assert capturas.leer_portada(tmp_path, True)[0] == "2020-12-24"
