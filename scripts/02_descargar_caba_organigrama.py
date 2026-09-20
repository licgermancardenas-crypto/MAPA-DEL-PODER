"""Descarga el organigrama del Gobierno de la Ciudad (buenosaires.gob.ar/organigrama)
y lo reconstruye como árbol: unidad → a quién responde → titulares.

Cómo se arma el árbol: la página de cada área es una lista plana de tres tipos
de evento: encabezados ("Subsecretarías que dependen de esta secretaría",
"Organismos dentro de USPRS"), tarjetas (la unidad) y textos de autoridad
("Autoridad: ...", o varios: "Presidente: ... / Director: ..."). El encabezado
declara de quién dependen las tarjetas que siguen; el rango de la unidad
(Secretaría > Subsecretaría > Dirección General > Gerencia Operativa >
Subgerencia) resuelve los hermanos que aparecen sin encabezado propio.

Qué no puede afirmar: la Ciudad no publica decreto ni fecha de designación en
el organigrama; eso queda vacío. "Sin designar" o sin texto se toma como vacante.
"""
import html as H
import json
import re
import time
from datetime import date
from pathlib import Path

import requests

BASE = "https://buenosaires.gob.ar"
OUT = Path(__file__).resolve().parents[1] / "raw" / "caba_organigrama"
OUT.mkdir(parents=True, exist_ok=True)

s = requests.Session()
s.headers["User-Agent"] = "grafo-gobierno-ba/0.1 (investigación)"

RANGOS = [
    (r"^ministerio|^jefatura de gabinete|^vicejefatura|^secretar[ií]a general$", 0),
    (r"^secretar[ií]a", 1),
    (r"^subsecretar[ií]a", 2),
    (r"^direcci[oó]n general", 3),
    (r"^gerencia operativa", 4),
    (r"^subgerencia", 5),
]


def rango(nombre):
    n = nombre.lower()
    for pat, r in RANGOS:
        if re.search(pat, n):
            return r
    return None


def texto(x):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", x))).strip()


def rango_efectivo(nodo, nodos):
    """Rango de un nodo; si no tiene (consejo, agencia), el de su superior con rango."""
    por_id = {n["id"]: n for n in nodos}
    while nodo["rango"] is None:
        nodo = por_id[nodo["responde_a"]]
    return nodo["rango"]


def padre_del_encabezado(crudo, h, nodos, ultimo_por_rango, raiz):
    """Lee a quién apunta un encabezado del organigrama."""
    # "Organismos dentro de USPRS", "Organismos dentro de la DGAI"
    for sigla in re.findall(r"\b([A-Z]{3,})\b", crudo):
        n = next((n for n in reversed(nodos) if n["nombre"].endswith(f"({sigla})")), None)
        if n:
            return n
    # "... dependientes de la Dirección General Derechos Humanos"
    for n in reversed(nodos[1:]):
        base = re.sub(r"\s*\([^)]*\)$", "", n["nombre"]).lower()
        if len(base) > 12 and base in h:
            return n
    if re.search(r"\b(del|de la) (ministerio|jefatura|vicejefatura|organismo|procuraci|sindicatura|consejo|unidad)"
                 r"|^organismos fuera de nivel$", h):
        return raiz
    for pat, r in [("gerencia", 4), ("direcci[oó]n", 3), ("subsecretar[ií]a", 2), ("secretar[ií]a", 1)]:
        if re.search(rf"(de est[ae]|de la|del) {pat}", h):
            return ultimo_por_rango.get(r)
    # "Organismos dentro de IDECABA" / "Organismos dependientes del EAIT": la
    # sigla puede venir mal escrita, pero siempre sigue a la tarjeta del organismo.
    if re.match(r"organismos (dentro|dependientes)", h) and len(nodos) > 1:
        return nodos[-1]
    return None


