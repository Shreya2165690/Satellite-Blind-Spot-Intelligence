# Satellite Blind-Spot Intelligence
**“What Changed?” — Automatic Satellite Change Investigator**

A Flask-based prototype for comparing two years of Sentinel-2 imagery over a user-selected area in Satara Taluka.

## Features
- Interactive Leaflet map; draw a polygon for the area of interest.
- Discover Sentinel-2 L2A scenes through the public Element 84 Earth Search STAC API.
- Compare selected years (2016–2026).
- Calculate indicative NDVI vegetation, NDBI built-up and water spectral proxies.
- Store analyses in SQLite and view report pages.
- Expose JSON REST endpoints.

## Requirements
- Windows 10/11, Python 3.10–3.12 recommended.
- Internet connection for satellite catalogue and COG imagery.
- No API key is required for the public Earth Search STAC endpoint.
- A polygon must be drawn inside Satara Taluka. The app does not yet ship an authoritative taluka boundary file; obtain an official boundary GeoJSON from a government/verified GIS source and use it as the basemap boundary in a future integration. The current UI lets the user draw the study polygon and reminds them to keep it within Satara Taluka.

## Run on Windows
```powershell
cd Satellite_Blind_Spot_Intelligence
py -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

If Rasterio installation fails on your Windows Python version, use Python 3.11 in a fresh virtual environment.

## Workflow
1. Draw a polygon in the map (keep it inside Satara Taluka).
2. Select earlier and later years.
3. Click **Find scenes** to inspect available Sentinel-2 observations.
4. Click **Run comparison**.
5. Review metrics and open the report.

## Important scientific limitations
- Sentinel-2 10 m imagery is not sufficient to reliably count every individual house. This prototype reports a spectral **built-up proxy**, not a verified building count.
- The current first version chooses the least-cloudy scene per year; it does not yet apply pixel-level cloud/shadow masking or seasonal compositing.
- Results are exploratory and should not be presented as ground-truth land-use statistics.
- For robust outputs: use same-season multi-scene composites, SCL cloud/shadow masks, accurate polygon geometry, equal-area calculations, and independent validation.
- The project flags these limitations rather than fabricating unavailable imagery or results.

## API endpoints
- `GET /api/health`
- `POST /api/scenes` JSON: `{"geometry": GeoJSONPolygon, "year": 2021}`
- `POST /api/analyze` JSON: `{"geometry": GeoJSONPolygon, "year1":2017, "year2":2021, "max_cloud":30}`
- `GET /api/history`
- `GET /api/report/<analysis_id>`

## Suggested future improvements
- Add official Satara Taluka boundary GeoJSON and enforce polygon containment.
- Add pixel-level Sentinel-2 SCL masking and multi-date seasonal composites.
- Add building-footprint source/model for building counts.
- Add geospatial area measurement with projected CRS.
- Add PDF report export and authentication if required.
