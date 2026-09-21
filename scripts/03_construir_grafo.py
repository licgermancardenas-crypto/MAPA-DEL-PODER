"""Une todas las fuentes en un solo grafo: data/grafo.json.

Modelo (el mismo de CivLab):
  - unidad:   un órgano del Estado (ministerio, dirección, concejo, cámara, bloque).
              Tiene `padre` (de quién depende) y `titulares`.
  - persona:  quien ocupa un cargo. Una persona puede ocupar varios; se unen por
              nombre normalizado (sin tildes, sin orden de nombre/apellido).
  - cargo:    arista persona → unidad, con rol, fuente, norma de designación y fecha.

Fuentes:
  PBA ejecutivo   raw/pba_mde/*.csv            (Mapa del Estado, oficial)
  CABA ejecutivo  raw/caba_organigrama/*.json  (buenosaires.gob.ar/organigrama, oficial)
  Legislaturas, intendentes, secretarios, concejales:  ../intendentes/data/*.json

Qué no puede afirmar: dos homónimos se funden en una sola persona; un mismo
nombre escrito distinto en dos fuentes queda como dos personas.
"""
import csv
import glob
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PREV = RAIZ.parent / "intendentes" / "data"
OUT = RAIZ / "data" / "grafo.json"

unidades = {}          # id → unidad
personas = {}          # clave → persona
cargos = []            # aristas
cargos_por_unidad = {}


def slug(x):
    x = unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", x).strip("-")


def clave_persona(nombre):
    """'VARELA, Leandro Gastón' y 'Leandro Gastón Varela' → misma clave."""
    t = slug(nombre).split("-")
    return "-".join(sorted(w for w in t if len(w) > 1))


def nombre_legible(nombre):
    """'KICILLOF, Axel' / 'Axel KICILLOF' → 'Axel Kicillof'."""
    nombre = re.sub(r"\s+", " ", nombre).strip(" ,")
    if "," in nombre:
        ap, _, nom = nombre.partition(",")
        nombre = f"{nom.strip()} {ap.strip()}"
    return " ".join(w.capitalize() if w.isupper() and len(w) > 1 else w for w in nombre.split())


def unidad(uid, nombre, tipo, padre=None, jur=None, **extra):
    if uid not in unidades:
        unidades[uid] = {"id": uid, "nombre": nombre.strip(), "tipo": tipo, "padre": padre,
                         "jur": jur or (unidades[padre]["jur"] if padre else None), **extra}
    return uid


def cargo(nombre, uid, rol, fuente, **extra):
    nombre = nombre_legible(nombre)
    if not nombre or re.fullmatch(r"[_\s,.-]*", nombre):
        return
    k = clave_persona(nombre)
    # La misma persona dos veces en la misma unidad (p. ej. el CSV de Gobernación
    # y la carga explícita del gobernador) es un solo cargo: se queda el primero.
    previo = next((c for c in cargos_por_unidad.get(uid, []) if c["persona"] == "p:" + k), None)
    if previo:
        if previo["rol"] == "Titular":      # gana el rol más específico ("Gobernador")
            previo["rol"] = rol
        return
    if k not in personas:
        personas[k] = {"id": "p:" + k, "nombre": nombre}
    cargos.append({"persona": "p:" + k, "unidad": uid, "rol": rol, "fuente": fuente,
                   **{a: b for a, b in extra.items() if b}})
    cargos_por_unidad.setdefault(uid, []).append(cargos[-1])


def tipo_por_nombre(n):
    n = n.lower()
    for pat, t in [("^ministerio", "ministerio"), ("^subsecretar", "subsecretaria"),
                   ("^secretar", "secretaria"), ("^direcci[oó]n provincial", "direccion_provincial"),
                   ("^direcci[oó]n general", "direccion_general"), ("^direcci", "direccion"),
                   ("^gerencia|^subgerencia", "gerencia"), ("^unidad|^coordinaci", "unidad")]:
        if re.search(pat, n):
            return t
    return "organismo"


# ── Raíces ──────────────────────────────────────────────────────────────────
unidad("pba", "Provincia de Buenos Aires", "jurisdiccion", jur="pba")
unidad("caba", "Ciudad Autónoma de Buenos Aires", "jurisdiccion", jur="caba")
for j in ("pba", "caba"):
    unidad(f"{j}:ejecutivo", "Poder Ejecutivo", "poder", f"{j}")
    unidad(f"{j}:legislativo", "Poder Legislativo", "poder", f"{j}")
