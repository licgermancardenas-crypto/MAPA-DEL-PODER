"""Fotos de la cúpula judicial (cortes, consejos de la magistratura, ministerios públicos) → data/fotos.json.

1. Sitio oficial de cada órgano: portada y páginas de integrantes, con la regla de los
   secretarios municipales (18_fotos_secretarios_municipales.py). Como cada órgano tiene
   pocos integrantes, alcanza con que la imagen nombre el apellido de uno solo de ellos
   (el TSJ nombra los archivos "Weinberg 1.png", "Lozano 1.png"…).
2. Wikimedia Commons, para los que siguen sin foto: archivos con nombre y apellido en el
   título cuya descripción o categorías los ubican en la justicia o la política argentina.

Los juzgados, tribunales y cámaras no publican fotos de sus jueces: quedan sin foto.
Revisar raw/hoja_justicia.png y anotar las descartadas en raw/fotos_rechazadas.json.
"""
import base64
import importlib.util
import io
import json
import re
import time
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]


def cargar(nombre, archivo):
    spec = importlib.util.spec_from_file_location(nombre, RAIZ / "scripts" / archivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


s18 = cargar("s18", "18_fotos_secretarios_municipales.py")
c16 = cargar("c16", "16_fotos_intendentes_commons.py")
p17 = cargar("p17", "17_fotos_intendentes_prensa.py")
slug = s18.slug

SITIOS = {   # unidad → página de integrantes
    "caba:j:tsj": "https://www.tsjbaires.gov.ar/",
    "caba:j:consejo": "https://consejo.jusbaires.gob.ar/institucional/consejeros/",
    "caba:j:mpt": "https://mptutelar.gob.ar/autoridades",
    "pba:j:mp": "https://www.mpba.gov.ar/",
    "pba:j:scba": "https://www.scba.gov.ar/paginas.asp?id=38741",
}
TIPOS = {"corte", "consejo_magistratura", "ministerio_publico"}
MENU = re.compile(r"juec|jueces|integrant|consejer|autoridad|composici|ministr|procurad", re.I)
CONTEXTO = re.compile(r"juez|jueza|judges?|justices?|corte|tribunal|magistrad|procurad|consejo|fiscal|"
                      r"politic\w* (argentin|of argentina)|lawyers? (from|of) argentina|abogad", re.I)


def palabras(nombre):
    return [w for w in slug(nombre).split("-") if len(w) > 2]


def nombra(t, persona):
    toks = palabras(persona)
    return bool(toks) and len(toks[-1]) > 3 and toks[-1] in t.split("-")


def commons(nombre):
    """→ (img, página) del único archivo de Commons que sirve, o None."""
    toks = re.sub(r"\b\w\.?\s", " ", nombre + " ").split()
    nom, ap = c16.norm(toks[0]), c16.norm(toks[-1])
    res = c16.api(action="query", list="search", srnamespace=6, srsearch=f'intitle:"{ap}" {nom}', srlimit=20)
    titulos = [s["title"] for s in res.get("query", {}).get("search", [])
               if nom in c16.norm(s["title"]) and ap in c16.norm(s["title"]) and re.search(r"\.(jpe?g|png|webp)$", s["title"], re.I)]
    if not titulos:
        return None
    info = c16.api(action="query", titles="|".join(titulos), prop="imageinfo", iiprop="url|extmetadata", iiurlwidth=400)
    for p in info.get("query", {}).get("pages", {}).values():
        ii = p["imageinfo"][0]
        ctx = " ".join(re.sub(r"<[^>]+>", " ", ii["extmetadata"].get(k, {}).get("value", "")) for k in ("ImageDescription", "Categories"))
        if CONTEXTO.search(ctx) and "argentin" in ctx.lower() + ii["descriptionurl"].lower() or "buenos aires" in ctx.lower():
            return ii["thumburl"], ii["descriptionurl"]
    return None


if __name__ == "__main__":
    grafo = json.loads((RAIZ / "data/grafo.json").read_text())
    fotos_f = RAIZ / "data/fotos.json"
    fotos = json.loads(fotos_f.read_text())
    U = {u["id"]: u for u in grafo["unidades"]}
    P = {p["id"]: p["nombre"] for p in grafo["personas"]}
    rechazadas_f = RAIZ / "raw/fotos_rechazadas.json"
    rechazadas = json.loads(rechazadas_f.read_text()) if rechazadas_f.exists() else {}

    por_organo = {}
    for c in grafo["cargos"]:
        if U[c["unidad"]]["tipo"] in TIPOS:
            por_organo.setdefault(c["unidad"], {})[c["persona"]] = P[c["persona"]]
    usadas = {f["src"] for f in fotos.values()}
    nuevas = []

    def guardar(pid, img, pagina, fuente):
        if pid in fotos or rechazadas.get(pid) == pagina:
            return
        src = c16.miniatura(img) if "wikimedia" in img else p17.miniatura(img)
        if src and src not in usadas and not s18.es_icono(src):
            usadas.add(src)
            nuevas.append(src)
            fotos[pid] = {"src": src, "fuente": fuente, "url": pagina}
            print(f"  {P[pid]}  ← {pagina}", flush=True)

    print("── Sitios oficiales")
    for unidad, personas in por_organo.items():
        if unidad in SITIOS and any(p not in fotos for p in personas):
            res = s18.buscar(unidad, SITIOS[unidad], personas, menu=MENU, rutas=[], nombra=nombra,
                             apellido=lambda n: palabras(n)[-1:])
            for pid, (img, pagina) in res.items():
                guardar(pid, img, pagina, f"Sitio oficial ({s18.urlparse(pagina).netloc})")
    print("── Wikimedia Commons")
    for personas in por_organo.values():
        for pid, nombre in personas.items():
            if pid not in fotos:
                hallada = commons(nombre)
                if hallada:
                    guardar(pid, *hallada, "Wikimedia Commons")
                time.sleep(1)
    fotos_f.write_text(json.dumps(fotos, ensure_ascii=False), encoding="utf-8")
    sin = sorted({P[p] for ps in por_organo.values() for p in ps if p not in fotos})
    print(f"{len(nuevas)} fotos nuevas · sin foto: {', '.join(sin)}")
    if nuevas:
        hoja = Image.new("RGB", (12 * 112, (len(nuevas) + 11) // 12 * 112), "white")
        for i, src in enumerate(nuevas):
            hoja.paste(Image.open(io.BytesIO(base64.b64decode(src.split(",", 1)[1]))), (i % 12 * 112, i // 12 * 112))
        hoja.save(RAIZ / "raw/hoja_justicia.png")
        print("Revisar raw/hoja_justicia.png (en el orden de la lista de arriba)")
