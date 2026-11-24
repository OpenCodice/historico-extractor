"""La cadena de versiones de un documento: un commit por versión, en su rama.

Cada versión se extrae con el extractor vigente del corpus (el de la CPEUM o
el de las leyes federales), sin modificarlo: lo propio de los PDF antiguos se
declara en `documentos.json` y se le pasa por sus puntos de extensión
(`fuente/ruido.json`, `titulos_encabezado` del registro).

Cada documento vive en una rama huérfana con su clave. Así se puede regenerar
uno (porque mejoró un extractor o apareció una captura) sin mover los hashes
de los demás.
"""
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess

from . import configuracion
from .capturas import asegurar, versiones

# Identidad fija: con ella, las mismas capturas y el mismo extractor dan los
# mismos hashes a quien regenere la rama.
FIRMA = {f"GIT_{quien}_{campo}": valor for quien in ("AUTHOR", "COMMITTER")
         for campo, valor in (("NAME", "OpenCodice"), ("EMAIL", "noreply@constitucion.app"))}
REPO_DE = {"constitucion": "OpenCodice/constitucion-extractor",
           "federal": "OpenCodice/fiscal-extractor"}


def _correr(*args, cwd=None, env=None) -> tuple[int, str]:
    r = subprocess.run([str(a) for a in args], cwd=cwd, env=env, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def _git(repo, *args, env=None) -> str:
    codigo, salida = _correr("git", *args, cwd=repo, env=env)
    if codigo:
        raise RuntimeError(f"git {' '.join(map(str, args))}: {salida}")
    return salida


def patrones_de_ruido(encabezados: dict) -> list[str]:
    return ([f"^{re.escape(p)}\\b" for p in encabezados["prefijos"]]
            + [f"^{re.escape(r)}$" for r in encabezados["renglones"]]
            + encabezados.get("patrones", []))


def encabezados_de(clave: str) -> dict:
    """Los encabezados antiguos que valen para un documento: los de todos más,
    si su PDF llevó un tiempo el número de página suelto al pie (`paginas_sueltas`:
    clave → hasta qué página), un renglón por cada número."""
    config = configuracion()
    encabezados = dict(config["encabezados_antiguos"])
    hasta = config.get("paginas_sueltas", {}).get(clave)
    if hasta:
        encabezados["renglones"] = encabezados["renglones"] + [str(n) for n in range(1, hasta + 1)]
    return encabezados


def sello_de_configuracion(clave: str) -> str:
    """Cambia cuando cambia lo que se le declara a los extractores para ese
    documento: una rama hecha con otra configuración es otra cadena."""
    canonico = json.dumps(encabezados_de(clave), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonico.encode()).hexdigest()[:12]


def extraer(doc: dict, pdf: pathlib.Path, version: str, trabajo: pathlib.Path,
            extractor: pathlib.Path) -> tuple[pathlib.Path | None, str]:
    """Construye una versión y le pasa las compuertas del extractor.
    Devuelve (carpeta con los .md, '') o (None, motivo)."""
    if trabajo.exists():
        shutil.rmtree(trabajo)
    salida = trabajo / "salida"
    salida.mkdir(parents=True)
    py = extractor / ".venv/bin/python"
    encabezados = encabezados_de(doc["clave"])
    auditoria = trabajo / "auditoria.json"
    if doc["extractor"] == "constitucion":
        (salida / "fuente").mkdir()
        (salida / "fuente/ruido.json").write_text(
            json.dumps({"patrones": patrones_de_ruido(encabezados)}, ensure_ascii=False))
        base = [py, "-m", "extractor"]
        pasos = {
            "build": [*base, "build", "--pdf", pdf, "--out", salida, "--version", version],
            "auditar": [*base, "auditar", "--pdf", pdf, "--out", salida, "--json", auditoria],
            "validar": [*base, "validar", "--out", salida],
        }
        articulos = salida / "articulos"
    else:
        registro = trabajo / "registro.json"
        entrada = {k: doc[k] for k in ("clave", "etiqueta", "sigla", "tipo", "url")}
        entrada |= {"parser": "articulado", "titulos_encabezado": encabezados["renglones"]}
        registro.write_text(json.dumps({"documentos": [entrada]}, ensure_ascii=False))
        pdfs = trabajo / "pdf"
        pdfs.mkdir()
        shutil.copy(pdf, pdfs / f"{doc['clave']}.pdf")
        base = [py, "-m", "extractor", "--registro", registro]
        pasos = {
            "build": [*base, "build", "--doc", doc["clave"], "--pdf", pdfs / f"{doc['clave']}.pdf",
                      "--out", salida, "--sin-pasajes"],
            "auditar": [*base, "auditar", "--out", salida, "--pdf-dir", pdfs, "--json", auditoria],
            "validar": [*base, "validar", "--out", salida],
        }
        articulos = salida / doc["clave"]
    for nombre, orden in pasos.items():
        codigo, texto = _correr(*orden, cwd=extractor)
        ultima = texto.splitlines()[-1] if texto else ""
        if codigo or (nombre == "auditar" and not ultima.startswith("0 de ")):
            return None, f"{nombre}: {ultima[:200]}"
    return articulos, ""


def _trailers(repo, rev: str) -> dict:
    cuerpo = _git(repo, "log", "-1", "--format=%B", rev)
    return dict(l.split(": ", 1) for l in cuerpo.splitlines() if re.match(r"[A-Z][\w-]+: ", l))


def _hechas(repo, rama: str) -> list[dict]:
    codigo, salida = _correr("git", "rev-list", "--reverse", f"refs/heads/{rama}", cwd=repo)
    return [] if codigo else [_trailers(repo, h) for h in salida.split()]


def _cambios(repo) -> dict[str, list[str]]:
    listas = {"A": [], "M": [], "D": []}
    for linea in _git(repo, "diff", "--cached", "--name-status", "--no-renames").splitlines():
        estado, ruta = linea.split("\t")
        listas[estado].append(pathlib.Path(ruta).stem)
    return listas


def mensaje(doc: dict, fila: dict, extractor_sha: str, cambios: dict | None) -> str:
    lineas = [f"Versión {doc['sigla']} (DOF {fila['version']})", "",
              f"Documento: {doc['clave']}", "Tipo: version",
              f"Publicacion: {fila['version']}", "Publicacion-Origen: portada", "Medio: DOF"]
    for estado, nombre in (("A", "Adicionados"), ("M", "Modificados"), ("D", "Retirados")):
        if cambios and cambios[estado]:
            lineas.append(f"Articulos-{nombre}: {', '.join(cambios[estado])}")
    lineas += [f"Fuente: https://web.archive.org/web/{fila['captura']}id_/{fila['url']}",
               f"Fuente-Sha256: {fila['sha256']}",
               f"Extractor: {REPO_DE[doc['extractor']]}@{extractor_sha}",
               f"Configuracion: {sello_de_configuracion(doc['clave'])}"]
    return "\n".join(lineas) + "\n"


def construir(doc: dict, capturas: pathlib.Path, repo: pathlib.Path, extractor: pathlib.Path,
              trabajo: pathlib.Path, desde_cero: bool = False, avisar=print,
              fuera_conocidas=()) -> list[dict]:
    """Deja en `repo` la rama del documento con un commit por versión que pasa
    las compuertas. Devuelve una fila por versión con lo que pasó.
    `fuera_conocidas` son las (versión, sha256) que ya fallaron las compuertas
    con esta configuración: no se reintentan al continuar una rama."""
    clave = doc["clave"]
    plan = versiones(clave)
    extractor_sha = _git(extractor, "rev-parse", "--short=12", "HEAD")
    if not (repo / ".git").exists():
        repo.mkdir(parents=True, exist_ok=True)
        _git(repo, "init", "-q")
    hechas = [] if desde_cero else _hechas(repo, clave)
    # Una rama se continúa si todo lo anterior a su punta ya está en ella o ya
    # se sabe que falla: entonces solo faltan versiones nuevas. Lo demás (otra
    # configuración, una captura nueva de una versión vieja) es otra cadena y
    # se rehace entera. El extractor sí puede cambiar de un commit al
    # siguiente; cada uno dice con cuál se hizo.
    previstas = [(v, f["sha256"]) for v, f in plan.items()]
    ya = [(t.get("Publicacion"), t.get("Fuente-Sha256")) for t in hechas]
    punta = max((v for v, _ in ya), default="")
    continua = bool(hechas) \
        and all(t.get("Configuracion") == sello_de_configuracion(clave) for t in hechas) \
        and all(par in previstas for par in ya) \
        and all(par in ya or par in fuera_conocidas for par in previstas if par[0] <= punta)
    _git(repo, "symbolic-ref", "HEAD", f"refs/heads/{clave}")
    if continua:
        _git(repo, "reset", "-q", "--hard")
    else:
        _correr("git", "update-ref", "-d", f"refs/heads/{clave}", cwd=repo)
        _git(repo, "read-tree", "--empty")
        ya = []
    for sobra in repo.iterdir():
        if sobra.name != ".git" and not continua:
            shutil.rmtree(sobra) if sobra.is_dir() else sobra.unlink()
    filas = []
    for version, fila in plan.items():
        if (version, fila["sha256"]) in ya:
            continue
        if (version, fila["sha256"]) in fuera_conocidas and continua:
            continue
        carpeta, motivo = extraer(doc, asegurar(fila, capturas), version, trabajo, extractor)
        if carpeta is None:
            filas.append({"version": version, "estado": "fuera", "motivo": motivo})
            avisar(f"{clave} {version}: fuera ({motivo})")
            continue
        destino = repo / clave
        if destino.exists():
            shutil.rmtree(destino)
        shutil.copytree(carpeta, destino, ignore=lambda _, nombres: [n for n in nombres if not n.endswith(".md")])
        _git(repo, "add", "-A")
        primera = _correr("git", "rev-parse", "-q", "--verify", "HEAD", cwd=repo)[0] != 0
        cambios = None if primera else _cambios(repo)
        fecha = f"{version}T12:00:00+00:00"
        _git(repo, "commit", "-q", "--allow-empty", "-m", mensaje(doc, fila, extractor_sha, cambios),
             env={**os.environ, **FIRMA, "GIT_AUTHOR_DATE": fecha, "GIT_COMMITTER_DATE": fecha})
        unidades = len(list(destino.glob("*.md")))
        filas.append({"version": version, "estado": "ok", "motivo": "", "unidades": unidades})
        avisar(f"{clave} {version}: {unidades} artículos")
    return filas
