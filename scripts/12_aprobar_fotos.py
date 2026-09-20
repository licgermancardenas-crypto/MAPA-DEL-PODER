"""Aprobación manual de las fotos de intendentes propuestas por 11_fotos_intendentes.py.

  python3 scripts/12_aprobar_fotos.py planilla
      → web/revision_intendentes.html: una tarjeta por municipio con sus candidatas.
        Al tocar la foto correcta, la página arma un código "APROBADAS v1: slug=n, ...".

  python3 scripts/12_aprobar_fotos.py aplicar "APROBADAS v1: almirante-brown=1, azul=2"
      → suma esas fotos a data/fotos.json (fuente: sitio oficial del municipio) y
        guarda el código en raw/aprobadas_intendentes.txt para poder rehacerlo.
"""
import base64
import html as H
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CAND = json.loads((RAIZ / "raw/candidatas_intendentes.json").read_text())
GRAFO = json.loads((RAIZ / "data/grafo.json").read_text())
FOTOS_F = RAIZ / "data/fotos.json"
FOTOS = json.loads(FOTOS_F.read_text())
INTENDENTE = {c["unidad"].rsplit(":", 1)[0]: c["persona"] for c in GRAFO["cargos"] if c["rol"].startswith("Intendente")}


def clave_muni(r):
    return r["id_municipio"].split(":")[-1]


def planilla():
    filas = []
    for r in sorted(CAND, key=lambda r: r["municipio"]):
        pid = INTENDENTE.get(r["id_municipio"])
        if not r["candidatas"] or not pid or (pid in FOTOS and FOTOS[pid]["fuente"] != "Wikidata"):
            continue
        actual = FOTOS.get(pid)
        opciones = "".join(
            f'<button class="op" type="button" data-k="{clave_muni(r)}" data-n="{i+1}" aria-pressed="false">'
            f'<img src="{c["src"]}" alt="Candidata {i+1}"><span class="n mono">{i+1}</span></button>'
            for i, c in enumerate(r["candidatas"]))
        fuentes = " · ".join(f'<a href="{H.escape(c["pagina"])}" target="_blank" rel="noopener">{i+1}</a>'
                             for i, c in enumerate(r["candidatas"]))
        filas.append(f'''<article class="m">
  <header><h2>{H.escape(r["intendente_dataset"] or r["intendente_guia"])}</h2>
  <p>{H.escape(r["municipio"])}{" · ya tiene foto de Wikidata" if actual else ""}</p></header>
  <div class="ops">{opciones}</div>
  <p class="src">Página donde apareció: {fuentes}</p>
</article>''')
    tpl = (RAIZ / "web/revision.tpl.html").read_text(encoding="utf-8")
    out = RAIZ / "web/revision_intendentes.html"
    out.write_text(tpl.replace("<!--FILAS-->", "\n".join(filas)).replace("<!--N-->", str(len(filas))), encoding="utf-8")
    print(f"{out} · {len(filas)} municipios para revisar")


def aplicar(codigo):
    sel = dict(re.findall(r"([a-z0-9-]+)=(\d)", codigo))
    por_clave = {clave_muni(r): r for r in CAND if r["id_municipio"]}
    n = 0
    for k, i in sel.items():
        r = por_clave.get(k)
        pid = INTENDENTE.get(f"pba:muni:{k}")
        if not r or not pid or int(i) > len(r["candidatas"]):
            print(f"  ignorado: {k}={i}")
            continue
        c = r["candidatas"][int(i) - 1]
        FOTOS[pid] = {"src": c["src"], "fuente": f"Sitio oficial de {r['municipio']} (aprobada a mano)", "url": c["pagina"]}
        n += 1
    FOTOS_F.write_text(json.dumps(FOTOS, ensure_ascii=False), encoding="utf-8")
    with open(RAIZ / "raw/aprobadas_intendentes.txt", "a", encoding="utf-8") as f:
        f.write(codigo.strip() + "\n")
    print(f"{n} fotos de intendentes sumadas")


if __name__ == "__main__":
    if sys.argv[1:2] == ["planilla"]:
        planilla()
    elif sys.argv[1:2] == ["aplicar"]:
        aplicar(" ".join(sys.argv[2:]))
    else:
        print(__doc__)
