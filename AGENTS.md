# historico-extractor — guía para agentes

Reconstruye el texto de cada ley después de cada reforma, desde 2006, a partir
de las capturas de Wayback del PDF de LeyesBiblio. Publica en
`OpenCodice/historico`: una rama por documento, un commit por versión.

Es un corpus aparte del vigente. Los repos de datos vigentes
(`constitucion-mexicana`, `leyes-federales`, `fiscal-mexicano`) empiezan en su
alta y no se tocan; el histórico se enlaza con ellos por (Documento,
Publicacion).

## Reglas propias

- **Los extractores vigentes no se modifican por un PDF antiguo.** Este repo
  los llama tal como están (`python -m extractor` de `constitucion-extractor`
  y `fiscal-extractor`). Lo que un formato antiguo necesite se declara aquí,
  en `documentos.json`, y se pasa por los puntos de extensión que ya tienen:
  `fuente/ruido.json` (CPEUM) y `titulos_encabezado` del registro (leyes
  federales). Si un defecto de una versión antigua no se puede resolver así,
  esa versión queda fuera con su motivo; no se parcha el extractor.
- **El texto nunca se edita a mano**, igual que en el resto de OpenCodice.
- **Las ramas se pueden regenerar.** A diferencia de los repos vigentes, la
  rama de un documento se rehace cuando mejora un extractor o aparece una
  captura; por eso cada documento tiene su rama y los hashes de las demás no
  se mueven. El commit registra la captura, su sha256 y el commit del extractor.
- **Una versión solo entra si pasa las compuertas** del extractor (`build`,
  `auditar` sin problemas de cobertura, `validar`) y la rama solo se publica
  si pasa la de coherencia.

## Piezas

| Archivo | Qué hace |
|---|---|
| `documentos.json` | Los documentos declarados (clave, extractor, nombres de archivo que ha tenido su PDF) y los encabezados de página de los formatos antiguos. |
| `historico/capturas.py` | Lista en el CDX de Wayback las capturas distintas del PDF, las baja a `capturas/` (fuera de git) y lee de cada portada su «Última reforma». Deja `manifiestos/<clave>.tsv`, que sí se versiona: es la procedencia. |
| `historico/cadena.py` | Por cada versión, en orden: extrae, pasa las compuertas del extractor y hace el commit en la rama del documento, fechado el día del DOF. Continúa una rama a medias si es prefijo del plan con el mismo extractor. |
| `historico/coherencia.py` | La compuerta de la cadena (ver abajo). |

Una versión es una fecha de portada; si hay varias capturas con la misma
fecha se usa la más reciente (la Cámara corrige erratas y notas sin cambiar la
portada). Las capturas que Wayback truncó no abren y quedan en el manifiesto
como `ilegible`.

## Compuerta de coherencia

Las compuertas de los extractores comparan una versión contra su propio PDF,
y un defecto que está igual en ambos lados las pasa. La cadena da otra
evidencia: la Cámara anota cada reforma al pie del artículo con su fecha del
DOF. Un artículo que cambia entre dos versiones consecutivas queda:

- **explicado**, si alguna versión de la cadena le anota una reforma de ese
  periodo;
- **solo notas**, si el texto es idéntico y cambiaron las líneas de notas;
- **solo forma**, si son las mismas palabras en el mismo orden, partidas en
  otros párrafos (una nota nueva corta el párrafo donde antes seguía);
- **sin explicar**, en cualquier otro caso: cambió la lectura, no la ley.

`python -m historico coherencia <clave> --out <repo>` sale con 1 si queda
algo sin explicar.

Lo que queda sin explicar suele ser una de dos cosas, y solo se distinguen
contra los dos PDF: una reedición de la Cámara (retocó puntuación, mayúsculas
o la numeración de incisos sin que mediara reforma) o una lectura distinta del
extractor (una tabla cuyas celdas salen en otro orden). Medido el 2026-11-23:
CPEUM, 75 versiones, 68 de 74 pasos limpios, 84 artículos sin explicar (53 de
ellos en la reedición de junio de 2008); LFT, 24 versiones, 17 de 23 pasos
limpios, 16 artículos sin explicar.

## Commits de datos

```
Versión LFT (DOF 2012-11-30)

Documento: lft
Tipo: version
Publicacion: 2012-11-30
Publicacion-Origen: portada
Medio: DOF
Articulos-Adicionados: …
Articulos-Modificados: …
Articulos-Retirados: …
Fuente: https://web.archive.org/web/<captura>id_/<url original>
Fuente-Sha256: …
Extractor: OpenCodice/fiscal-extractor@<sha>
```

Las listas de artículos salen del diff contra la versión anterior (la primera
versión no las lleva). `Articulos-Modificados` incluye los cambios de solo
notas.

## Para probar en local

`python -m pytest` con el `.venv` de cualquiera de los extractores. Las
cadenas necesitan los clones de ambos extractores junto a este repo, cada uno
con su `.venv`. Git: directo en `main`, commits en español, sin coautoría de
asistentes.
