# Abstract
Satellite Blind-Spot Intelligence (“What Changed?”) is a web-based remote-sensing prototype designed to investigate land-cover changes within Satara Taluka, Maharashtra. A user draws a study polygon, chooses two observation years between 2016 and 2026, and requests satellite observations from the public Sentinel-2 catalogue. The processing pipeline compares spectral indices derived from red, near-infrared and short-wave infrared bands. It reports indicative vegetation, built-up and water spectral proxies, together with scene dates, cloud metadata, valid-pixel coverage and data-quality limitations. A Flask backend exposes REST endpoints, while SQLite stores investigation history. The frontend uses Leaflet for interactive map selection and displays results in a dashboard. The system is designed to support historical visual investigation; its outputs are exploratory and are not a substitute for verified building inventories or ground-truth land-use surveys.

## Objectives
1. Retrieve historical Sentinel-2 observations for a user-selected area.
2. Compare two selected years within 2016–2026.
3. Estimate vegetation, built-up and water spectral proxy changes.
4. Identify data-quality blind spots and communicate uncertainty.
5. Store analyses and present an investigation report.

## Modules
Frontend dashboard, Flask REST backend, STAC satellite discovery, raster processing, spectral-index comparison, SQLite database, report view.

## Expected outcome
A working prototype that demonstrates the end-to-end workflow using real satellite observations when suitable scenes are available.
