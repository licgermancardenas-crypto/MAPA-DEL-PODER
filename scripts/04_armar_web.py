"""Inserta data/grafo.json dentro de web/app.html → web/index.html (un solo archivo, abre sin servidor)."""
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
datos = (RAIZ / "data/grafo.json").read_text(encoding="utf-8").replace("</", "<\\/")
fotos_f = RAIZ / "data/fotos.json"
fotos = {k: v for k, v in (json.loads(fotos_f.read_text()) if fotos_f.exists() else {}).items()}
html = (RAIZ / "web/app.html").read_text(encoding="utf-8").replace("/*__GRAFO__*/null", datos) \
    .replace("/*__FOTOS__*/{}", json.dumps(fotos, ensure_ascii=False).replace("</", "<\\/"))
camb_f = RAIZ / "data/historial/cambios.json"
html = html.replace("/*__CAMBIOS__*/{corridas:[]}",
                    (camb_f.read_text(encoding="utf-8") if camb_f.exists() else '{"corridas":[]}').replace("</", "<\\/"))
(RAIZ / "web/index.html").write_text(html, encoding="utf-8")
print(f"web/index.html · {len(html)/1e6:.1f} MB · {len(fotos)} fotos")
