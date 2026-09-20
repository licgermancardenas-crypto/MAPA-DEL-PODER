"""Integrantes de la Legislatura bonaerense desde los sitios oficiales de cada cámara,
con bloque, sección electoral, mandato y URL de la foto oficial.

  Diputados  hcdiputados-ba.gov.ar/index.php?page=diputados&search=seccionCompleta  (92)
  Senado     senado-ba.gov.ar/Senadores.aspx                                        (46)

Reemplaza a ../intendentes/data/legisladores.json, que tenía 80 de 92 diputados.
"""
import html as H
import json
import re
from datetime import date
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parents[1] / "raw" / "legislatura_pba.json"
s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (mapa-del-estado-ba; investigación)"


def texto(x):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", x))).replace("\xa0", " ").strip()


SECCION = {"PRIMERA": 1, "SEGUNDA": 2, "TERCERA": 3, "CUARTA": 4, "QUINTA": 5, "SEXTA": 6, "SEPTIMA": 7,
           "SÉPTIMA": 7, "OCTAVA": 8, "CAPITAL": 8}

# Diputados: tabla con foto | nombre (APELLIDO NOMBRES) | bloque | mandato | distrito y sección.
base = "https://www.hcdiputados-ba.gov.ar/"
t = s.get(base + "index.php?page=diputados&search=seccionCompleta", timeout=60).text
diputados = []
for fila in re.findall(r"<tr>\s*<th scope=\"row\">(.*?)</tr>", t, re.S):
    foto = re.search(r'src="\./([^"]+)"', fila)
    m = re.search(r'page=diputado&id=(\d+)"[^>]*>(.*?)</a>', fila, re.S)
    tds = re.findall(r"<td>(.*?)</td>", fila, re.S)
    if not m or len(tds) < 4:
        continue
    sec = re.search(r"SECCIÓN ELECTORAL:</span>\s*<span[^>]*>(.*?)</span>", fila, re.S)
    dist = re.search(r"DISTRITO:</span>\s*<span[^>]*>(.*?)</span>", fila, re.S)
    if any(d["id"] == m.group(1) for d in diputados):   # la tabla se repite por sección y por bloque
        continue
    diputados.append({
        "id": m.group(1), "apellido_nombre": texto(m.group(2)), "bloque": texto(tds[1]).title(),
        "mandato": texto(tds[2]), "seccion": SECCION.get(texto(sec.group(1)).upper()) if sec else None,
        "distrito": texto(dist.group(1)).title() if dist else None,
        "foto": base + foto.group(1) if foto else None, "url": f"{base}index.php?page=diputado&id={m.group(1)}"})

# Senado: tarjetas con nombre "Apellido, Nombre", bloque, "Sección: 2º", mandato y foto de fondo.
base = "https://www.senado-ba.gov.ar/"
t = s.get(base + "Senadores.aspx", timeout=60).text
senadores = []
for idp, bloque in re.findall(r'href=["\']Senador\.aspx\?idP=(\d+)["\']>(.*?)(?=href=["\']Senador\.aspx\?idP=|</form>)', t, re.S):
    campos = [c for c in (texto(x) for x in re.split(r"<[^>]+>", bloque)) if c]
    foto = re.search(r"url\('(/imagenes/Senadores/[^']+)'\)", bloque)
    if not campos:
        continue
    sec = next((c for c in campos if c.startswith("Sección")), "")
    sec = re.search(r"\d", sec).group() if re.search(r"\d", sec) else SECCION.get(sec.split(":")[-1].strip().upper())
    senadores.append({
        "id": idp, "apellido_nombre": campos[0], "bloque": campos[1].title() if len(campos) > 1 else None,
        "seccion": int(sec) if sec else None, "mandato": next((c for c in campos if re.fullmatch(r"\d{4}-\d{4}", c)), None),
        "foto": base + foto.group(1).lstrip("/") if foto else None, "url": f"{base}Senador.aspx?idP={idp}"})

OUT.write_text(json.dumps({"fecha": date.today().isoformat(), "diputados": diputados, "senadores": senadores},
                          ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{len(diputados)} diputados · {len(senadores)} senadores · "
      f"{sum(bool(x['foto']) for x in diputados + senadores)} con foto")