def parsear_area(slug):
    page = s.get(f"{BASE}/organigrama/{slug}", timeout=60).text
    area = texto(re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S).group(1))
    m = re.search(r"Autoridad superior:\s*([^<]+)</a>", page)
    raiz = {"id": slug, "nombre": area, "responde_a": None, "rango": 0,
            "url": f"{BASE}/organigrama/{slug}",
            "titulares": [{"cargo": "Autoridad superior", "nombre": m.group(1).strip()}] if m else []}
    nodos = [raiz]

    eventos = re.finditer(
        r'<h[24] class="mb-[34][^"]*"[^>]*>(?P<h>.*?)</h[24]>'
        r'|<h3 class="card-title">(?P<t>.*?)</h3>'
        r'|field--name-field-texto[^>]*>(?P<a>.*?)</div>',
        page, re.S)

    ultimo_por_rango = {0: raiz}
    contexto = raiz          # padre que declara el último encabezado
    for ev in eventos:
        if ev.group("h") is not None:
            crudo = texto(ev.group("h"))
            h = crudo.lower()
            if not h or "{" in h:   # vacío o CSS incrustado
                continue
            contexto = padre_del_encabezado(crudo, h, nodos, ultimo_por_rango, raiz) or contexto
            # Lo que cuelga de un nivel más profundo que el encabezado ya no aplica.
            tope = rango_efectivo(contexto, nodos)
            for k in [k for k in ultimo_por_rango if k > tope]:
                del ultimo_por_rango[k]
            continue

        if ev.group("a") is not None:
            if len(nodos) > 1:
                for linea in re.split(r"<br\s*/?>", ev.group("a")):
                    linea = texto(linea)
                    if not linea:
                        continue
                    cargo, _, quien = linea.partition(":")
                    if not quien:
                        cargo, quien = "Autoridad", cargo
                    quien = quien.strip()
                    if quien and quien.lower() != "sin designar":
                        nodos[-1]["titulares"].append({"cargo": cargo.strip(), "nombre": quien})
            continue

        nombre = texto(ev.group("t"))
        if not nombre:      # tarjeta extra de la misma unidad (otro titular)
            continue
        m_href = re.search(r'href="([^"]*)"', ev.group("t"))
        href = m_href.group(1) if m_href else ""
        r = rango(nombre)
        # El encabezado manda; si la tarjeta tiene igual o más rango que ese
        # padre, es un hermano que aparece sin encabezado propio.
        if r is not None and r <= rango_efectivo(contexto, nodos):
            padre = next((ultimo_por_rango[k] for k in range(r - 1, -1, -1) if k in ultimo_por_rango), raiz)
            contexto = padre
        else:
            padre = contexto
        nodo = {"id": f"{slug}/{len(nodos)}", "nombre": nombre, "responde_a": padre["id"],
                "rango": r, "url": BASE + href if href.startswith("/") else None, "titulares": []}
        nodos.append(nodo)
        if r is not None:
            ultimo_por_rango[r] = nodo
            for k in [k for k in ultimo_por_rango if k > r]:
                del ultimo_por_rango[k]
    return nodos


if __name__ == "__main__":
    indice = s.get(f"{BASE}/organigrama", timeout=60).text
    slugs = sorted(set(re.findall(r'href="/organigrama/([^"]+)"', indice)))
    print(f"{len(slugs)} áreas")

    todo = {}
    for slug in slugs:
        try:
            todo[slug] = parsear_area(slug)
            vac = sum(not n["titulares"] for n in todo[slug])
            print(f"  {slug}: {len(todo[slug])} unidades, {vac} vacantes")
        except Exception as e:  # una página rota no frena el resto
            print(f"  {slug}: FALLÓ {e!r}")
        time.sleep(0.5)

    (OUT / "organigrama.json").write_text(json.dumps(
        {"fecha": date.today().isoformat(), "fuente": f"{BASE}/organigrama", "areas": todo},
        ensure_ascii=False, indent=1), encoding="utf-8")
