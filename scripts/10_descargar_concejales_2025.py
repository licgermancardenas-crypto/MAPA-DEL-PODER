"""Concejales electos el 7/9/2025 (mandato 2025-2029) desde el Escrutinio Definitivo
de la Junta Electoral bonaerense: un PDF por distrito en
juntaelectoral.gba.gov.ar/escrutinio-definitivo-2025/concejales/2025NNN.pdf

Del PDF se toman los TITULARES de cada lista con bancas, en orden. Los suplentes
no se cargan (no ocupan banca salvo reemplazo).
Con los electos 2023 (mandato 2023-2027, ya en el grafo) se completa cada Concejo.
"""
import json
import re
import subprocess
import time
from datetime import date
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
PDFS = RAIZ / "raw" / "concejales_2025"
PDFS.mkdir(parents=True, exist_ok=True)
BASE = "https://www.juntaelectoral.gba.gov.ar/escrutinio-definitivo-2025/"
s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (mapa-del-estado-ba; investigación)"

indice = s.get(BASE + "index.html", timeout=60).text
# El índice omite algunos distritos (San Miguel, Lezama) cuyos PDF sí existen: se prueban todos.
distritos = sorted(set(re.findall(r"distrito_(\d{3})\.html", indice)) | {f"{i:03d}" for i in range(1, 136)})
print(f"{len(distritos)} distritos")

salida = []
for d in distritos:
    pdf = PDFS / f"2025{d}.pdf"
    if not pdf.exists():
        r = s.get(f"{BASE}concejales/2025{d}.pdf", timeout=90)
        if r.status_code != 200 or not r.content.startswith(b"%PDF"):
            print(f"  {d}: sin PDF ({r.status_code})")
            continue
        pdf.write_bytes(r.content)
        time.sleep(0.4)
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
    dist = re.search(r"DISTRITO:\s*(\d+)\s*-\s*(.+)", txt)
    cant = re.search(r"Cargo: Concejal\s+Cantidad:\s*(\d+)", txt)
    electos = []
    # Cada bloque: "2200-ALIANZA FUERZA PATRIA / Bancas Obtenidas: 8 / Titulares 1 NOMBRE ... Suplentes".
    # Si una lista cruza de página, el encabezado se repite y la continuación de
    # suplentes puede venir sin la palabra "Suplentes": por eso se toman como
    # máximo N titulares (N = bancas obtenidas) con número de orden distinto.
    por_lista = {}
    for lista, n, bloque in re.findall(r"^\s*(\d+\s*-\s*[^\n]+?)\s*\n\s*Bancas Obtenidas\s*:\s*(\d+)(.*?)(?=^\s*Suplentes|^\s*\d+\s*-\s*[A-Z]|\Z)",
                                       txt, re.S | re.M):
        lista = re.sub(r"^\d+\s*-\s*", "", lista).strip()
        tope, vistos = por_lista.setdefault(lista, (int(n), {}))
        for orden, nombre in re.findall(r"^\s*(?:Titulares)?\s+(\d+)\s{2,}(\S.*?)\s*$", bloque, re.M):
            if int(orden) <= tope and int(orden) not in vistos:
                vistos[int(orden)] = nombre.strip()
    for lista, (tope, vistos) in por_lista.items():
        electos += [{"orden": o, "nombre": nm, "lista": lista} for o, nm in sorted(vistos.items())]
    salida.append({"codigo": d, "distrito": dist.group(2).strip() if dist else None,
                   "bancas": int(cant.group(1)) if cant else None, "electos": electos,
                   "fuente": f"{BASE}concejales/2025{d}.pdf"})
    ok = "OK" if cant and len(electos) == int(cant.group(1)) else f"REVISAR ({len(electos)} de {cant.group(1) if cant else '?'})"
    print(f"  {d} {salida[-1]['distrito']}: {ok}")

(RAIZ / "raw" / "concejales_2025.json").write_text(json.dumps(
    {"fecha": date.today().isoformat(), "fuente": BASE, "distritos": salida}, ensure_ascii=False, indent=1),
    encoding="utf-8")
print(f"{sum(len(x['electos']) for x in salida)} concejales en {len(salida)} distritos")
