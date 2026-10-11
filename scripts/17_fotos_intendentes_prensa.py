"""Cuarta vuelta para los intendentes sin foto: bancos de imágenes de portales de noticias.

Varios portales regionales están hechos con WordPress y su API deja buscar imágenes por
nombre (/wp-json/wp/v2/media?search=apellido). Los periodistas suelen nombrar el archivo
con el apellido del intendente cuando la foto es de él solo ("DINAPOLI.jpg", "Pablo-Zurro.jpg").

Toma una imagen si su título o nombre de archivo tiene el apellido y además el nombre de pila,
el partido o nada más que el apellido; descarta las que nombran a otra persona ("zurro y
cristina", "dinapoli-kicillof"), que suelen ser fotos de reuniones.

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
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) mapa-del-estado-ba/0.1"}
PORTALES = ["https://www.infozona.com.ar", "https://www.labrujula24.com", "https://elcuartopoder.com.ar"]
RELLENO = {"intendente", "intendenta", "jpg", "jpeg", "png", "webp", "scaled", "foto", "de", "del", "la", "el"}


def slug(x):
    x = unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", x).strip("-")


def miniatura(img):
    try:
        r = requests.get(img, headers=UA, timeout=20)
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


def sirve(titulo, nombre, ap, muni):
    """¿El título/archivo habla de este intendente y de nadie más?"""
    if " y " in f" {titulo.replace('-', ' ')} " or ap not in titulo:
        return False
    resto = [p.rstrip("0123456789") for p in titulo.split("-")]
    resto = [p for p in resto if p and p not in RELLENO and not re.fullmatch(r"\d+x|x\d*", p)]
    conocidas = set(ap.split("-")) | set(nombre) | set(muni.split("-"))
    return all(p in conocidas for p in resto)


def buscar(r, persona):
    limpio = re.sub(r"'[^']*'|\b[A-Z]\.\s*", "", persona).split()
    nombre, ap = [slug(x) for x in limpio[:-1]], slug(limpio[-1])
    muni = slug(r["municipio"])
    ya = {c["img"] for c in r["candidatas"]}
    nuevas = []
    for portal in PORTALES:
        try:
            items = requests.get(f"{portal}/wp-json/wp/v2/media", headers=UA, timeout=20,
                                 params={"search": ap, "per_page": 30, "_fields": "source_url,title,link"}).json()
        except (requests.RequestException, ValueError):
            continue
        for it in items if isinstance(items, list) else []:
            img = it.get("source_url", "")
            titulo = slug(it.get("title", {}).get("rendered", "")) + "-" + slug(img.rsplit("/", 1)[-1].rsplit(".", 1)[0])
            if img in ya or not sirve(titulo, nombre, ap, muni):
                continue
            src = miniatura(img)
            if src:
                nuevas.append({"img": img, "pagina": it.get("link") or portal, "puntaje": 3, "src": src})
                ya.add(img)
            if len(nuevas) == 3:
                break
        if len(nuevas) == 3:
            break
        time.sleep(0.5)
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
    CAND_F.write_text(json.dumps(cand, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{sum(bool(r['candidatas']) for r in cand)} municipios con candidatas en total")
