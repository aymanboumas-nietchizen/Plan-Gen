# PLANFGEN — Space Planning Engine

## Project Structure
- `planfgen/` — main Python package
  - `core/` — geometry, generator (BFS placement + Voronoi fill), scorer, optimizer, walls
  - `rules/` — base_rules, ma_rules (Moroccan DTU codes), access_rules
  - `export/` — json_export, dxf
  - `studio/` — Streamlit app (`app.py`, `components.py`)
  - `grasshopper/` — Rhino/Grasshopper integration
  - `tests/` — pytest test suite
  - `examples/` — sample programmes (apartment, school, office)
  - `main.py` — CLI entry point

## Environment
- Python 3.12 installed at `/c/Users/USER/AppData/Local/Programs/Python/Python312/`
- Always `export PATH="/c/Users/USER/AppData/Local/Programs/Python/Python312:$PATH"` before running python/pip
- Dependencies: `pip install -r planfgen/requirements.txt`

## Commands
- **Run tests:** `python -m pytest planfgen/tests/ -v`
- **Run CLI:** `python planfgen/main.py --programme <json> --W 12 --H 9 --N 200`
- **Run Streamlit:** `streamlit run planfgen/studio/app.py --server.headless true`
- **Clear caches:** `find . -type d -name __pycache__ -exec rm -rf {} +`

## Code Conventions
- French naming for domain terms: `nom`, `surface`, `couleur`, `facade`, `adjacences`, `compacite`, `couverture`
- Geometry via Shapely `Polygon`; graph via NetworkX
- Scoring: `Score_global = 0.40×adjacences + 0.25×compacite + 0.20×facade + 0.15×couverture`
- DXF export: always use `doc.saveas(filepath)`, never `doc.save()`
- After modifying modules, clear `__pycache__` dirs before running Streamlit

## Key Architecture Notes
- Generator uses BFS placement from hub node + Voronoi tessellation to fill voids
- Hub = node with highest `degree * surface` product, placed at seed-dependent corner
- Optimizer generates N variants (different seeds), returns top-K by score
- Layouts with < 50% adjacency score are filtered out (`min_adj_score=0.5`, auto-relaxes)