unidad("pba:municipios", "Municipios (135)", "poder", "pba")
unidad("pba:organismos-constitucionales", "Organismos de la Constitución", "poder", "pba")

# ── PBA ejecutivo: Mapa del Estado ─────────────────────────────────────────
mde_meta = json.loads((RAIZ / "raw/pba_mde/_descarga.json").read_text())
gob = unidad("pba:gobernacion", "Gobernación de la Provincia de Buenos Aires", "gobernacion", "pba:ejecutivo")
CONSTITUCIONALES = {"contaduría general de la provincia", "dirección general de cultura y educación",
                    "fiscalía de estado", "honorable tribunal de cuentas", "junta electoral",
                    "tesorería general de la provincia"}

filas = []
for f in sorted(glob.glob(str(RAIZ / "raw/pba_mde/*.csv"))):
    with open(f, encoding="utf-8") as fh:
        for i, r in enumerate(csv.DictReader(fh)):
            r = {k: (v or "").strip() for k, v in r.items()}
            r["_org"], r["_i"] = Path(f).stem, i
            filas.append(r)

# Las unidades se repiten entre archivos (el Patronato figura en su propio CSV
# y en el de Justicia): se deduplican por (nombre, a quién responde).
vistos, unicas = set(), []
for r in filas:
    k = (r["unidad"].lower(), r["responde_a"].lower())
    if k not in vistos:
        vistos.add(k)
        unicas.append(r)

# id estable por fila; el padre se busca primero en el mismo CSV (la fila con ese
# nombre más cercana hacia arriba, porque hay direcciones homónimas en ramas
# distintas) y si no, en cualquier CSV.
por_org = defaultdict(list)
for r in unicas:
    r["_id"] = f"pba:u:{r['_org']}:{r['_i']}"
    por_org[r["_org"]].append(r)
global_por_nombre = {}
for r in unicas:
    global_por_nombre.setdefault(r["unidad"].lower(), r["_id"])


def padre_pba(r):
    pn = r["responde_a"].lower()
    if r["unidad"].lower() in CONSTITUCIONALES:
        return "pba:organismos-constitucionales"
    if not pn:
        return gob
    if pn == "gobernación de la provincia de buenos aires":
        return gob
    previas = [x for x in por_org[r["_org"]] if x["_i"] < r["_i"] and x["unidad"].lower() == pn]
    if previas:
        return previas[-1]["_id"]
    mismas = [x for x in por_org[r["_org"]] if x["unidad"].lower() == pn]
    if mismas:
        return mismas[0]["_id"]
    return global_por_nombre.get(pn, gob)


for r in unicas:
    if r["unidad"].lower() == "gobernación de la provincia de buenos aires":
        r["_id"] = gob
for r in unicas:
    if r["_id"] == gob:
        continue
    unidad(r["_id"], r["unidad"], tipo_por_nombre(r["unidad"]), None, jur="pba",
           norma_creacion=r["unidad_fundamento"] or None, web=r["unidad_enlace"] or None)
for r in unicas:
    if r["_id"] != gob:
        unidades[r["_id"]]["padre"] = padre_pba(r)
    fecha = None
    if r["autoridad_fecha_inicio"]:
        try:
            fecha = datetime.strptime(r["autoridad_fecha_inicio"], "%d/%m/%Y").date().isoformat()
        except ValueError:
            pass
    cargo(f"{r['autoridad_apellido']}, {r['autoridad_nombre']}", r["_id"], "Titular",
          "Mapa del Estado PBA", norma=r["autoridad_fundamento"], norma_url=r["autoridad_fundamento_enlace"],
          desde=fecha, genero=r["autoridad_genero"])

# Gobernador y vice (el CSV de Gobernación solo trae la unidad).
cargo("Axel KICILLOF", gob, "Gobernador", "Mapa del Estado PBA")
cargo("Verónica María MAGARIO", gob, "Vicegobernadora", "Mapa del Estado PBA")

