"""Fotos de las personas del grafo → data/fotos.json  {persona_id: {src, fuente, url}}.

Solo se usan fuentes donde la foto está atada al cargo, no a un nombre suelto:
  1. Organigrama GCBA: cada ficha de funcionario trae "Foto del funcionario".
  2. Legislatura CABA: ficha de cada legislador/a.
  3. Diputados y Senado PBA: sitios oficiales (raw/legislatura_pba.json).
  4. Wikidata (imagen de Wikimedia Commons) para cargos de primera línea, SOLO si
     el nombre coincide con una única persona humana argentina con foto.
Una foto equivocada es peor que ninguna: ante duda (0 o >1 candidatos) no hay foto.

Las imágenes se recortan cuadradas (sesgo hacia arriba, donde está la cara), se
reducen a 112 px y se guardan en WebP para incrustarlas en la página (el visor
de Artifacts bloquea imágenes externas). Caché en raw/fotos/.
"""
import base64
import hashlib
import io
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests
from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
CACHE = RAIZ / "raw" / "fotos"
CACHE.mkdir(parents=True, exist_ok=True)
OUT = RAIZ / "data" / "fotos.json"

s = requests.Session()
s.headers["User-Agent"] = "MapaDelEstadoBA/0.1 (proyecto de investigación independiente) python-requests"


def slug(x):
    x = unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", x).strip("-")


def clave(nombre):
    """Misma clave que 03_construir_grafo.py: tokens ordenados, sin tildes."""
    return "p:" + "-".join(sorted(w for w in slug(nombre).split("-") if len(w) > 1))


def miniatura(url):
    """Descarga (con caché) y devuelve data URI WebP 112×112, o None."""
    f = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".webp")
    if not f.exists():
        try:
            r = s.get(url, timeout=40)
            if r.status_code != 200 or len(r.content) < 1500:
                return None
            im = Image.open(io.BytesIO(r.content))
            im = im.convert("RGB")
            w, h = im.size
            lado = min(w, h)
            top = 0 if h > w else 0
            left = (w - lado) // 2
            if h > w:                      # retrato: la cara suele estar en el tercio superior
                top = min(int(h * 0.06), h - lado)
            im = im.crop((left, top, left + lado, top + lado)).resize((112, 112), Image.LANCZOS)
            im.save(f, "WEBP", quality=72, method=6)
        except Exception:
            return None
    return "data:image/webp;base64," + base64.b64encode(f.read_bytes()).decode()


grafo = json.loads((RAIZ / "data/grafo.json").read_text())
PERSONAS = {p["id"] for p in grafo["personas"]}
fotos = {}
if OUT.exists():
    fotos = json.loads(OUT.read_text())


def asignar(nombre, url, fuente, pagina=None):
    pid = clave(nombre)
    if pid not in PERSONAS or pid in fotos and fotos[pid]["fuente"] != "Wikidata":
        return False
    src = miniatura(url)
    if src:
        fotos[pid] = {"src": src, "fuente": fuente, "url": pagina or url}
        return True
    return False


def asignar_en_cuerpo(nombre, url, fuente, pagina, raiz):
    """Como asignar(), pero si el nombre oficial es más largo que el cargado
    ("Grillo, Alejandro Omar" vs "Alejandro Grillo") busca, SOLO entre quienes
    tienen cargo dentro de `raiz`, a una única persona cuyo nombre esté contenido."""
    if asignar(nombre, url, fuente, pagina):
        return True
    toks = set(clave(nombre)[2:].split("-"))
    dentro = {c["persona"] for c in grafo["cargos"] if c["unidad"].startswith(raiz)}
    cands = [pid for pid in dentro if set(pid[2:].split("-")) <= toks and len(pid[2:].split("-")) >= 2]
    if len(cands) == 1 and cands[0] not in fotos:
        src = miniatura(url)
        if src:
            fotos[cands[0]] = {"src": src, "fuente": fuente, "url": pagina}
            return True
    return False


def paso(nombre):
    print(f"── {nombre}", flush=True)


# 1. Organigrama GCBA ─────────────────────────────────────────────────────────
paso("Ejecutivo CABA")
org = json.loads((RAIZ / "raw/caba_organigrama/organigrama.json").read_text())["areas"]
n = 0
for nodos in org.values():
    for nd in nodos:
        if not nd.get("url") or "/perfil_institucional/" not in nd["url"] or len(nd["titulares"]) != 1:
            continue
        pid = clave(nd["titulares"][0]["nombre"])
        if pid in fotos:
            continue
        try:
            t = s.get(nd["url"], timeout=40).text
        except requests.RequestException:
            continue
        # alt varía: "Foto del funcionario", "Foto de funcionario", "Imagen del funcionario X"
        m = re.search(r'<img src="([^"]+)" alt="[^"]*funcionari[^"]*"', t, re.I)
        if m and asignar(nd["titulares"][0]["nombre"], "https://buenosaires.gob.ar" + m.group(1)
                         if m.group(1).startswith("/") else m.group(1), "Organigrama GCBA", nd["url"]):
            n += 1
        time.sleep(0.25)
print(f"   {n} fotos")

# 2. Legislatura CABA ─────────────────────────────────────────────────────────
paso("Legislatura CABA")
t = s.get("https://www.legislatura.gob.ar/", timeout=60).text
n = 0
for url in sorted(set(re.findall(r'href="(https://www\.legislatura\.gob\.ar/legislador/[^"]+)"', t))):
    try:
        p = s.get(url, timeout=40).text
    except requests.RequestException:
        continue
    m = re.search(r'<img src="(https://parlamentaria\.legislatura\.gob\.ar/uploads/imagenes/legislador/[^"]+)" alt="([^"]+)"', p)
    if m and asignar_en_cuerpo(m.group(2), m.group(1), "Legislatura CABA", url, "caba:legislatura"):
        n += 1
    time.sleep(0.25)
