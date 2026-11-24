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
| `historico/declarar.py` | Declara en `documentos.json` las leyes federales del registro vigente (`leyes-federales/fuentes.json`), con el número que tuvo su PDF antes de nombrarse por sigla; lo saca de los índices de LeyesBiblio archivados. |
| `historico/cadena.py` | Por cada versión, en orden: extrae, pasa las compuertas del extractor y hace el commit en la rama del documento, fechado el día del DOF. Continúa una rama a medias si es prefijo del plan con el mismo extractor. |
| `historico/coherencia.py` | La compuerta de la cadena (ver abajo). |
| `historico/reedicion.py` | Prueba, con el texto de los dos PDF, que un cambio sin reforma lo hizo la Cámara. |
| `coherencia/<clave>.json`, `verificaciones/<clave>.json` | El informe de la compuerta de cada rama y los veredictos del agente. |

Una versión es una fecha de portada; si hay varias capturas con la misma
fecha se usa la más reciente (la Cámara corrige erratas y notas sin cambiar la
portada). Las capturas que Wayback truncó no abren y quedan en el manifiesto
como `ilegible`.

## Tandas

`reconstruir.yml` corre `python -m historico tanda`: por cada documento de la
tanda, capturas, cadena, coherencia y, si queda limpia, `git push --force` de
su rama a `OpenCodice/historico`; al final, la tabla de ramas del README de
`main`. Lo que pasó con cada documento queda en `estado/<clave>.json` (fecha,
versiones, las que quedaron fuera con su motivo, si se publicó), que el mismo
workflow sube a este repo junto con los manifiestos y los informes.

Qué toca: primero los documentos declarados que nunca se han intentado, de
seis en seis; cuando no quedan, todos, del que lleva más tiempo sin revisarse
al más reciente, hasta agotar cuatro horas. La revisión de una rama publicada
sin capturas nuevas ni cambios en lo declarado no rehace nada. Mientras queden sin
intentar, la corrida declara `estado pendiente=[true]` y el supervisor lanza
la siguiente; después basta la cita semanal. Una rama publicada se continúa
(solo se extraen las versiones nuevas) si nada anterior cambió; si no, se
rehace entera. `desde_cero=si` la rehace siempre, por ejemplo para aprovechar
una mejora de un extractor en las versiones viejas.

Una ley abrogada y la que la sustituyó pueden compartir nombre y archivo (la
LISR de 2002 y la de 2013). La portada dice cuándo se publicó la ley
(`origen` en el manifiesto) y solo entran las capturas de la vigente.

Los PDF no se guardan: el manifiesto dice de qué captura salió cada versión y
`capturas.asegurar` la vuelve a bajar comprobando su sha256.

Dos cosas se leen de cada PDF sin declarar nada (`cadena.membretes`): el
renglón del membrete con la fecha de esa versión, que en una ley de pocas
páginas no se repite lo bastante para que el extractor lo reconozca, y el
número de página suelto al pie que algunos PDF llevaron entre 2005 y 2012.

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
- **reedición**, si cambió sin nota y cada diferencia está literal en el
  PDF de su versión y falta en el de la otra (`historico/reedicion.py`): la
  Cámara retocó puntuación, acentos, mayúsculas o incisos. Vale también para
  un artículo adicionado o retirado, y es la única prueba en las leyes cuyo
  PDF no anota las reformas (el CFF): ahí caen sus reformas. Si la frase
  está repetida en otro artículo, se prueba con más contexto y contando sus
  apariciones en cada PDF;
- **nota en el cuerpo**, si lo que cambia es texto de una nota de reforma
  que una versión dejó como texto del artículo: cita su DOF o la otra
  versión lo lleva entre sus notas (la ley no cambia);
- **solo puntuación**, si son las mismas letras y cifras y cambian espacios o
  signos (un guion de fin de renglón);
