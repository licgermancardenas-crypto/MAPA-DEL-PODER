"""Candidatas de foto para cada intendente, tomadas del sitio oficial de su municipio.
El resultado NO entra solo al grafo: genera una planilla para aprobar a mano
(web/revision_intendentes.html) y las aprobadas se cargan con 12_aprobar_fotos.py.

  1. gba.gob.ar/municipios → sitio oficial e intendente vigente de cada municipio.
  2. En el sitio: portada + hasta 8 páginas internas con "intendente", "gobierno",
     "autoridades", "gabinete" o "institucional" en el link.
  3. Puntaje de cada imagen: apellido en alt/archivo (+3), apellido en el texto de
     alrededor (+1), "intendent" cerca (+1). Se descartan logos y banners, y las
     imágenes que no tienen proporción de retrato (0,6–1,7).

También reporta dónde el intendente vigente no coincide con el dataset 2023.
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
OUT = RAIZ / "raw" / "candidatas_intendentes.json"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) mapa-del-estado-ba/0.1"}


def slug(x):
    x = unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", x).strip("-")


def get(url, **kw):
    try:
        return requests.get(url, headers=UA, timeout=15, verify=False, **kw)
    except requests.RequestException:
        return None


def texto(x):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip()


# 1. Guía de municipios ───────────────────────────────────────────────────────
guia = requests.get("https://www.gba.gob.ar/municipios", headers=UA, timeout=60).text
munis = []
for b in re.findall(r'<div id="[^"]+" class="tabcontent">(.*?)</div>', guia, re.S):
    nom = re.search(r'<h3[^>]*>(.*?)</h3>', b, re.S)
    inte = re.search(r"Intendente:\s*([^<]+)", b)
    web = re.search(r'href="\s*([^"]+?)\s*"', b)
    if nom and inte:
        munis.append({"municipio": texto(nom.group(1)), "intendente_guia": texto(inte.group(1)),
                      "web": web.group(1).strip() if web else None})
print(f"{len(munis)} municipios en la guía")

nuestros = {slug(m["municipio"]): m for m in json.loads((RAIZ.parent / "intendentes/data/intendentes.json").read_text())}
ALIAS = {"25-de-mayo": "veinticinco-de-mayo", "9-de-julio": "nueve-de-julio", "partido-de-la-costa": "la-costa",
         "coronel-de-marina-l-rosales": "coronel-rosales", "general-lamadrid": "general-la-madrid",
         "olavarria": "olavarria", "carmen-de-patagones": "patagones"}


def apellido(nombre):
    """'Javier MARTÍNEZ' → 'martinez' (la guía escribe el apellido en mayúsculas)."""
    may = [w for w in nombre.split() if len(w) > 2 and w.isupper()]
    return slug(" ".join(may) if may else nombre.split()[-1])


# 2-3. Rastreo ────────────────────────────────────────────────────────────────
CLAVES = re.compile(r"intendent|gobierno|autoridad|gabinete|institucional|municipio|quienes", re.I)
BASURA = re.compile(r"logo|escudo|banner|icon|sprite|footer|header|flecha|arrow|placeholder|whatsapp|facebook|instagram|twitter|youtube|\.svg|\.gif", re.I)


def rastrear(m):
    m = {**m, "apellido": apellido(m["intendente_guia"])}
    if not m["web"]:
        return {**m, "candidatas": [], "error": "sin sitio"}
    ap = apellido(m["intendente_guia"])
    home = get(m["web"] if m["web"].startswith("http") else "http://" + m["web"])
    if not home or home.status_code >= 400:
        return {**m, "candidatas": [], "error": "sitio caído"}
    base = home.url
    paginas = [(base, home.text)]
    internos = []
    for href, txt in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', home.text, re.S):
        u = urljoin(base, href)
        if urlparse(u).netloc == urlparse(base).netloc and CLAVES.search(href + " " + texto(txt)) and u not in internos:
            internos.append(u)
    for u in internos[:8]:
        r = get(u)
        if r and r.status_code < 400 and "html" in r.headers.get("content-type", ""):
            paginas.append((r.url, r.text))

    puntaje = {}
    for url, html in paginas:
        for m_img in re.finditer(r"<img\b[^>]*>", html, re.I):
            tag = m_img.group(0)
            src = re.search(r'(?:data-src|data-lazy-src|src)="([^"]+)"', tag)
            if not src or src.group(1).startswith("data:"):
                continue
            img = urljoin(url, src.group(1).split(" ")[0])
            alt = (re.search(r'(?:alt|title)="([^"]*)"', tag) or [None, ""])[1]
            if BASURA.search(img + " " + alt):
                continue
            cerca = slug(texto(html[max(0, m_img.start() - 400): m_img.end() + 400]))
            p = 3 * (ap in slug(alt + " " + img.rsplit("/", 1)[-1])) + (ap in cerca) + ("intendent" in cerca)
            if p >= 2:
                prev = puntaje.get(img, (0, None))
                puntaje[img] = (max(p, prev[0]), url)

    candidatas = []
    for img, (p, pagina) in sorted(puntaje.items(), key=lambda kv: -kv[1][0])[:6]:
        r = get(img)
        if not r or r.status_code >= 400 or len(r.content) < 4000:
            continue
        try:
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception:
            continue
        w, h = im.size
        if min(w, h) < 120 or not 0.6 <= w / h <= 1.7:
            continue
        lado = min(w, h)
        left, top = (w - lado) // 2, (min(int(h * 0.06), h - lado) if h > w else 0)
        th = im.crop((left, top, left + lado, top + lado)).resize((112, 112), Image.LANCZOS)
        f = CACHE / (hashlib.sha1(img.encode()).hexdigest() + ".webp")
        th.save(f, "WEBP", quality=72, method=6)
        candidatas.append({"img": img, "pagina": pagina, "puntaje": p,
                           "src": "data:image/webp;base64," + base64.b64encode(f.read_bytes()).decode()})
        if len(candidatas) == 3:
            break
    return {**m, "apellido": ap, "candidatas": candidatas}


with ThreadPoolExecutor(10) as ex:
    res = list(ex.map(rastrear, munis))

# Cruce con el dataset: ¿el intendente vigente es el mismo que el electo en 2023?
for r in res:
    k = slug(r["municipio"])
    k = ALIAS.get(k, k)
    nuestro = nuestros.get(k)
    r["id_municipio"] = f"pba:muni:{k}" if nuestro else None
    r["intendente_dataset"] = nuestro["intendente"] if nuestro else None
    r["cambio"] = bool(nuestro) and r["apellido"] not in slug(nuestro["intendente"])

OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{sum(bool(r['candidatas']) for r in res)} con candidatas · "
      f"{sum(1 for r in res if not r['id_municipio'])} sin cruzar · {sum(r['cambio'] for r in res)} con intendente distinto")
for r in res:
    if r["cambio"]:
        print(f"  CAMBIO {r['municipio']}: guía «{r['intendente_guia']}» / dataset «{r['intendente_dataset']}»")
    if not r["id_municipio"]:
        print(f"  SIN CRUCE {r['municipio']}")


# 4. Segunda pasada con navegador para los sitios que arman la página con JS ──
def pasada_navegador(pendientes):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(ignore_https_errors=True, user_agent=UA["User-Agent"])
        for r in pendientes:
            ap, puntaje = r["apellido"], {}
            try:
                pg = ctx.new_page()
                pg.goto(r["web"] if r["web"].startswith("http") else "http://" + r["web"], timeout=30000,
                        wait_until="domcontentloaded")
                pg.wait_for_timeout(2500)
                urls = [pg.url] + [u for u in pg.eval_on_selector_all(
                    "a[href]", "els => els.filter(a => /intendent|gobierno|autoridad|gabinete|institucional/i"
                               ".test(a.href + ' ' + a.innerText)).map(a => a.href)") if u.startswith("http")][:5]
                for u in dict.fromkeys(urls):
                    if u != pg.url:
                        pg.goto(u, timeout=30000, wait_until="domcontentloaded")
                        pg.wait_for_timeout(2000)
                    for src, alt, cerca, w, h in pg.eval_on_selector_all("img", """els => els.map(e => [
                            e.currentSrc || e.src, (e.alt || '') + ' ' + (e.title || ''),
                            ((e.closest('div,figure,section,article') || e.parentElement || {}).innerText || '').slice(0, 600),
                            e.naturalWidth, e.naturalHeight])"""):
                        if not src or src.startswith("data:") or BASURA.search(src + " " + alt):
                            continue
                        if min(w, h) < 120 or not 0.6 <= w / max(h, 1) <= 1.7:
                            continue
                        p_ = 3 * (ap in slug(alt + " " + src.rsplit("/", 1)[-1])) + (ap in slug(cerca)) + \
                            ("intendent" in slug(cerca))
                        if p_ >= 2 and p_ > puntaje.get(src, (0,))[0]:
                            puntaje[src] = (p_, pg.url)
                pg.close()
            except Exception:
                continue
            for img, (p_, pagina) in sorted(puntaje.items(), key=lambda kv: -kv[1][0])[:3]:
                resp = get(img)
                if not resp or resp.status_code >= 400:
                    continue
                try:
                    im = Image.open(io.BytesIO(resp.content)).convert("RGB")
                except Exception:
                    continue
                w, h = im.size
                lado = min(w, h)
                left, top = (w - lado) // 2, (min(int(h * 0.06), h - lado) if h > w else 0)
                f = CACHE / (hashlib.sha1(img.encode()).hexdigest() + ".webp")
                im.crop((left, top, left + lado, top + lado)).resize((112, 112), Image.LANCZOS).save(f, "WEBP", quality=72)
                r["candidatas"].append({"img": img, "pagina": pagina, "puntaje": p_,
                                        "src": "data:image/webp;base64," + base64.b64encode(f.read_bytes()).decode()})
            print(f"  {r['municipio']}: {len(r['candidatas'])} candidatas (navegador)", flush=True)
        b.close()


pasada_navegador([r for r in res if not r["candidatas"] and r["web"]])
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"Total: {sum(bool(r['candidatas']) for r in res)} municipios con candidatas")
