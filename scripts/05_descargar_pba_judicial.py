"""Descarga la Guía Judicial de la Suprema Corte bonaerense (scba.gov.ar/guia):
todos los organismos de cada departamento judicial, con fuero, contacto e
integrantes (juez/a, camaristas, secretarios, auxiliares).

Cómo se lee: cada organismo abre con una fila de encabezado celeste; después
vienen Fuero / Competencia / Asiento y una fila por integrante (cargo | nombre |
nota en <i>, p. ej. "Subrogante"). La fila del titular trae class="big".

Qué no puede afirmar: la guía no publica decreto ni fecha de designación; la
nota en <i> (subrogante, interino, licencia) es la única pista de situación.
"""
import html as H
import json
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests

BASE = "https://www.scba.gov.ar/guia"
OUT = Path(__file__).resolve().parents[1] / "raw" / "pba_judicial"
OUT.mkdir(parents=True, exist_ok=True)

s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (mapa-del-estado-ba; investigación)"


def texto(x):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", x))).strip()


def get(url):
    r = s.get(url, timeout=90)
    r.encoding = "latin-1"      # ASP clásico, ISO-8859-1
    return r.text


def parsear(page, depto):
    bloques = re.split(r'<tr style="background-color:#55bbcf;">', page)[1:]
    orgs = []
    for b in bloques:
        cab = re.search(r'<p class="left"><b>(.*?)</b>', b, re.S)
        campo = lambda k: (lambda m: texto(m.group(1)) if m else None)(
            re.search(rf"<b>{k}:?\s*</b>:?(.*?)</p>", b, re.S))
        idrep = re.search(r"idrep=(\d+)", b)
        mail = re.search(r"([\w.+-]+@jusbuenosaires\.gov\.ar)", b)
        gente = []
        for m in re.finditer(r'<tr ><td><p( class="big")?><b>(.*?)</b></p></td><td><p>(.*?)<i>(.*?)</i>', b, re.S):
            nom = re.sub(r"^(Dr|Dra|Esc|Lic|Cdor|Cdora|Ing|Arq|Sr|Sra|Mg|Abog)\.?\s+", "", texto(m.group(3)))
            if nom:
                gente.append({"cargo": texto(m.group(2)), "nombre": nom,
                              "nota": texto(m.group(4)) or None, "titular": bool(m.group(1))})
        # Sin encabezado propio es un desplegable ("Relatores de ministros")
        # del organismo anterior: sus integrantes van a ese organismo.
        if not cab:
            if orgs:
                orgs[-1]["integrantes"] += gente
            continue
        orgs.append({"id": idrep.group(1) if idrep else None, "nombre": texto(cab.group(1)), "depto": depto,
                     "fuero": campo("Fuero"), "competencia": campo("Competencia territorial"),
                     "mail": mail.group(1) if mail else None, "integrantes": gente})
    return orgs


if __name__ == "__main__":
    indice = get(f"{BASE}/default.asp")
    deptos = sorted(set(re.findall(r'mapadeptos\.asp\?depto=([^"]+)"', indice)))
    paginas = [(d, f"{BASE}/mapadeptos.asp?depto={quote(d)}") for d in deptos]
    paginas.append(("Justicia de Paz", f"{BASE}/mapafuero.asp?fuero={quote('Justicia de Paz')}"))

    todo, vistos = [], set()
    for depto, url in paginas:
        orgs = parsear(get(url), depto)
        nuevos = [o for o in orgs if (o["id"] or o["nombre"]) not in vistos]
        vistos |= {o["id"] or o["nombre"] for o in nuevos}
        todo += nuevos
        print(f"  {depto}: {len(orgs)} organismos ({len(nuevos)} nuevos), "
              f"{sum(len(o['integrantes']) for o in orgs)} integrantes")
        time.sleep(1)

    (OUT / "guia_judicial.json").write_text(json.dumps(
        {"fecha": date.today().isoformat(), "fuente": f"{BASE}/default.asp", "organismos": todo},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(todo)} organismos")
