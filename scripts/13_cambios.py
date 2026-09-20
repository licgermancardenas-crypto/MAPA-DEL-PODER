"""Compara el grafo recién generado con la foto guardada de la corrida anterior
y deja el registro de novedades en data/historial/cambios.json.

Detecta: designaciones nuevas, bajas, cambios de titular, organismos creados o
dados de baja, y vacantes que se abren o se cubren.

No usa red ni servicios: es un diff local entre dos JSON.
"""
import json
import shutil
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HIST = RAIZ / "data" / "historial"
HIST.mkdir(parents=True, exist_ok=True)
ULTIMO = HIST / "ultimo.json"
CAMBIOS = HIST / "cambios.json"

actual = json.loads((RAIZ / "data/grafo.json").read_text())


def indexar(g):
    u = {x["id"]: x for x in g["unidades"]}
    p = {x["id"]: x["nombre"] for x in g["personas"]}
    c = {}
    for x in g["cargos"]:
        c.setdefault(x["unidad"], []).append(x)
    return u, p, c


if not ULTIMO.exists():
    shutil.copy(RAIZ / "data/grafo.json", ULTIMO)
    CAMBIOS.write_text(json.dumps({"corridas": []}, ensure_ascii=False), encoding="utf-8")
    print("Primera corrida: se guardó la foto de referencia, sin cambios que mostrar.")
    raise SystemExit

previo = json.loads(ULTIMO.read_text())
uA, pA, cA = indexar(actual)
uP, pP, cP = indexar(previo)

eventos = []


def ev(tipo, unidad, texto, **extra):
    eventos.append({"tipo": tipo, "unidad": unidad, "unidad_nombre": uA.get(unidad, uP.get(unidad, {})).get("nombre"),
                    "jur": uA.get(unidad, uP.get(unidad, {})).get("jur"), "texto": texto, **extra})


for uid, u in uA.items():
    if uid not in uP and u["tipo"] not in ("bloque", "periodo"):
        ev("alta_organismo", uid, f"Nuevo organismo: {u['nombre']}")
for uid, u in uP.items():
    if uid not in uA and u["tipo"] not in ("bloque", "periodo"):
        ev("baja_organismo", uid, f"Ya no figura: {u['nombre']}")

for uid in set(cA) | set(cP):
    ahora = {c["persona"]: c for c in cA.get(uid, [])}
    antes = {c["persona"]: c for c in cP.get(uid, [])}
    if uid not in uA:
        continue
    for pid, c in ahora.items():
        if pid not in antes:
            ev("designacion", uid, f"{pA[pid]} asume como {c['rol']} en {uA[uid]['nombre']}",
               persona=pA[pid], rol=c["rol"], norma=c.get("norma"), norma_url=c.get("norma_url"), desde=c.get("desde"))
    for pid, c in antes.items():
        if pid not in ahora:
            ev("baja", uid, f"{pP[pid]} deja {c['rol']} en {uA[uid]['nombre']}", persona=pP[pid], rol=c["rol"])

for uid, u in uA.items():
    if uid in uP and u.get("vacante") != uP[uid].get("vacante"):
        ev("vacante_abre" if u["vacante"] else "vacante_cubre", uid,
           ("Queda vacante: " if u["vacante"] else "Se cubre la vacante: ") + u["nombre"])

reg = json.loads(CAMBIOS.read_text()) if CAMBIOS.exists() else {"corridas": []}
if eventos:
    reg["corridas"].insert(0, {"fecha": date.today().isoformat(), "eventos": eventos})
    reg["corridas"] = reg["corridas"][:20]      # se guardan las últimas 20 actualizaciones
CAMBIOS.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
shutil.copy(RAIZ / "data/grafo.json", ULTIMO)

resumen = {}
for e in eventos:
    resumen[e["tipo"]] = resumen.get(e["tipo"], 0) + 1
print(f"{len(eventos)} cambios desde la última actualización: {resumen or 'ninguno'}")
for e in eventos[:15]:
    print(f"  · {e['texto']}")
