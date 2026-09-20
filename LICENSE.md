# Licencias

**Código** (`scripts/`, `web/app.html`, `web/revision.tpl.html`, `actualizar.sh`): MIT.

**Datos** (`data/grafo.json`, `raw/`): provienen de fuentes públicas oficiales —Mapa del Estado
de la Provincia, organigrama del GCBA, guías judiciales de la SCBA y del Consejo de la
Magistratura porteño, sitios de las cámaras legislativas y escrutinios de la Junta Electoral
bonaerense—. Cada unidad y cada cargo guarda de qué fuente salió. El armado, la normalización y
el cruce entre fuentes son obra de este proyecto y se comparten bajo CC BY 4.0: citá
"Mapa del Estado BA" y el enlace al repositorio.

**Fotos** (`data/fotos.json`): NO son de este proyecto. Son miniaturas de 112 px tomadas de:
- los organigramas oficiales del GCBA y de las cámaras legislativas,
- los sitios oficiales de cada municipio,
- Wikimedia Commons vía Wikidata, donde cada archivo tiene su propia licencia y autor.

Se incluyen como cita, con el enlace a la página de origen en cada ficha. **No hay cesión de
derechos**: si vas a reutilizarlas, verificá la licencia de cada imagen en su fuente. Para
quitarlas del repositorio: `rm data/fotos.json && python3 scripts/04_armar_web.py`.

Este es un proyecto independiente, sin relación con el Gobierno de la Provincia de Buenos Aires
ni con el de la Ciudad.
