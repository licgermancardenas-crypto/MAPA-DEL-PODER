"""Tercera vuelta para los intendentes sin foto: Wikimedia Commons.

Para cada intendente sin foto busca archivos cuyo título tenga su nombre y apellido, y solo
los toma si la descripción o las categorías del archivo nombran su partido, o lo ubican como
político argentino sin decir que fue intendente de otro distrito (así se descartan los
homónimos: futbolistas, cineastas, intendentes de otra época y otro lugar…).

Suma las candidatas a raw/candidatas_intendentes.json (sin pisar las que ya estaban).
Igual que antes, nada entra al grafo sin aprobación manual (12_aprobar_fotos.py).
"""
import base64
import hashlib
import io
import json
import re
import time
import unicodedata
from pathlib import Path

import requests
from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
CACHE = RAIZ / "raw" / "fotos"
CAND_F = RAIZ / "raw" / "candidatas_intendentes.json"
API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "mapa-del-estado-ba/0.1 (https://github.com/licgermancardenas-crypto/MAPA-DEL-PODER)"}
CONTEXTO = re.compile(r"intendent|mayors? of|municipalidad|politic\w* (argentin|of argentina)|deputies of argentina", re.I)


def norm(x):
    return unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower()


def api(**p):
    """GET a la API de Commons; espera y reintenta si limita los pedidos."""
    for i in range(5):
        try:
            r = requests.get(API, params={**p, "format": "json"}, headers=UA, timeout=30)
            if r.status_code == 200 and r.text.startswith("{"):
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(5 * (i + 1))
    return {}


def miniatura(img):
    try:
        r = requests.get(img, headers=UA, timeout=30)
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception:
        return None
    w, h = im.size
    if min(w, h) < 120 or not 0.6 <= w / h <= 1.7:
        return None
    lado = min(w, h)
    left, top = (w - lado) // 2, (min(int(h * 0.06), h - lado) if h > w else 0)
    f = CACHE / (hashlib.sha1(img.encode()).hexdigest() + ".webp")
    im.crop((left, top, left + lado, top + lado)).resize((112, 112), Image.LANCZOS).save(f, "WEBP", quality=72)
    return "data:image/webp;base64," + base64.b64encode(f.read_bytes()).decode()


def buscar(r, nombre):
    limpio = re.sub(r"'[^']*'|\b[A-Z]\.\s*", "", nombre).split()
    nom, ap = norm(limpio[0]), norm(limpio[-1])
    res = api(action="query", list="search", srnamespace=6, srsearch=f'intitle:"{ap}" {nom}', srlimit=20)
    titulos = [s["title"] for s in res.get("query", {}).get("search", [])
               if nom in norm(s["title"]) and ap in norm(s["title"]) and re.search(r"\.(jpe?g|png|webp)$", s["title"], re.I)]
    if not titulos:
        return []
    info = api(action="query", titles="|".join(titulos[:20]), prop="imageinfo", iiprop="url|extmetadata", iiurlwidth=400)
    ya = {c["img"] for c in r["candidatas"]}
    nuevas = []
    for p in info.get("query", {}).get("pages", {}).values():
        ii = p["imageinfo"][0]
        meta = ii["extmetadata"]
        ctx = " ".join(re.sub(r"<[^>]+>", " ", meta.get(k, {}).get("value", "")) for k in ("ImageDescription", "Categories"))
        en_su_partido = norm(r["municipio"]) in norm(ctx)
        de_otro_lado = re.search(r"intendente de|mayors of", ctx, re.I)  # homónimo que gobernó otro distrito
        if ii["thumburl"] in ya or not (en_su_partido or CONTEXTO.search(ctx) and not de_otro_lado):
            continue
        src = miniatura(ii["thumburl"])
        if src:
            nuevas.append({"img": ii["thumburl"], "pagina": ii["descriptionurl"], "puntaje": 5, "src": src})
        time.sleep(1)
    r["candidatas"] += nuevas
    return nuevas


if __name__ == "__main__":
    cand = json.loads(CAND_F.read_text())
    fotos = json.loads((RAIZ / "data/fotos.json").read_text())
    grafo = json.loads((RAIZ / "data/grafo.json").read_text())
    personas = {p["id"]: p["nombre"] for p in grafo["personas"]}
    INT = {c["unidad"].rsplit(":", 1)[0]: c["persona"] for c in grafo["cargos"] if c["rol"].startswith("Intendente")}

    pendientes = [r for r in cand if INT.get(r["id_municipio"]) and INT[r["id_municipio"]] not in fotos]
    print(f"{len(pendientes)} intendentes sin foto")
    for r in pendientes:
        nuevas = buscar(r, personas[INT[r["id_municipio"]]])
        if nuevas:
            print(f"  {r['municipio']}: {len(nuevas)} nuevas")
        time.sleep(1.5)
    CAND_F.write_text(json.dumps(cand, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{sum(bool(r['candidatas']) for r in cand)} municipios con candidatas en total")