# ── PBA legislativo: sitios oficiales de cada cámara ───────────────────────
lp = json.loads((RAIZ / "raw/legislatura_pba.json").read_text())
# Diputados viene como "APELLIDO NOMBRES" sin coma; si el dataset previo tiene a
# la misma persona ("Nombres Apellido") se usa ese orden para mostrarla.
previos = json.loads((PREV / "legisladores.json").read_text())
orden_previo = {clave_persona(x["nombre"]): x["nombre"] for k in ("diputados_prov", "senadores_prov") for x in previos[k]}
for cam, nom, fuente, lista in [("diputados_prov", "Cámara de Diputados", "Cámara de Diputados PBA", lp["diputados"]),
                                ("senadores_prov", "Senado", "Senado PBA", lp["senadores"])]:
    cid = unidad(f"pba:{cam}", nom, "camara", "pba:legislativo", bancas=92 if "dip" in cam else 46,
                 cobertura=len(lista))
    for x in lista:
        bid = unidad(f"{cid}:bloque:{slug(x['bloque'])}", f"Bloque {x['bloque']}", "bloque", cid)
        nombre = orden_previo.get(clave_persona(x["apellido_nombre"]), x["apellido_nombre"])
        cargo(nombre, bid, "Diputado/a" if "dip" in cam else "Senador/a", fuente,
              seccion=x.get("seccion"), mandato=x.get("mandato"), distrito=x.get("distrito"))

# ── PBA municipios ─────────────────────────────────────────────────────────
intend = json.loads((PREV / "intendentes.json").read_text())
secre = json.loads((PREV / "secretarios.json").read_text())
conce = json.loads((PREV / "concejales_flat.json").read_text())
for m in intend:
    mid = unidad(f"pba:muni:{slug(m['municipio'])}", m["municipio"], "municipio", "pba:municipios",
                 seccion=m.get("seccion"), padron=m.get("padron"))
    dem = unidad(f"{mid}:ejecutivo", f"Departamento Ejecutivo · {m['municipio']}", "ejecutivo_municipal", mid)
    unidad(f"{mid}:hcd", f"Concejo Deliberante · {m['municipio']}", "concejo", mid)
    cargo(m["intendente"], dem, "Intendente/a", "Datos previos (intendentes.json)",
          partido=m.get("partido"))
for muni, lista in secre.items():
    mid = f"pba:muni:{slug(muni)}"
    if mid not in unidades:
        continue
    for x in lista:
        sid = unidad(f"{mid}:sec:{slug(x['cargo'])}", x["cargo"], "secretaria_municipal", f"{mid}:ejecutivo")
        cargo(x["nombre"], sid, x["cargo"], "Datos previos (secretarios.json)")
# Cada Concejo se renueva por mitades: electos 2023 (mandato 2023-2027) y 2025 (2025-2029).
# Se agrupan por la lista por la que entraron; el bloque que integran hoy puede ser otro.
for x in conce:
    hcd = f"pba:muni:{slug(x['municipio'])}:hcd"
    if hcd not in unidades:
        continue
    per = unidad(f"{hcd}:2023", "Electos 2023 · mandato 2023–2027", "periodo", hcd)
    bid = unidad(f"{per}:{slug(x['bloque'])}", x["bloque"], "bloque", per)
    cargo(x["nombre"], bid, "Concejal/a", "Escrutinio JEPBA 2023", partido=x.get("partido"), mandato="2023-2027")

c25 = json.loads((RAIZ / "raw/concejales_2025.json").read_text())
ALIAS = {"del-pilar": "pilar"}
for d in c25["distritos"]:
    k = re.sub(r"^partido-de-", "", slug(d["distrito"]))
    hcd = f"pba:muni:{ALIAS.get(k, k)}:hcd"
    if hcd not in unidades:
        print(f"  concejales 2025: sin municipio para {d['distrito']}")
        continue
    unidades[hcd]["bancas"] = unidades[hcd].get("bancas", 0) + (d["bancas"] or 0) * 2
    per = unidad(f"{hcd}:2025", "Electos 2025 · mandato 2025–2029", "periodo", hcd)
    for e in d["electos"]:
        bid = unidad(f"{per}:{slug(e['lista'])}", e["lista"].title().replace("Alianza ", ""), "bloque", per)
        cargo(e["nombre"], bid, "Concejal/a", "Escrutinio Definitivo JEPBA 2025", mandato="2025-2029",
              orden=e["orden"], norma_url=d["fuente"], norma="Escrutinio definitivo 2025")

