#!/usr/bin/env bash
# EL BOTÓN: rebaja las fuentes oficiales, rearma el grafo, calcula qué cambió y abre la página.
# No usa Claude ni servicios pagos: solo descargas de sitios públicos.
set -uo pipefail
cd "$(dirname "$0")"
inicio=$(date +%s)

paso () {            # sigue aunque una fuente esté caída: avisa y usa lo último descargado
  echo "▸ $1"
  if ! python3 "scripts/$2"; then
    echo "  ⚠ falló $2 — se conservan los datos anteriores de esa fuente"
  fi
}

paso "Ejecutivo PBA (Mapa del Estado)"        01_descargar_pba_mde.py
paso "Ejecutivo CABA (organigrama)"           02_descargar_caba_organigrama.py
paso "Judicial PBA (Guía Judicial SCBA)"      05_descargar_pba_judicial.py
paso "Judicial CABA (Guía Judicial)"          06_descargar_caba_judicial.py
paso "Ministerios Públicos"                   07_descargar_ministerios_publicos.py
paso "Legislatura PBA"                        08_descargar_legislatura_pba.py
paso "Concejales 2025"                        10_descargar_concejales_2025.py
paso "Armando el grafo"                       03_construir_grafo.py
paso "Novedades desde la última vez"          13_cambios.py
[ "${1:-}" = "--con-fotos" ] && paso "Fotos"  09_fotos.py
paso "Armando la página"                      04_armar_web.py

echo "✔ Listo en $(( ($(date +%s) - inicio) / 60 )) min · web/index.html"
command -v xdg-open >/dev/null && xdg-open web/index.html >/dev/null 2>&1 &

# ── Publicar en GitHub: solo si vos decís que sí ─────────────────────────────
# Sin terminal interactiva (o con --sin-publicar) no pregunta ni publica nada.
if [ "${1:-}" != "--sin-publicar" ] && [ -t 0 ] && git rev-parse --git-dir >/dev/null 2>&1; then
  cambios=$(git status --porcelain | wc -l)
  if [ "$cambios" -gt 0 ]; then
    echo
    echo "Hay $cambios archivos con cambios para publicar:"
    git status --short | head -10
    [ "$cambios" -gt 10 ] && echo "  …y $((cambios - 10)) más"
    echo
    echo "Publicar los sube a GitHub y los deja visibles para cualquiera en"
    echo "  https://licgermancardenas-crypto.github.io/MAPA-DEL-PODER/"
    read -rp "¿Publicar? [s/N] " r
    if [ "$r" = "s" ] || [ "$r" = "S" ]; then
      git add -A
      git commit -q -m "Actualización de datos $(date +%d/%m/%Y)"
      if git push -q origin HEAD; then
        echo "✔ Publicado. GitHub Pages lo republica en un minuto."
      else
        echo "⚠ No se pudo publicar (¿sin internet o sin permisos?). El commit quedó hecho:"
        echo "  para reintentar, corré: git push origin HEAD"
      fi
    else
      echo "No se publicó. Los cambios quedan solo en tu máquina."
    fi
  fi
fi
