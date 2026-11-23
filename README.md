# historico-extractor

Reconstruye las versiones anteriores de las leyes mexicanas: el texto de cada
ley tal como estaba después de cada reforma, desde 2006.

La Cámara de Diputados publica cada ley en una sola dirección que se
sobrescribe con cada reforma. Las versiones anteriores solo sobreviven en las
capturas de [Wayback Machine](https://web.archive.org/). Este repo las baja,
lee en la portada de cada una la fecha de su última reforma, y extrae cada
versión con los mismos extractores que mantienen el texto vigente
([constitucion-extractor](https://github.com/OpenCodice/constitucion-extractor)
y [fiscal-extractor](https://github.com/OpenCodice/fiscal-extractor)).

El resultado es una rama por ley, con un commit por versión:

```
Versión LFT (DOF 2012-11-30)

Documento: lft
Tipo: version
Publicacion: 2012-11-30
Publicacion-Origen: portada
Medio: DOF
Articulos-Modificados: 002, 003, …
Fuente: https://web.archive.org/web/20130116033416id_/http://www.diputados.gob.mx/LeyesBiblio/pdf/125.pdf
Fuente-Sha256: …
Extractor: OpenCodice/fiscal-extractor@38ac6e0…
```

## Uso

```
python -m historico capturas lft                 # baja las capturas y las fecha
python -m historico cadena lft --out ../historico # un commit por versión, en la rama lft
python -m historico coherencia lft --out ../historico
```

Necesita, junto a este repo, los clones de los dos extractores con su `.venv`.

Parte de [OpenCodice](https://github.com/OpenCodice). Licencia MIT; el texto
legal es de dominio público.
