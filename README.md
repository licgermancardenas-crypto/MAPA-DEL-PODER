# Mapa del Estado BA

Un "US Gov Graph" (CivLab) para la Provincia y la Ciudad de Buenos Aires: organismos,
cargos, titulares y vacantes en un grafo navegable.
Proyecto independiente: no está afiliado al Gobierno de la Provincia ni al de la Ciudad
(ni al sitio oficial mapadelestado.gba.gob.ar, que es una de sus fuentes). Web: `web/index.html` (un solo
archivo, abre sin servidor).

**El botón:** el acceso directo *Actualizar Mapa del Estado BA* del escritorio (o `./actualizar.sh`)
rebaja todas las fuentes, rearma el grafo, calcula qué cambió desde la vez anterior y abre la página.
Tarda unos 10 minutos y no usa Claude ni ningún servicio pago. Si una fuente está caída, avisa y
conserva lo último descargado de esa fuente.

```bash
./actualizar.sh                # actualizar datos
./actualizar.sh --con-fotos    # además rebusca fotos (más lento)
```

Los cambios de cada corrida quedan en `data/historial/cambios.json` y se ven en la pestaña
**Novedades** de la página: designaciones, bajas, organismos nuevos y vacantes que se abren o se cubren.

## Fuentes

| Capa | Fuente | Trae |
|---|---|---|
| Ejecutivo PBA | [Mapa del Estado](https://mapadelestado.gba.gob.ar) — CSV por organismo | ~3.350 unidades, titular, **decreto de designación con link**, fecha de inicio, vacantes |
| Ejecutivo CABA | [Organigrama GCBA](https://buenosaires.gob.ar/organigrama) — HTML | ~510 unidades y titulares (sin norma ni fecha) |
| Legislaturas, intendentes, secretarios, concejales | `../intendentes/data/*.json` | datos ya compilados en la plataforma PBA |
| Judicial PBA | [Guía Judicial SCBA](https://www.scba.gov.ar/guia/) — 20 departamentos | ~1.330 organismos (Corte, Casación, cámaras, juzgados, Paz) con magistrados, secretarios y notas (interino, licencia) |
| Judicial CABA | [Guía Judicial CABA](https://guiajudicial.jusbaires.gob.ar) + [TSJ](https://www.tsjbaires.gov.ar) | 93 organismos de los 4 fueros, TSJ, vacantes con subrogancia |
| Legislatura PBA | hcdiputados-ba.gov.ar · senado-ba.gov.ar | 92 diputados y 46 senadores con bloque, sección, mandato y foto |
| Concejales 2025 | [Escrutinio definitivo JEPBA 2025](https://www.juntaelectoral.gba.gov.ar/escrutinio-definitivo-2025/) — PDF por distrito | 1.097 titulares en 135 distritos (verificado contra bancas oficiales) |
| Fotos | organigrama GCBA, Legislatura CABA, cámaras PBA, Wikidata (solo coincidencia única + perfil político/judicial) | `data/fotos.json`, cada una con su fuente |
| Ministerios Públicos | mpba.gov.ar, mpfciudad.gob.ar, mptutelar.gob.ar | cúpulas (Procurador, Fiscal General, Asesora Tutelar) |

## Modelo

`unidad` (con `padre`) · `persona` · `cargo` (persona → unidad, con rol, fuente, norma, fecha).
Las personas se unen **por nombre normalizado**: los homónimos se funden (ver pestaña
"Cruces", que lo advierte).

## Huecos conocidos

- Fotos: ~5% de las personas. No hay fuente oficial con foto para concejales, directores
  provinciales ni personal de juzgados; no se cruza por nombre con buscadores (homónimos).
- Judicial: faltan fiscalías y defensorías departamentales (no hay lista descargable), la
  composición del Consejo de la Magistratura (PBA y CABA), las secretarías centrales de la SCBA
  y el Defensor/a General porteño (mpdefensa.gob.ar responde 403: figura "sin dato").
- Sin juntas comunales porteñas ni diputados/senadores nacionales (los del dataset previo son
  anteriores a diciembre 2025).
- CABA: el árbol se reconstruye de encabezados HTML; si la Ciudad cambia la maqueta, revisar
  `scripts/02_descargar_caba_organigrama.py`.

## Fotos de intendentes (paso manual)

```bash
python3 scripts/11_fotos_intendentes.py          # busca candidatas en el sitio de cada municipio
python3 scripts/12_aprobar_fotos.py planilla     # → web/revision_intendentes.html
python3 scripts/12_aprobar_fotos.py aplicar "APROBADAS v1: arrecifes=1, ..."   # código que arma la planilla
python3 scripts/04_armar_web.py
```
Los códigos aplicados quedan en `raw/aprobadas_intendentes.txt`.
