"""Integrantes de los dos Consejos de la Magistratura, desde sus sitios oficiales.

  PBA   cmagistratura.gba.gob.ar/institucional  → consejeros por estamento
        (Poder Judicial, Legislativo, Ejecutivo y Colegio de Abogados), titulares
        y suplentes, más la estructura interna del organismo.
  CABA  consejo.jusbaires.gob.ar/institucional/autoridades → los 9 consejeros.

Qué no puede afirmar: ninguno de los dos publica fecha de designación ni la
norma que la dispuso; el bonaerense tampoco aclara el mandato de cada consejero.
"""
import html as H
import json
import re
from datetime import date
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parents[1] / "raw" / "consejos_magistratura.json"
s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (mapa-del-estado-ba; investigación)"
TRATO = re.compile(r"^(?:Dra|Dr|Lic|Cra|Cr|Mag|A\.C|Ing|Arq|Esc)\.?\s+", re.I)


def lineas(url):
    """Texto del sitio como lista de líneas: cada dato viene en su propia etiqueta."""
    r = s.get(url, timeout=60, verify=False)
    t = re.sub(r"<(script|style).*?</\1>", "", r.text, flags=re.S)
    t = H.unescape(re.sub(r"<[^>]+>", "\n", t))
    return [re.sub(r"[ \t\xa0]+", " ", x).strip(" .,\xa0") for x in t.split("\n") if x.strip(" .,\xa0")]


def titulo(x):
    """'JEFA ÁREA DE GESTIÓN ADMINISTRATIVA Y RRHH' → 'Jefa Área de Gestión Administrativa y RRHH'."""
    menores = {"de", "del", "la", "el", "y", "en", "por", "a"}
    out = []
    for i, w in enumerate(x.split()):
        if len(w) > 1 and w.isupper() and not any(v in w.lower() for v in "aeiouáéíóú"):
            out.append(w)                      # sigla: RRHH, TIC
        elif i and w.lower() in menores:
            out.append(w.lower())
        else:
            out.append(w.capitalize())
    return " ".join(out)


def nombre_limpio(x):
    return TRATO.sub("", x).strip(" .,")


# ── PBA ──────────────────────────────────────────────────────────────────────
url_pba = "https://www.cmagistratura.gba.gob.ar/institucional"
ls = lineas(url_pba)
ini = next(i for i, x in enumerate(ls) if x.upper().startswith("INTEGRANTES"))
fin = next(i for i, x in enumerate(ls) if x.upper().startswith("ESTRUCTURA INTERNA"))
integrantes, estructura = [], []
ROL = re.compile(r"^(presidente|vicepresidente|consejer[oa])\b", re.I)
ESTAMENTO = re.compile(r"^(poder judicial|poder legislativo|poder ejecutivo|colegio de abogados|"
                       r"ministro de la suprema corte.*)$", re.I)

# Cada consejero ocupa varias líneas: nombre, rol, a veces "por el Interior", estamento.
# Se recorre por el rol y se toma el nombre de la línea anterior.
for i in range(ini + 1, fin):
    if not ROL.match(ls[i]) or ESTAMENTO.match(ls[i - 1]):
        continue
    nombre = nombre_limpio(ls[i - 1])
    if len(nombre) < 5 or ROL.match(nombre) or nombre.upper().startswith("INTEGRANTES"):
        continue
    estamento, region = None, None
    for j in range(i + 1, min(i + 4, fin)):
        if ROL.match(ls[j]):
            break
        if ESTAMENTO.match(ls[j]):
            estamento = ls[j].upper()
        elif ls[j].lower().startswith("por el"):
            region = ls[j][6:].strip().title()
    integrantes.append({"nombre": nombre, "rol": ls[i].title(), "estamento": estamento, "region": region})

# Estructura interna: el cargo en mayúsculas y abajo el nombre.
fin2 = next((i for i, x in enumerate(ls) if x.upper().startswith("SEGU")), len(ls))
for i in range(fin, fin2 - 1):
    cargo, nom = ls[i], ls[i + 1]
    # La presidencia ya figura entre los consejeros: no se repite como área.
    if cargo.isupper() and len(cargo) > 5 and TRATO.match(nom) and not cargo.startswith("PRESIDENTE"):
        estructura.append({"cargo": titulo(cargo), "nombre": nombre_limpio(nom)})

# ── CABA ─────────────────────────────────────────────────────────────────────
url_caba = "https://consejo.jusbaires.gob.ar/institucional/autoridades"
ls = lineas(url_caba)
caba = []
for i, x in enumerate(ls):
    if x.endswith("@jusbaires.gob.ar") and i >= 2:
        caba.append({"nombre": nombre_limpio(ls[i - 2]), "rol": ls[i - 1], "mail": x})

OUT.write_text(json.dumps({"fecha": date.today().isoformat(),
                           "pba": {"url": url_pba, "integrantes": integrantes, "estructura": estructura},
                           "caba": {"url": url_caba, "integrantes": caba}},
                          ensure_ascii=False, indent=1), encoding="utf-8")
print(f"PBA: {len(integrantes)} consejeros + {len(estructura)} de estructura interna")
for i in integrantes:
    print(f"   {i['estamento']:<20} {i['rol']:<20} {i['nombre']}")
print(f"CABA: {len(caba)} integrantes")
for i in caba:
    print(f"   {i['rol']:<20} {i['nombre']}")
