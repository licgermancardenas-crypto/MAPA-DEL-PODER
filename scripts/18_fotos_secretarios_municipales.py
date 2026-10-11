"""Fotos de secretarios municipales desde las páginas de gabinete de cada sitio oficial → data/fotos.json.

Para cada municipio recorre la portada y las páginas que su menú enlaza como gabinete,
funcionarios, autoridades, secretarías o equipo (más algunas rutas típicas). Una imagen se
asigna a un secretario solo si:
  · su texto alternativo, título o nombre de archivo, o la leyenda pegada a ella
    (el texto que la sigue hasta la próxima imagen, como en las tarjetas de gabinete),
    contiene nombre y apellido de ese secretario;
  · y no nombra a ningún otro secretario del mismo municipio.
La comparación es solo contra los secretarios de ESE municipio (unos 6), así que un homónimo
de otro distrito no puede llevarse la foto. Ante duda, no hay foto.

Además, en los sitios hechos con WordPress busca en su banco de imágenes (/wp-json/wp/v2/media)
por apellido, con la misma regla: título, texto alternativo o archivo con nombre y apellido.

Algunos sitios ponen junto al nombre un ícono o la foto del edificio de la secretaría: los íconos
se descartan por tener pocos colores; lo demás hay que mirarlo en raw/hoja_secretarios.png
(una miniatura por foto asignada en la corrida) y anotarlo en raw/fotos_rechazadas.json
({persona_id: página}) para que no vuelva a asignarse.
"""
import base64
import io
import json
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from PIL import Image

urllib3.disable_warnings()
RAIZ = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) mapa-del-estado-ba/0.1"}
RUTAS = ["gabinete", "funcionarios", "autoridades", "municipio/gabinete", "municipio/funcionarios",
         "municipio/autoridades", "gobierno/gabinete", "secretarias", "institucional/gabinete", "equipo"]
MENU = re.compile(r"gabinete|funcionari|autoridad|secretari|equipo|organigrama", re.I)
BASURA = re.compile(r"logo|escudo|banner|icon|sprite|footer|header|flecha|arrow|placeholder|whatsapp|"
                    r"facebook|instagram|twitter|youtube|\.svg|\.gif", re.I)


def slug(x):
    x = unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", x).strip("-")


def get(url):
    try:
        r = requests.get(url, headers=UA, timeout=15, verify=False)
        return r if r.status_code < 400 and "html" in r.headers.get("content-type", "") else None
    except requests.RequestException:
        return None


def texto(x):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip()


def nombra(t, persona):
    """¿El texto (ya en slug) tiene el primer nombre y el último apellido de la persona?"""
    toks = [w for w in slug(persona).split("-") if len(w) > 2]
    if len(toks) < 2:
        return False
    palabras = set(t.split("-"))
    return toks[0] in palabras and toks[-1] in palabras or toks[-1] in palabras and toks[-2] in palabras and len(toks) > 2


def es_icono(src):
    """Dibujo en color con pocos colores (íconos de secretarías). Las fotos en blanco y negro
    también tienen pocos colores, por eso solo se mira si la imagen es en color."""
    im = Image.open(io.BytesIO(base64.b64decode(src.split(",", 1)[1]))).convert("RGB")
    px = list(im.getdata())
    en_color = sum(max(p) - min(p) > 24 for p in px) > len(px) * 0.1
    return en_color and len(set(px)) < 1500


def apellido(nombre):
    return [w for w in slug(nombre).split("-") if len(w) > 2][-1:]