# ── CABA ejecutivo: organigrama oficial ────────────────────────────────────
caba_meta = json.loads((RAIZ / "raw/caba_organigrama/organigrama.json").read_text())
jg = unidad("caba:jefatura", "Jefatura de Gobierno", "gobernacion", "caba:ejecutivo")
cargo("Jorge Macri", jg, "Jefe de Gobierno", "Organigrama GCBA")
for slug_area, nodos in caba_meta["areas"].items():
    for n in nodos:
        uid = "caba:u:" + n["id"]
        padre = "caba:u:" + n["responde_a"] if n["responde_a"] else jg
        # Procuración y Sindicatura son órganos de control, no dependen de Jefatura de Gabinete.
        nombre = re.sub(r"\s*\(([A-Z0-9 ]+)\)$", "", n["nombre"])
        sigla = (re.search(r"\(([A-Z0-9 ]+)\)$", n["nombre"]) or [None, None])[1]
        unidad(uid, nombre, tipo_por_nombre(nombre), padre, jur="caba", sigla=sigla, web=n.get("url"))
        for t in n["titulares"]:
            cargo(t["nombre"], uid, t["cargo"] if t["cargo"] not in ("Autoridad", "Autoridad superior") else "Titular",
                  "Organigrama GCBA")

# ── CABA legislativo ───────────────────────────────────────────────────────
lc = json.loads((PREV / "legisladores_caba.json").read_text())
leg_caba = unidad("caba:legislatura", "Legislatura de la Ciudad", "camara", "caba:legislativo", bancas=60,
                  cobertura=len(lc["diputados"]))
for x in lc["diputados"]:
    bid = unidad(f"{leg_caba}:bloque:{slug(x['bloque'])}", f"Bloque {x['bloque']}", "bloque", leg_caba)
    cargo(x["nombre"], bid, "Legislador/a" + (" · presidente/a de bloque" if x.get("presidente_bloque") else ""),
          "Datos previos (legisladores_caba.json)", mandato=x.get("mandato"))
cargo(lc["autoridades"]["presidenta"], leg_caba, "Presidenta (Vicejefa de Gobierno)", "Datos previos")

# ── Poder Judicial ─────────────────────────────────────────────────────────
# Se cargan magistrados y funcionarios con firma (secretarios, jefes). Auxiliares,
# relatores, adscriptos e inspectores se cuentan en `equipo` pero no son nodos.
ROL_CON_PESO = re.compile(r"juez|jueza|president|vocal|ministr|camarist|^secretari|subsecretari|consejer|"
                          r"jef[ea]|delegad|director|titular|intendente|magistrad|fiscal|defensor|asesor", re.I)
FUERA = re.compile(r"auxiliar|adscript|inspector|relator", re.I)


def cargar_integrantes(uid, integrantes, fuente, jurisdiccional):
    """Titular = fila marcada como tal; si no hay, el primer cargo con peso."""
    con_peso = [p for p in integrantes if p["nombre"] and ROL_CON_PESO.search(p["cargo"]) and not FUERA.search(p["cargo"])]
    if not any(p["titular"] for p in integrantes) and con_peso and not jurisdiccional:
        con_peso[0]["titular"] = True
    unidades[uid]["equipo"] = len(integrantes)
    for p in con_peso:
        cargo(p["nombre"], uid, p["cargo"], fuente, nota=p.get("nota"))
    # Un tribunal sin juez/a no se tapa con su secretario: la vacante es la del magistrado.
    magistrados = [p for p in integrantes if p["nombre"] and re.search(r"juez|jueza|president|vocal|ministr|magistrad|juez/a", p["cargo"], re.I)]
    if jurisdiccional and not magistrados:
        unidades[uid]["vacante_forzada"] = True
        nota = next((p["nota"] for p in integrantes if not p["nombre"] and p.get("nota")), None)
        if nota:
            unidades[uid]["nota"] = nota


