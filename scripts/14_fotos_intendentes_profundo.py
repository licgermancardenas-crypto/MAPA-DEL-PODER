"""Segunda vuelta para los intendentes que siguen sin foto (después de 11_fotos_intendentes.py).

Prueba, para cada municipio pendiente:
  · variantes del dominio (http/https, con y sin www) para los sitios que no respondieron;
  · rutas típicas: /intendente, /intendencia, /autoridades, /gabinete, /institucional…;
  · el buscador del sitio (?s=apellido) y, en los WordPress, su API: /wp-json/wp/v2/media?search=
    y /wp-json/wp/v2/search?search=;
  · la imagen de vista previa (og:image) de las páginas que hablan del intendente.

Suma las candidatas a raw/candidatas_intendentes.json (sin pisar las que ya estaban).
Igual que antes, nada entra al grafo sin aprobación manual (12_aprobar_fotos.py).
"""
import base64
import hashlib
import io
import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from PIL import Image

urllib3.disable_warnings()
RAIZ = Path(__file__).resolve().parents[1]
CACHE = RAIZ / "raw" / "fotos"
CAND_F = RAIZ / "raw" / "candidatas_intendentes.json"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) mapa-del-estado-ba/0.1"}
RUTAS = ["", "intendente", "el-intendente", "intendencia", "autoridades", "gabinete", "institucional",
         "municipio", "gobierno", "nuestro-intendente", "?s=intendente"]
BASURA = re.compile(r"logo|escudo|banner|icon|sprite|footer|header|flecha|arrow|placeholder|whatsapp|"
                    r"facebook|instagram|twitter|youtube|\.svg|\.gif", re.I)


def slug(x):
    x = unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", x).strip("-")


def get(url, **kw):
    try:
        return requests.get(url, headers=UA, timeout=12, verify=False, **kw)
    except requests.RequestException:
        return None


def texto(x):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip()


def bases(web):
    """Variantes del dominio para los sitios que no respondieron."""
    host = re.sub(r"^https?://", "", (web or "").strip()).strip("/")
    if not host:
        return []
    sin_www = host[4:] if host.startswith("www.") else host
    out = []
    for h in (host, sin_www, "www." + sin_www):
        for esq in ("https://", "http://"):
            u = esq + h
            if u not in out:
                out.append(u)
    return out


def miniatura(img):
    r = get(img)
    if not r or r.status_code >= 400 or len(r.content) < 4000:
        return None
    try:
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


def buscar(r):
    ap = r["apellido"]
    puntaje = {}

    def mirar_html(url, html):
        for m in re.finditer(r"<img\b[^>]*>", html, re.I):
            src = re.search(r'(?:data-src|data-lazy-src|src)="([^"]+)"', m.group(0))
            alt = (re.search(r'(?:alt|title)="([^"]*)"', m.group(0)) or [None, ""])[1]
            if not src or src.group(1).startswith("data:"):
                continue
            img = urljoin(url, src.group(1).split(" ")[0])
            if BASURA.search(img + " " + alt):
                continue
            cerca = slug(texto(html[max(0, m.start() - 400): m.end() + 400]))
            p = 3 * (ap in slug(alt + " " + img.rsplit("/", 1)[-1])) + (ap in cerca) + ("intendent" in cerca)
            if p >= 2:
                puntaje[img] = max(p, puntaje.get(img, 0))
        og = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html, re.I)
        if og and ("intendent" in slug(url) or ap in slug(url) or ap in slug(texto(html[:3000]))):
            img = urljoin(url, og.group(1))
            if not BASURA.search(img):
                puntaje[img] = max(2, puntaje.get(img, 0))

    base_ok = None
    for base in bases(r["web"]):
        home = get(base)
        if home is not None and home.status_code < 400:
            base_ok = home.url.rstrip("/") + "/"
            mirar_html(home.url, home.text)
            break
    if not base_ok:
        return r, "sitio caído"

    for ruta in RUTAS[1:]:
        resp = get(urljoin(base_ok, ruta))
        if resp is not None and resp.status_code < 400 and "html" in resp.headers.get("content-type", ""):
            mirar_html(resp.url, resp.text)

    # WordPress: buscador de medios y de contenidos por apellido
    for api, campo in [(f"wp-json/wp/v2/media?search={ap}&per_page=20", "source_url"),
                       (f"wp-json/wp/v2/search?search={ap}&per_page=10", "url")]:
        resp = get(urljoin(base_ok, api))
        if not resp or resp.status_code >= 400:
            continue
        try:
            items = resp.json()
        except ValueError:
            continue
        for it in items if isinstance(items, list) else []:
            valor = it.get(campo, "")
            if campo == "source_url" and valor and not BASURA.search(valor):
                alt = (it.get("alt_text") or "") + " " + json.dumps(it.get("title", ""), ensure_ascii=False)
                if ap in slug(alt + " " + valor.rsplit("/", 1)[-1]):
                    puntaje[valor] = max(3, puntaje.get(valor, 0))
            elif campo == "url" and valor:
                pag = get(valor)
                if pag is not None and pag.status_code < 400:
                    mirar_html(pag.url, pag.text)

    nuevas = []
    ya = {c["img"] for c in r["candidatas"]}
    for img, p in sorted(puntaje.items(), key=lambda kv: -kv[1]):
        if img in ya:
            continue
        src = miniatura(img)
        if src:
            nuevas.append({"img": img, "pagina": base_ok, "puntaje": p, "src": src})
        if len(nuevas) == 3:
            break
    r["candidatas"] += nuevas
    return r, f"{len(nuevas)} nuevas"


if __name__ == "__main__":
    cand = json.loads(CAND_F.read_text())
    fotos = json.loads((RAIZ / "data/fotos.json").read_text())
    grafo = json.loads((RAIZ / "data/grafo.json").read_text())
    INT = {c["unidad"].rsplit(":", 1)[0]: c["persona"] for c in grafo["cargos"] if c["rol"].startswith("Intendente")}

    pendientes = [r for r in cand if r["web"] and INT.get(r["id_municipio"]) not in fotos]
    print(f"{len(pendientes)} intendentes sin foto")
    with ThreadPoolExecutor(8) as ex:
        for r, estado in ex.map(buscar, pendientes):
            if not estado.startswith("0"):
                print(f"  {r['municipio']}: {estado}")
    CAND_F.write_text(json.dumps(cand, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{sum(bool(r['candidatas']) for r in cand)} municipios con candidatas en total")
