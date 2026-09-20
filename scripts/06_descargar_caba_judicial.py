"""Descarga la Guía del Poder Judicial de la Ciudad (guiajudicial.jusbaires.gob.ar):
juzgados y cámaras de cada fuero, más los organismos (TSJ, Consejo de la
Magistratura), con sus magistrados y secretarios.

Cómo se lee cada ficha: <span> fuero, <span> instancia, <h3> nombre y una serie de
<p><strong>: las que no llevan "Rol:" delante son magistrados ("Dra. TESONE,
Romina"); las otras son funcionarios ("Secretario/a: Dr. X (Interino)").

Qué no puede afirmar: no hay norma ni fecha de designación. Los ministerios
públicos (fiscal, tutelar, defensa) tienen sitios propios y no están acá.
"""
import html as H
import json
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import unquote

import requests

BASE = "https://guiajudicial.jusbaires.gob.ar"
OUT = Path(__file__).resolve().parents[1] / "raw" / "caba_judicial"
OUT.mkdir(parents=True, exist_ok=True)

s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (mapa-del-estado-ba; investigación)"


def get(path):
    r = s.get(BASE + path, timeout=60)
    r.encoding = "latin-1"
    return r.text


def texto(x):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", x))).strip()


def persona(raw):
    """'Dr. APOSTOLIDIS, Federico Matías (Interino)' → ('Federico Matías Apostolidis', 'Interino')."""
    nota = re.search(r"\(([^)]+)\)\s*$", raw)
    raw = re.sub(r"\([^)]*\)\s*$", "", raw).strip()
    raw = re.sub(r"^(Dr|Dra|Lic|Cdor|Cdora|Ing|Sr|Sra)\.?\s+", "", raw, flags=re.I)
    return raw, (nota.group(1) if nota else None)


def nombre_corto(raw):
    """'VILLASUR GARCÍA, María Alejandra' → 'María Alejandra Villasur García'."""
    ap, _, nom = raw.partition(",")
    return f"{nom.strip()} {ap.strip().title()}".strip() if nom else raw


def ficha(path):
    t = get(path)
    box = t[t.find('class="info-result"'):t.find("Volver al listado")] or t
    spans = [texto(x) for x in re.findall(r"<span>(.*?)</span>", box, re.S)]
    nombre = texto((re.search(r"<h3>(.*?)</h3>", box, re.S) or [None, path])[1])
    gente = []
    for st in re.findall(r"<p><strong>(.*?)</strong></p>", box, re.S):
        st = texto(st)
        if st.lower().startswith(("mesa de entradas", "horario", "turno")):
            continue
        # "Vacante: Subroga Dra. X" → juzgado vacante, subrogado por X.
        m = re.match(r"vacante\s*:?\s*(?:-?\s*subroga\s*:?)?\s*(.*)", st, re.I)
        if m:
            sub = persona(m.group(1))[0] if m.group(1) else None
            gente.append({"cargo": "Juez/a", "nombre": None, "titular": True,
                          "nota": "Vacante" + (f" · subroga {nombre_corto(sub)}" if sub else "")})
            continue
        # Rol explícito solo si lo que precede a ":" es un rótulo corto ("Secretario/a").
        rol, sep, quien = st.partition(":")
        if not sep or len(rol) > 40 or re.search(r"\b(dr|dra)\.|\(", rol, re.I):
            rol, quien = "Magistrado/a", st
        # "A (En uso de licencia) - Subroga: B" / "A (En uso de licencia) - Dr. B"
        partes = re.split(r"\s*-\s*(?:subroga\s*:?)?\s*(?=(?:dr|dra)\.|[A-ZÁÉÍÓÚÑ]{3,},)", quien.strip(), maxsplit=1, flags=re.I)
        nom, nota = persona(partes[0])
        if len(partes) > 1:
            nota = f"{nota or 'Licencia'} · subroga {nombre_corto(persona(partes[1])[0])}"
        if nom:
            gente.append({"cargo": rol.strip(), "nombre": nom, "nota": nota,
                          "titular": rol == "Magistrado/a" or "president" in rol.lower() or "juez" in rol.lower()})
    return {"id": path, "nombre": nombre, "fuero": spans[0] if spans else None,
            "instancia": spans[1] if len(spans) > 1 else None, "integrantes": gente}


if __name__ == "__main__":
    rutas = set()
    indice = get("/juzgados")
    paginas = {"/juzgados"} | set(re.findall(r'href="(/juzgados/p\d+)"', indice))
    for p in sorted(paginas):
        rutas |= set(re.findall(r'href="(/juzgado/\d+/[^"]+)"', get(p)))
    org = get("/organismos")
    rutas |= set(re.findall(r'href="(?:https://guiajudicial\.jusbaires\.gob\.ar)?(/organismo/\d+/[^"]+)"', org))
    for p in [f"/organismos/p{i}" for i in range(1, 20)]:
        nuevos = set(re.findall(r'href="(?:https://guiajudicial\.jusbaires\.gob\.ar)?(/organismo/\d+/[^"]+)"', get(p)))
        if not nuevos - rutas:
            break
        rutas |= nuevos
    print(f"{len(rutas)} fichas")

    fichas = []
    for r in sorted(rutas):
        try:
            fichas.append(ficha(r))
        except Exception as e:
            print(f"  {r}: FALLÓ {e!r}")
        time.sleep(0.4)

    # La guía no lista a los jueces del TSJ; su sitio publica un CV por juez/a.
    tsj = s.get("https://www.tsjbaires.gov.ar/", timeout=60).text
    jueces = {}
    for j in re.findall(r'/media/jueces/([^"]+?)\.pdf', tsj):
        j = re.sub(r"[_\s]+", " ", unquote(j)).strip()
        jueces.setdefault(re.sub(r"\W", "", j.lower()), j)
    jueces = sorted(jueces.values())
    for f in fichas:
        if f["nombre"].startswith("Tribunal Superior de Justicia"):
            f["integrantes"] = [{"cargo": "Juez/a del TSJ", "nombre": re.sub(r"[_]", " ", j).title(),
                                 "nota": None, "titular": True} for j in jueces]
            f["fuente_integrantes"] = "https://www.tsjbaires.gov.ar/"

    (OUT / "guia_judicial.json").write_text(json.dumps(
        {"fecha": date.today().isoformat(), "fuente": BASE, "organismos": fichas},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(fichas)} organismos · {sum(len(f['integrantes']) for f in fichas)} integrantes")