# PBA ──
pj = json.loads((RAIZ / "raw/pba_judicial/guia_judicial.json").read_text())
unidad("pba:judicial", "Poder Judicial", "poder", "pba")
scba = unidad("pba:j:scba", "Suprema Corte de Justicia", "corte", "pba:judicial", bancas=7)
casa = unidad("pba:j:casacion", "Tribunal de Casación Penal", "tribunal", "pba:judicial")
for o in pj["organismos"]:
    n = o["nombre"]
    if n == "Suprema Corte de Justicia":
        uid = scba
    elif n.startswith("Suprema Corte de Justicia "):
        uid = unidad(f"pba:j:o:{o['id'] or slug(n)}", n.replace("Suprema Corte de Justicia ", "").strip(" -"),
                     "oficina_judicial", scba)
    elif n == "Tribunal de Casación Penal":
        uid = casa
    elif n.startswith("Tribunal de Casación Penal"):
        uid = unidad(f"pba:j:o:{o['id'] or slug(n)}", n, "tribunal", casa)
    else:
        dep = unidad(f"pba:j:depto:{slug(o['depto'])}", f"Departamento Judicial {o['depto']}", "departamento_judicial",
                     "pba:judicial")
        fue = unidad(f"{dep}:fuero:{slug(o['fuero'] or 'administrativo')}",
                     f"Fuero {o['fuero']}" if o["fuero"] else "Dependencias administrativas", "fuero", dep)
        tipo = ("camara_judicial" if n.lower().startswith("cámara") else "tribunal" if n.lower().startswith("tribunal")
                else "juzgado" if n.lower().startswith("juzgado") else "oficina_judicial")
        uid = unidad(f"pba:j:o:{o['id'] or slug(o['depto'] + n)}", n, tipo, fue, mail=o.get("mail"))
    cargar_integrantes(uid, o["integrantes"], "Guía Judicial SCBA", jurisdiccional=bool(o["fuero"]))
ministros = [c for c in cargos if c["unidad"] == scba]
unidades[scba]["cobertura"] = len(ministros)
for i in range(7 - len(ministros)):
    unidad(f"{scba}:vacante:{i+1}", f"Cargo de juez/a de la Corte · vacante {i+1}", "asiento", scba,
           vacante_forzada=True,
           nota="La Constitución fija 7 miembros; la Corte funciona con 3 desde 2024 (jubilación de Genoud, "
                "renuncias de De Lázzari e Hitters, fallecimiento de Negri).")

mp = json.loads((RAIZ / "raw/ministerios_publicos.json").read_text())
for o in mp["organos"]:
    base = "pba:judicial" if o["jur"] == "pba" else "caba:judicial"
    if o["jur"] == "caba":
        unidad("caba:judicial", "Poder Judicial", "poder", "caba")
    uid = unidad(f"{o['jur']}:j:{o['id']}", o["nombre"], "ministerio_publico", base, web=o["url"],
                 sin_dato=o["titular"] is None)
    if o["titular"]:
        cargo(o["titular"]["nombre"], uid, o["titular"]["cargo"], "Sitio oficial del Ministerio Público", )
    for a in o.get("areas", []):
        aid = unidad(f"{uid}:{slug(a['nombre'])}", a["nombre"], "secretaria", uid)
        cargo(a["nombre_titular"], aid, a["cargo"], "Sitio oficial del Ministerio Público")

# CABA ──
cj = json.loads((RAIZ / "raw/caba_judicial/guia_judicial.json").read_text())
unidad("caba:judicial", "Poder Judicial", "poder", "caba")
consejo = unidad("caba:j:consejo", "Consejo de la Magistratura", "consejo_magistratura", "caba:judicial")
for o in cj["organismos"]:
    n, inst = o["nombre"], o["instancia"] or ""
    if n.startswith("Tribunal Superior de Justicia"):
        uid = unidad("caba:j:tsj", "Tribunal Superior de Justicia", "corte", "caba:judicial", bancas=5,
                     cobertura=len(o["integrantes"]))
        fuente = "Sitio oficial del TSJ"
    elif n.startswith("Consejo de la Magistratura"):
        continue
    elif inst.startswith("Consejo de la Magistratura") or o["fuero"] == "Poder Judicial":
        uid = unidad(f"caba:j:o:{slug(o['id'])}", n, "oficina_judicial", consejo)
        fuente = "Guía Judicial CABA"
    else:
        fue = unidad(f"caba:j:fuero:{slug(o['fuero'])}", f"Fuero {o['fuero']}", "fuero", "caba:judicial")
        ins = unidad(f"{fue}:{slug(inst)}", inst, "instancia", fue)
        tipo = "camara_judicial" if "cámara" in inst.lower() else "juzgado"
        uid = unidad(f"caba:j:o:{slug(o['id'])}", n if not n.startswith("Sala") else f"{inst} · {n}", tipo, ins)
        fuente = "Guía Judicial CABA"
    for p in o["integrantes"]:
        if p["cargo"] == "Magistrado/a":
            p["cargo"] = "Juez/a" + (f" · {p['nota']}" if p["nota"] and "Sala" in (p["nota"] or "") else "")
    cargar_integrantes(uid, o["integrantes"], fuente,
                       jurisdiccional=unidades[uid]["tipo"] in ("juzgado", "camara_judicial", "corte"))