- **otro orden**, si son las mismas palabras en otro orden (las celdas de una
  tabla);
- **fórmula**, si cada diferencia es de una fórmula: su marca apunta a otra
  página, una versión la leyó como texto y la otra dejó la marca, o cambian
  restos sueltos de ella (un subíndice, nunca una palabra);
- **juzgado**, si un agente dejó su veredicto (ver abajo);
- **sin explicar**, en cualquier otro caso.

Solo «sin explicar» detiene la publicación de la rama:
`python -m historico coherencia <clave> --out <repo>` sale con 1. «Nota en el
cuerpo», «solo puntuación», «otro orden» y «fórmula» son lecturas distintas del mismo contenido; pasan,
y quedan a la vista en el informe versionado `coherencia/<clave>.json`.

Medido el 2026-11-23, ambas ramas pasan sin ningún veredicto de agente:

| | CPEUM (75 versiones) | LFT (24 versiones) |
|---|---|---|
| Con reforma anotada | 405 | 1,063 |
| Solo notas | 121 | 660 |
| Solo forma | 6 | 14 |
| Reedición de la Cámara | 77 | 12 |
| Nota en el cuerpo | 6 | 0 |
| Otro orden | 0 | 4 |
| Sin explicar | 0 | 0 |

### Juicio de lo que queda sin explicar

Lo que no se puede probar con código lo juzga un agente que solo juzga. El
informe trae, por cada paso, los `pendientes` (artículo y huella de sus dos
versiones) y el sha256 de las dos capturas. El agente compara las dos
versiones del artículo contra sus dos PDF y agrega a
`verificaciones/<clave>.json` un registro por artículo:

```json
{"desde": "2008-05-07", "hasta": "2008-06-18", "articulo": "059",
 "antes": "<huella>", "despues": "<huella>",
 "veredicto": "fuente", "detalle": "el PDF de junio acentúa «período»"}
```

- `fuente`: las dos versiones son fieles, cada una a su PDF; el cambio lo
  hizo la Cámara. Cuenta como juzgado.
- `lectura`: los PDF dicen lo mismo, o alguna versión no es fiel al suyo.
  Sigue sin explicar, y el `detalle` dice cuál versión y qué le falta o sobra.

El veredicto va ligado a las huellas: si la extracción cambia, deja de aplicar.
Un defecto de lectura de una versión antigua se resuelve declarando algo en
`documentos.json` o dejando esa versión fuera (`versiones_fuera` de
`documentos.json`: clave → versión → motivo); nunca parchando el extractor.
Lo declarado en `encabezados_antiguos` vale para todos los documentos y
cambiarlo rehace todas las ramas; lo que es de una sola ley se declara en
`por_documento` (`renglones`: renglones exactos que no son texto de ningún
artículo, como el último de un título de capítulo que quedaba pegado al
artículo anterior; `registro`: opciones del registro del extractor, como
`huecos` cuando una errata del PDF en un rótulo, «Artículo 29l», rompe la
numeración; `version_por_notas`: la portada no cambia con cada publicación y
la versión es la fecha más reciente que anotan los artículos, con
`Publicacion-Origen: notas`) y solo rehace la suya.
Si el defecto también está en el texto vigente, es del extractor: va como
issue a su repo y la rama espera a que se corrija.

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
Configuracion: <huella de lo declarado en documentos.json>
```

Los commits van firmados como «OpenCodice», con una identidad fija, para
que regenerar una rama con las mismas capturas y el mismo extractor dé los
mismos hashes. Las listas de artículos salen del diff contra la versión anterior (la primera
versión no las lleva). `Articulos-Modificados` incluye los cambios de solo
notas.

## Para probar en local

`python -m pytest` con el `.venv` de cualquiera de los extractores. Las
cadenas necesitan los clones de ambos extractores junto a este repo, cada uno
con su `.venv`. Git: directo en `main`, commits en español, sin coautoría de
asistentes.