print(f"   {n} fotos")

# 3. Legislatura PBA ──────────────────────────────────────────────────────────
paso("Legislatura PBA")
lp = json.loads((RAIZ / "raw/legislatura_pba.json").read_text())
n = 0
for x in lp["diputados"] + lp["senadores"]:
    if x.get("foto") and asignar(x["apellido_nombre"], x["foto"],
                                 "Cámara de Diputados PBA" if "hcdiputados" in x["foto"] else "Senado PBA", x["url"]):
        n += 1
print(f"   {n} fotos")

# 4. Wikidata para primera línea ─────────────────────────────────────────────
paso("Wikidata")
U = {u["id"]: u for u in grafo["unidades"]}
# Sin concejales ni direcciones: un homónimo notable les pondría la foto de otra persona.
PRIMERA = {"gobernacion", "ministerio", "corte", "ministerio_publico"}
OFICIOS = {"Q82955", "Q40348", "Q16533", "Q188094", "Q212238", "Q1930187", "Q1622272"}  # político, abogado, juez, economista, funcionario, periodista, profesor univ.
PERFIL = re.compile(r"pol[ií]tic|abogad|jue[zc]|ministr|funcionari|intendent|diputad|senador|economista|legislador|politician|lawyer|judge", re.I)


def es_primera_linea(c):
    u = U[c["unidad"]]
    if u["tipo"] in PRIMERA or c["rol"].startswith(("Intendente", "Juez/a del TSJ")):
        return True
    padre = U.get(u["padre"] or "", {})
    return (padre.get("tipo") in ("gobernacion",) and u["tipo"] != "bloque") or u["padre"] == "pba:organismos-constitucionales"


candidatos = {}
for c in grafo["cargos"]:
    if c["persona"] not in fotos and es_primera_linea(c):
        candidatos[c["persona"]] = next(p["nombre"] for p in grafo["personas"] if p["id"] == c["persona"]) \
            if c["persona"] not in candidatos else candidatos[c["persona"]]
print(f"   {len(candidatos)} personas de primera línea sin foto")

WD = "https://www.wikidata.org/w/api.php"


def wd(params):
    """GET a la API de Wikidata respetando su límite: 1 pedido/s y espera ante 429."""
    for intento in range(5):
        time.sleep(1.0)
        r = s.get(WD, params={**params, "format": "json", "maxlag": 5}, timeout=30)
        if r.status_code == 429 or '"maxlag"' in r.text[:300]:
            time.sleep(int(r.headers.get("Retry-After", 20)) + 5 * intento)
            continue
        return r.json()
    raise requests.RequestException("Wikidata no responde")


n = 0
for pid, nombre in candidatos.items():
    toks = set(slug(nombre).split("-"))
    try:
        res = wd({"action": "wbsearchentities", "search": nombre, "language": "es", "type": "item", "limit": 7}).get("search", [])
        partes = nombre.split()
        if not res and len(partes) >= 3:
            # segundo nombre de más: probar con primer nombre + apellido
            res = wd({"action": "wbsearchentities", "search": f"{partes[0]} {partes[-1]}", "language": "es",
                      "type": "item", "limit": 7}).get("search", [])
        ids = [r["id"] for r in res]
        if not ids:
            continue
        ents = wd({"action": "wbgetentities", "ids": "|".join(ids), "props": "claims|labels|descriptions",
                   "languages": "es|en"})["entities"]
    except (requests.RequestException, ValueError, KeyError):
        continue
    ok = []
    for e in ents.values():
        cl = e.get("claims", {})
        humano = any(x["mainsnak"].get("datavalue", {}).get("value", {}).get("id") == "Q5" for x in cl.get("P31", []))
        argentino = any(x["mainsnak"].get("datavalue", {}).get("value", {}).get("id") == "Q414" for x in cl.get("P27", [])) \
            or "argentin" in json.dumps(e.get("descriptions", {}), ensure_ascii=False).lower()
        label = (e.get("labels", {}).get("es") or e.get("labels", {}).get("en") or {}).get("value", "")
        ltoks = {w for w in slug(label).split("-") if len(w) > 1}
        coincide = len(ltoks) >= 2 and (ltoks <= toks or toks <= ltoks)
        img = cl.get("P18", [{}])[0].get("mainsnak", {}).get("datavalue", {}).get("value")
        oficio = any(x["mainsnak"].get("datavalue", {}).get("value", {}).get("id") in OFICIOS for x in cl.get("P106", [])) \
            or PERFIL.search(json.dumps(e.get("descriptions", {}), ensure_ascii=False))
        if humano and argentino and coincide and oficio and img:
            ok.append((e["id"], img))
    if len(ok) == 1:
        qid, img = ok[0]
        url = "https://commons.wikimedia.org/wiki/Special:FilePath/" + requests.utils.quote(img.replace(" ", "_")) + "?width=240"
        src = miniatura(url)
        if src:
            fotos[pid] = {"src": src, "fuente": "Wikidata", "url": f"https://www.wikidata.org/wiki/{qid}"}
            n += 1
print(f"   {n} fotos")

OUT.write_text(json.dumps(fotos, ensure_ascii=False), encoding="utf-8")
por_fuente = {}
for f in fotos.values():
    por_fuente[f["fuente"]] = por_fuente.get(f["fuente"], 0) + 1
print(f"{len(fotos)} personas con foto · {OUT.stat().st_size/1e6:.1f} MB · {por_fuente}")
