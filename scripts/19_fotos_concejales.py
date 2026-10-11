"""Fotos de concejales desde los sitios de cada Concejo Deliberante → data/fotos.json.

El sitio del Concejo se busca en los enlaces de la portada del municipio (concejo, HCD,
deliberante) y en los dominios habituales (hcd<partido>.gob.ar, concejo<partido>.gob.ar…).
En cada uno se recorren la portada, las páginas que su menú enlaza como concejales, bloques,
integrantes o composición, y el banco de imágenes de WordPress, con la misma regla que los
secretarios municipales (18_fotos_secretarios_municipales.py): la imagen tiene que nombrar a
uno solo de los concejales, secretarios o intendente de ese municipio.

Los concejales electos en 2025 vienen como "Apellido Nombre" y los de 2023 como "Nombre
Apellido", así que acá alcanza con dos palabras del nombre si una es la primera o la última.

Revisar raw/hoja_concejales.png y anotar las descartadas en raw/fotos_rechazadas.json.
"""
import base64
import importlib.util
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse

from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]


def cargar(nombre, archivo):
    spec = importlib.util.spec_from_file_location(nombre, RAIZ / "scripts" / archivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


s18 = cargar("s18", "18_fotos_secretarios_municipales.py")
p17 = cargar("p17", "17_fotos_intendentes_prensa.py")
slug, get, texto = s18.slug, s18.get, s18.texto

ENLACE = re.compile(r"concejo|\bhcd|deliberante", re.I)
MENU = re.compile(r"concejal|bloque|integrante|autoridad|composici|cuerpo|banca|presidencia", re.I)
RUTAS = ["concejales", "integrantes", "bloques", "composicion", "el-concejo", "el-cuerpo", "autoridades",
         "institucional/concejales", "el-concejo/concejales", "concejo/concejales", "hcd/concejales"]


def palabras(nombre):
    return [w for w in slug(nombre).split("-") if len(w) > 2]


def nombra(t, persona):
    toks = palabras(persona)
    if len(toks) < 2:
        return False
    en_texto = set(t.split("-"))
    return sum(w in en_texto for w in toks) >= 2 and (toks[0] in en_texto or toks[-1] in en_texto)


def sitios_del_concejo(muni, web):
    """URLs candidatas del sitio del Concejo de un municipio."""
    partido = muni.split(":")[-1].replace("-", "")
    urls = []
    home = None
    for esq in ("https://", "http://"):
        home = get(esq + re.sub(r"^https?://", "", web).strip("/"))
        if home:
            break
    if home:
        for m in re.finditer(r'<a\b[^>]*href="([^"#]+)"[^>]*>(.*?)</a>', home.text, re.I | re.S):
            url = urljoin(home.url, m.group(1))
            if url.startswith("http") and len(texto(m.group(2))) <= 40 and ENLACE.search(m.group(1) + " " + texto(m.group(2))) \
                    and not re.search(r"facebook|instagram|twitter|youtube|\.pdf", url, re.I):
                urls.append(url)
    for host in (f"hcd{partido}.gob.ar", f"hcd{partido}.gov.ar", f"concejo{partido}.gob.ar",
                 f"hcd{partido}.org", f"hcd{partido}.com.ar", f"concejodeliberante{partido}.gob.ar"):
        r = get("https://" + host) or get("http://" + host)
        if r:
            urls.append(r.url)
    vistos, salida = set(), []
    for u in urls:
        clave = urlparse(u).netloc + urlparse(u).path.rstrip("/")
        if clave not in vistos:
            vistos.add(clave)
            salida.append(u)
    return salida[:4]


def trabajo(muni, web, personas, objetivo):
    hallado = {}
    for sitio in sitios_del_concejo(muni, web):
        for pid, v in s18.buscar(muni, sitio, personas, menu=MENU, rutas=RUTAS, nombra=nombra,
                                 apellido=lambda n: [palabras(n)[0], palabras(n)[-1]] if n in objetivo else []).items():
            hallado.setdefault(pid, v)
    return hallado


if __name__ == "__main__":
    grafo = json.loads((RAIZ / "data/grafo.json").read_text())
    fotos_f = RAIZ / "data/fotos.json"
    fotos = json.loads(fotos_f.read_text())
    U = {u["id"]: u for u in grafo["unidades"]}
    P = {p["id"]: p["nombre"] for p in grafo["personas"]}
    rechazadas_f = RAIZ / "raw/fotos_rechazadas.json"
    rechazadas = json.loads(rechazadas_f.read_text()) if rechazadas_f.exists() else {}
    webs = {r["id_municipio"]: r["web"] for r in json.loads((RAIZ / "raw/candidatas_intendentes.json").read_text()) if r["web"]}

    todos, concejales = {}, {}   # municipio → {persona_id: nombre}
    for c in grafo["cargos"]:
        if ":muni:" not in c["unidad"]:
            continue
        muni = ":".join(c["unidad"].split(":")[:3])
        todos.setdefault(muni, {})[c["persona"]] = P[c["persona"]]
        if U[c["unidad"]]["tipo"] == "bloque":
            concejales.setdefault(muni, {})[c["persona"]] = P[c["persona"]]

    trabajos = [(m, webs[m], todos[m], {P[p] for p in cs if p not in fotos})
                for m, cs in concejales.items() if m in webs and any(p not in fotos for p in cs)]
    print(f"{len(trabajos)} municipios con concejales sin foto")
    n, nuevas = 0, []
    usadas = {f["src"] for f in fotos.values()}
    with ThreadPoolExecutor(8) as ex:
        for (muni, *_), res in zip(trabajos, ex.map(lambda t: trabajo(*t), trabajos)):
            for pid, (img, pagina) in res.items():
                if pid in fotos or pid not in concejales[muni] or rechazadas.get(pid) == pagina:
                    continue
                src = p17.miniatura(img)
                if src and (src in usadas or s18.es_icono(src)):
                    src = None   # silueta genérica repetida, o ícono de colores planos
                if src:
                    nuevas.append(src)
                    usadas.add(src)
                    fotos[pid] = {"src": src, "fuente": f"Concejo Deliberante ({urlparse(pagina).netloc})", "url": pagina}
                    n += 1
                    print(f"  {muni.split(':')[-1]}: {P[pid]}  ← {pagina}", flush=True)
    fotos_f.write_text(json.dumps(fotos, ensure_ascii=False), encoding="utf-8")
    print(f"{n} fotos de concejales")
    if nuevas:
        hoja = Image.new("RGB", (12 * 112, (len(nuevas) + 11) // 12 * 112), "white")
        for i, src in enumerate(nuevas):
            hoja.paste(Image.open(io.BytesIO(base64.b64decode(src.split(",", 1)[1]))), (i % 12 * 112, i // 12 * 112))
        hoja.save(RAIZ / "raw/hoja_concejales.png")
        print("Revisar raw/hoja_concejales.png (en el orden de la lista de arriba)")
