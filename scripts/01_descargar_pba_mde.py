"""Descarga la estructura completa del Poder Ejecutivo bonaerense desde el
Mapa del Estado oficial (mapadelestado.gba.gob.ar).

Qué hace: recorre las páginas índice (jurisdicciones, organismos, autoridades),
junta los IDs de organismo y baja el CSV que el sitio exporta para cada uno.
Cada CSV trae todas las unidades (ministerio → subsecretaría → dirección
provincial → dirección), a quién responden, su titular, el decreto de
designación y la fecha de inicio.

Qué no puede afirmar: el Mapa del Estado lo carga la propia Provincia; si un
decreto no se cargó, la vacante o el titular viejo figuran igual. Se guarda la
fecha de descarga para saber de cuándo es la foto.
"""
import json
import re
import time
from datetime import date
from pathlib import Path

import requests

BASE = "https://mapadelestado.gba.gob.ar"
RAW = Path(__file__).resolve().parents[1] / "raw" / "pba_mde"
RAW.mkdir(parents=True, exist_ok=True)

s = requests.Session()
s.headers["User-Agent"] = "grafo-gobierno-ba/0.1 (investigación)"

ids = set()
for page in ["jurisdicciones", "organismos", "autoridades/autoridades"]:
    html = s.get(f"{BASE}/{page}", timeout=30).text
    ids |= {int(x) for x in re.findall(r'href="/organismos/(\d+)"', html)}
print(f"{len(ids)} organismos")

ok = {}
for oid in sorted(ids):
    r = s.get(f"{BASE}/organismos/{oid}.csv", timeout=60)
    r.encoding = "utf-8"  # el servidor no declara charset y requests asume latin-1
    if r.status_code == 200 and r.text.startswith("unidad,"):
        (RAW / f"{oid}.csv").write_text(r.text, encoding="utf-8")
        ok[oid] = r.text.count("\n") - 1
        print(f"  {oid}: {ok[oid]} unidades")
    else:
        print(f"  {oid}: FALLÓ ({r.status_code})")
    time.sleep(0.5)

(RAW / "_descarga.json").write_text(json.dumps(
    {"fecha": date.today().isoformat(), "fuente": BASE, "organismos": ok}, indent=2))
