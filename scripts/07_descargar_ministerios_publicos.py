"""Cabezas de los Ministerios Públicos (fiscal, defensa, tutelar) de PBA y CABA,
leídas de sus sitios oficiales.

  PBA   mpba.gov.ar/organigrama         Procuración General y sus secretarías
  CABA  mpfciudad.gob.ar/.../autoridades Fiscal General
        mptutelar.gob.ar                 Asesor/a General Tutelar
        mpdefensa.gob.ar                 Defensor/a General (el sitio responde 403 a
                                         descargas automáticas: queda "sin dato")

Qué no puede afirmar: solo la cúpula. Fiscalías y defensorías departamentales no
se publican en una lista descargable.
"""
import html as H
import json
import re
from datetime import date
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parents[1] / "raw" / "ministerios_publicos.json"
s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (mapa-del-estado-ba; investigación)"
TIT = r"(?:Dr\.|Dra\.|Lic\.|Cdor\.|Cdora\.|Ing\.|Arq\.)"


def plano(url):
    try:
        r = s.get(url, timeout=60)
        if r.status_code != 200:
            return None
        t = re.sub(r"<(script|style).*?</\1>", "", r.content.decode("utf-8", "replace"), flags=re.S)
        return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", "\n", t)))
    except requests.RequestException:
        return None


def buscar(txt, patron):
    m = re.search(patron, txt or "")
    return m.group(1).strip().title() if m else None


out = {"fecha": date.today().isoformat(), "organos": []}

# PBA: Procuración General (un solo órgano con fiscales, defensores y asesores).
url = "https://www.mpba.gov.ar/organigrama"
t = plano(url)
areas = re.findall(rf"((?:PROCURACI[ÓO]N|SECRETAR[ÍI]A)[A-ZÁÉÍÓÚÑ ,.]{{4,}}?)\s+{TIT}\s*"
                   rf"([A-ZÁÉÍÓÚÑ][\wáéíóúñÁÉÍÓÚÑ .'-]+?)\s+(Secretari[oa]|Procurador[a]? General)\b", t or "")
cabeza = next((a for a in areas if a[0].startswith("PROCURACI")), None)
out["organos"].append({
    "jur": "pba", "id": "mp", "nombre": "Ministerio Público (Procuración General)", "url": url,
    "titular": {"cargo": "Procurador General", "nombre": cabeza[1]} if cabeza else None,
    "areas": [{"nombre": a[0].strip().capitalize(), "cargo": a[2], "nombre_titular": a[1]}
              for a in areas if not a[0].startswith("PROCURACI")]})

# CABA: tres ministerios públicos autónomos.
url = "https://mpfciudad.gob.ar/institucional/autoridades"
t = plano(url)
m = re.search(r"Fiscalía General ([A-ZÁÉÍÓÚÑ ]{6,}?) (Fiscal General(?: A/C)?)", t or "")
out["organos"].append({"jur": "caba", "id": "mpf", "nombre": "Ministerio Público Fiscal", "url": url,
                       "titular": {"cargo": m.group(2), "nombre": m.group(1).title()} if m else None})

url = "https://mptutelar.gob.ar/"
nom = buscar(plano(url), rf"Asesora? General Tutelar,? {TIT}?\s*([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(?: [A-ZÁÉÍÓÚÑ][\wáéíóúñ]+){{1,3}})")
out["organos"].append({"jur": "caba", "id": "mpt", "nombre": "Ministerio Público Tutelar", "url": url,
                       "titular": {"cargo": "Asesor/a General Tutelar", "nombre": nom} if nom else None})

url = "https://www.mpdefensa.gob.ar/"
nom = buscar(plano(url), rf"Defensora? General,? {TIT}?\s*([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(?: [A-ZÁÉÍÓÚÑ][\wáéíóúñ]+){{1,3}})")
out["organos"].append({"jur": "caba", "id": "mpd", "nombre": "Ministerio Público de la Defensa", "url": url,
                       "titular": {"cargo": "Defensor/a General", "nombre": nom} if nom else None})

OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
for o in out["organos"]:
    print(f"  {o['jur']} {o['nombre']}: {o['titular'] or 'SIN DATO'} · {len(o.get('areas', []))} áreas")