# ── Consejos de la Magistratura ────────────────────────────────────────────
cm = json.loads((RAIZ / "raw/consejos_magistratura.json").read_text())
# PBA: el Consejo integra los cuatro estamentos que fija la Constitución provincial.
cm_pba = unidad("pba:j:consejo", "Consejo de la Magistratura", "consejo_magistratura", "pba:judicial",
                web=cm["pba"]["url"])
ESTAMENTOS = {"PODER JUDICIAL": "Representantes del Poder Judicial",
              "PODER LEGISLATIVO": "Representantes del Poder Legislativo",
              "PODER EJECUTIVO": "Representantes del Poder Ejecutivo",
              "COLEGIO DE ABOGADOS": "Representantes del Colegio de Abogados"}
for x in cm["pba"]["integrantes"]:
    est = ESTAMENTOS.get(x["estamento"] or "")
    padre = unidad(f"{cm_pba}:{slug(est)}", est, "estamento", cm_pba) if est else cm_pba
    rol = x["rol"] + (f" por el {x['region']}" if x["region"] else "")
    cargo(x["nombre"], padre, rol, "Consejo de la Magistratura PBA")
for x in cm["pba"]["estructura"]:
    uid = unidad(f"{cm_pba}:{slug(x['cargo'])}", x["cargo"], "unidad", cm_pba)
    cargo(x["nombre"], uid, x["cargo"], "Consejo de la Magistratura PBA")
for x in cm["caba"]["integrantes"]:
    cargo(x["nombre"], "caba:j:consejo", x["rol"], "Consejo de la Magistratura CABA", mail=x.get("mail"))

# ── Salida ─────────────────────────────────────────────────────────────────
con_titular = {c["unidad"] for c in cargos}
# Vacante: unidad de gestión sin titular. Los agrupadores (poderes, cámaras,
# bloques, concejos, fueros) no tienen titular propio y no cuentan; tampoco lo
# que marcamos "sin dato" (la fuente no lo publica, no significa que esté vacío).
AGRUPA = {"jurisdiccion", "poder", "camara", "bloque", "municipio", "concejo", "departamento_judicial",
          "fuero", "instancia", "periodo", "estamento", "consejo_magistratura"}
for u in unidades.values():
    u["vacante"] = bool(u.pop("vacante_forzada", False)) or (
        u["tipo"] not in AGRUPA and u["id"] not in con_titular and not u.get("sin_dato"))

grafo = {
    "generado": date.today().isoformat(),
    "fuentes": {
        "pba_ejecutivo": {"url": mde_meta["fuente"], "fecha": mde_meta["fecha"]},
        "caba_ejecutivo": {"url": caba_meta["fuente"], "fecha": caba_meta["fecha"]},
        "legislaturas_municipios": {"url": "intendentes/data", "fecha": "2026-07-04"},
        "pba_judicial": {"url": pj["fuente"], "fecha": pj["fecha"]},
        "caba_judicial": {"url": cj["fuente"], "fecha": cj["fecha"]},
        "concejales_2025": {"url": c25["fuente"], "fecha": c25["fecha"]},
        "consejos_magistratura": {"url": cm["pba"]["url"], "fecha": cm["fecha"]},
    },
    "unidades": list(unidades.values()),
    "personas": list(personas.values()),
    "cargos": cargos,
}
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(grafo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

multi = defaultdict(set)
for c in cargos:
    multi[c["persona"]].add(c["unidad"])
print(f"{len(unidades)} unidades · {len(personas)} personas · {len(cargos)} cargos · "
      f"{sum(u['vacante'] for u in unidades.values())} vacantes · "
      f"{sum(len(v) > 1 for v in multi.values())} personas con más de un cargo · "
      f"{OUT.stat().st_size/1e6:.1f} MB")