def buscar(muni, web, secretarios, menu=MENU, rutas=RUTAS, nombra=nombra, apellido=apellido):
    """→ {persona_id: (img, pagina)} para un municipio. `secretarios` son todas las personas
    del municipio contra las que se compara ({persona_id: nombre}); `apellido(nombre)` da las
    palabras con las que buscar a cada una en el banco de imágenes de WordPress."""
    home = None
    for esq in ("https://", "http://"):
        host = re.sub(r"^https?://", "", web).strip("/")
        home = get(esq + host)
        if home:
            break
    if not home:
        return {}
    paginas = [home.url]
    hostname = urlparse(home.url).netloc
    for m in re.finditer(r'<a\b[^>]*href="([^"#]+)"[^>]*>(.*?)</a>', home.text, re.I | re.S):
        url = urljoin(home.url, m.group(1))
        etiqueta = texto(m.group(2))
        # textos largos en el menú suelen ser títulos de noticias, no secciones
        if urlparse(url).netloc == hostname and len(etiqueta) <= 40 and menu.search(m.group(1) + " " + etiqueta) \
                and url not in paginas:
            paginas.append(url)
    paginas = paginas[:12] + [urljoin(home.url.rstrip("/") + "/", r) for r in rutas]

    hallado = {}   # persona → (img, pagina)
    dudosas = set()
    for url in dict.fromkeys(paginas):
        r = home if url == home.url else get(url)
        if not r:
            continue
        html = r.text
        imgs = list(re.finditer(r"<img\b[^>]*>", html, re.I))
        for i, m in enumerate(imgs):
            src = re.search(r'(?:data-src|data-lazy-src|src)="([^"]+)"', m.group(0))
            if not src or src.group(1).startswith("data:"):
                continue
            img = urljoin(r.url, src.group(1).split(" ")[0])
            atrib = " ".join(re.findall(r'(?:alt|title)="([^"]*)"', m.group(0)))
            if BASURA.search(img + " " + atrib):
                continue
            fin = imgs[i + 1].start() if i + 1 < len(imgs) else len(html)
            leyenda = texto(html[m.end(): min(fin, m.end() + 600)])
            t = slug(atrib + " " + img.rsplit("/", 1)[-1] + " " + leyenda)
            quienes = [pid for pid, nombre in secretarios.items() if nombra(t, nombre)]
            if len(quienes) == 1:
                pid = quienes[0]
                if pid in hallado and hallado[pid][0] != img:
                    dudosas.add(pid)   # dos fotos distintas para la misma persona: no elegir
                hallado.setdefault(pid, (img, r.url))
    # WordPress: banco de imágenes del propio sitio, buscando por apellido
    base = home.url.rstrip("/") + "/"
    es_wp = True
    for pid, nombre in secretarios.items():
        for palabra in apellido(nombre):
            if pid in hallado or not es_wp:
                break
            try:
                items = requests.get(urljoin(base, "wp-json/wp/v2/media"), headers=UA, timeout=15, verify=False,
                                     params={"search": palabra, "per_page": 20, "_fields": "source_url,title,alt_text,link"}).json()
            except (requests.RequestException, ValueError):
                items = None
            if not isinstance(items, list):
                es_wp = False   # no es WordPress (o no deja consultar): no insistir con los demás
                break
            for it in items:
                img = it.get("source_url", "")
                t = slug(json.dumps(it.get("title", ""), ensure_ascii=False) + " " + it.get("alt_text", "") + " " + img.rsplit("/", 1)[-1])
                if img and not BASURA.search(img) and [p for p, n in secretarios.items() if nombra(t, n)] == [pid]:
                    hallado[pid] = (img, it.get("link") or base)
                    break
    return {pid: v for pid, v in hallado.items() if pid not in dudosas}


if __name__ == "__main__":
    import importlib.util
    spec = importlib.util.spec_from_file_location("p17", RAIZ / "scripts/17_fotos_intendentes_prensa.py")
    p17 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p17)

    grafo = json.loads((RAIZ / "data/grafo.json").read_text())
    fotos_f = RAIZ / "data/fotos.json"
    fotos = json.loads(fotos_f.read_text())
    U = {u["id"]: u for u in grafo["unidades"]}
    P = {p["id"]: p["nombre"] for p in grafo["personas"]}
    rechazadas_f = RAIZ / "raw/fotos_rechazadas.json"
    rechazadas = json.loads(rechazadas_f.read_text()) if rechazadas_f.exists() else {}
    webs = {r["id_municipio"]: r["web"] for r in json.loads((RAIZ / "raw/candidatas_intendentes.json").read_text()) if r["web"]}

    por_muni = {}
    for c in grafo["cargos"]:
        if U[c["unidad"]]["tipo"] == "secretaria_municipal":
            muni = ":".join(c["unidad"].split(":")[:3])
            por_muni.setdefault(muni, {})[c["persona"]] = P[c["persona"]]

    trabajos = [(m, webs[m], secs) for m, secs in por_muni.items()
                if m in webs and any(pid not in fotos for pid in secs)]
    print(f"{len(trabajos)} municipios con sitio y secretarios sin foto")
    n, nuevas = 0, []
    usadas = {f["src"] for f in fotos.values()}
    with ThreadPoolExecutor(8) as ex:
        for (muni, _, _), res in zip(trabajos, ex.map(lambda t: buscar(*t), trabajos)):
            for pid, (img, pagina) in res.items():
                if pid in fotos or rechazadas.get(pid) == pagina:
                    continue
                src = p17.miniatura(img)
                if src and (src in usadas or es_icono(src)):
                    src = None   # silueta genérica repetida, o ícono de colores planos
                if src:
                    nuevas.append(src)
                    usadas.add(src)
                    fotos[pid] = {"src": src, "fuente": f"Sitio oficial del municipio ({urlparse(pagina).netloc})", "url": pagina}
                    n += 1
                    print(f"  {muni.split(':')[-1]}: {P[pid]}", flush=True)
    fotos_f.write_text(json.dumps(fotos, ensure_ascii=False), encoding="utf-8")
    print(f"{n} fotos de secretarios municipales")
    if nuevas:
        hoja = Image.new("RGB", (12 * 112, (len(nuevas) + 11) // 12 * 112), "white")
        for i, src in enumerate(nuevas):
            hoja.paste(Image.open(io.BytesIO(base64.b64decode(src.split(",", 1)[1]))), (i % 12 * 112, i // 12 * 112))
        hoja.save(RAIZ / "raw/hoja_secretarios.png")
        print("Revisar raw/hoja_secretarios.png (en el orden de la lista de arriba)")
