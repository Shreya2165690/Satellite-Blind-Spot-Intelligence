
"""Sentinel-2 L2A satellite discovery and land-cover change analysis."""

from datetime import datetime, timezone
import math
import requests
import numpy as np

STAC_SEARCH = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"
TIMEOUT = 60

HEADERS = {
    "Accept": "application/geo+json",
    "Content-Type": "application/json"
}

# SCL classes excluded: no data, defective, shadow, unclassified,
# cloud medium/high probability, cirrus and snow/ice.
BAD_SCL_CLASSES = {0, 1, 3, 7, 8, 9, 10, 11}

# Satara Taluka is in UTM zone 43N.
TARGET_CRS = "EPSG:32643"
PIXEL_SIZE = 10


def _validate_geometry(geometry):
    if not isinstance(geometry, dict):
        raise ValueError("Draw a polygon on the map first.")

    if geometry.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError("Only polygon or rectangle selection is supported.")

    if not geometry.get("coordinates"):
        raise ValueError("Selected polygon is empty.")

    return geometry


def _has_required_assets(item):
    if item.get("collection") != COLLECTION:
        return False

    assets = item.get("assets") or {}

    required = ("red", "nir", "swir16", "scl")

    return all(
        (assets.get(key) or {}).get("href")
        for key in required
    )


def _items(geometry, year, max_cloud=30, limit=100):

    geometry = _validate_geometry(geometry)

    year = int(year)
    max_cloud = float(max_cloud)

    if not 0 <= max_cloud <= 100:
        raise ValueError("Cloud cover must be between 0 and 100.")

    payload = {
        "collections": [COLLECTION],
        "intersects": geometry,
        "datetime": (
            f"{year}-01-01T00:00:00Z/"
            f"{year}-12-31T23:59:59Z"
        ),
        "query": {
            "eo:cloud_cover": {
                "lte": max_cloud
            }
        },
        "limit": min(int(limit), 100)
    }

    try:
        response = requests.post(
            STAC_SEARCH,
            json=payload,
            headers=HEADERS,
            timeout=TIMEOUT
        )

        response.raise_for_status()
        data = response.json()

    except requests.RequestException as exc:
        raise RuntimeError(
            f"Satellite catalogue connection failed: {exc}"
        ) from exc

    except ValueError as exc:
        raise RuntimeError(
            "Invalid response received from satellite catalogue."
        ) from exc

    features = data.get("features", [])

    # Strictly reject Sentinel-1 and other collections.
    valid_items = [
        item for item in features
        if _has_required_assets(item)
    ]

    return valid_items


def search_scenes(geometry, year):

    items = _items(
        geometry,
        year,
        max_cloud=100,
        limit=100
    )

    scenes = []

    for item in items[:20]:

        props = item.get("properties") or {}

        scenes.append({
            "id": item.get("id"),
            "date": (props.get("datetime") or "")[:10],
            "cloud_cover": props.get("eo:cloud_cover"),
            "platform": props.get("platform"),
            "collection": item.get("collection")
        })

    return {
        "year": int(year),
        "count": len(items),
        "scenes": scenes,
        "catalogue": "Element 84 Earth Search STAC",
        "collection": COLLECTION
    }


def _scene_date(item):

    return (
        item.get("properties") or {}
    ).get("datetime", "")


def _choose_scene(items):

    def score(item):

        props = item.get("properties") or {}

        cloud = props.get("eo:cloud_cover")

        if cloud is None:
            cloud = 100

        try:
            acquired = datetime.fromisoformat(
                _scene_date(item).replace("Z", "+00:00")
            )

            day_difference = abs(
                acquired.timetuple().tm_yday - 182
            )

        except (ValueError, TypeError):
            day_difference = 365

        return float(cloud), day_difference

    return min(items, key=score)


def _make_grid(geometry):

    from rasterio.warp import transform_geom

    projected = transform_geom(
        "EPSG:4326",
        TARGET_CRS,
        geometry
    )

    points = []

    def walk(value):

        if isinstance(value, (list, tuple)):

            if (
                len(value) >= 2
                and isinstance(value[0], (int, float))
                and isinstance(value[1], (int, float))
            ):
                points.append(
                    (float(value[0]), float(value[1]))
                )

            else:
                for child in value:
                    walk(child)

    walk(projected["coordinates"])

    if not points:
        raise ValueError("Could not calculate polygon boundaries.")

    xs, ys = zip(*points)

    minx = min(xs)
    maxx = max(xs)
    miny = min(ys)
    maxy = max(ys)

    width = math.ceil((maxx - minx) / PIXEL_SIZE)
    height = math.ceil((maxy - miny) / PIXEL_SIZE)

    if width <= 0 or height <= 0:
        raise ValueError("Selected area is too small.")

    if width * height > 25_000_000:
        raise ValueError(
            "Selected area is too large. Please draw a smaller polygon."
        )

    from rasterio.transform import from_origin

    transform = from_origin(
        minx,
        maxy,
        PIXEL_SIZE,
        PIXEL_SIZE
    )

    return projected, transform, width, height


def _read_asset(
    url,
    transform,
    width,
    height,
    resampling,
    dtype="float32"
):

    import rasterio
    from rasterio.warp import reproject

    destination = np.zeros(
        (height, width),
        dtype=dtype
    )

    with rasterio.open(url) as src:

        if src.crs is None:
            raise RuntimeError(
                "Satellite image has no coordinate reference system."
            )

        if dtype == "float32":

            destination.fill(np.nan)
            destination_nodata = np.nan

        else:

            destination_nodata = 0

        source_nodata = (
            src.nodata if src.nodata is not None else 0
        )

        reproject(
            source=rasterio.band(src, 1),
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=source_nodata,
            dst_transform=transform,
            dst_crs=TARGET_CRS,
            dst_nodata=destination_nodata,
            resampling=resampling,
            init_dest_nodata=True
        )

    return destination


def _read_scene(item, geometry):

    import rasterio
    from rasterio.enums import Resampling
    from rasterio.features import geometry_mask

    assets = item["assets"]

    try:

        projected, transform, width, height = _make_grid(
            geometry
        )

        inside = geometry_mask(
            [projected],
            out_shape=(height, width),
            transform=transform,
            invert=True
        )

        if not inside.any():
            raise RuntimeError(
                "Selected polygon contains no pixels at 10 m resolution."
            )

        # Sentinel-2 optical bands.
        red = _read_asset(
            assets["red"]["href"],
            transform, width, height,
            Resampling.bilinear
        )

        nir = _read_asset(
            assets["nir"]["href"],
            transform, width, height,
            Resampling.bilinear
        )

        swir = _read_asset(
            assets["swir16"]["href"],
            transform, width, height,
            Resampling.bilinear
        )

        # SCL is categorical: nearest-neighbour resampling.
        scl = _read_asset(
            assets["scl"]["href"],
            transform, width, height,
            Resampling.nearest,
            dtype="int16"
        )

        # Convert Sentinel-2 integer reflectance to reflectance units.
        if np.isfinite(red).any() and np.nanmax(red) > 2:
            red /= 10000.0

        if np.isfinite(nir).any() and np.nanmax(nir) > 2:
            nir /= 10000.0

        if np.isfinite(swir).any() and np.nanmax(swir) > 2:
            swir /= 10000.0

        ndvi_den = nir + red
        ndbi_den = swir + nir

        ndvi = np.divide(
            nir - red,
            ndvi_den,
            out=np.full_like(red, np.nan),
            where=np.abs(ndvi_den) > 1e-6
        )

        ndbi = np.divide(
            swir - nir,
            ndbi_den,
            out=np.full_like(red, np.nan),
            where=np.abs(ndbi_den) > 1e-6
        )

        valid = (
            inside
            & np.isfinite(ndvi)
            & np.isfinite(ndbi)
            & (red > 0)
            & (nir > 0)
            & ~np.isin(
                scl,
                list(BAD_SCL_CLASSES)
            )
        )

        ndvi[~valid] = np.nan
        ndbi[~valid] = np.nan

        return ndvi, ndbi, valid, inside

    except Exception as exc:

        if isinstance(exc, RuntimeError):
            raise

        raise RuntimeError(
            "Could not read Sentinel-2 imagery. "
            "Check internet access and satellite asset availability. "
            f"Details: {exc}"
        ) from exc


def run_comparison(
    geometry,
    year1,
    year2,
    max_cloud=30
):

    geometry = _validate_geometry(geometry)

    year1 = int(year1)
    year2 = int(year2)

    current_year = datetime.now(timezone.utc).year

    if year1 < 2017 or year2 > current_year or year1 >= year2:
        raise ValueError(
            f"Choose increasing years between 2017 and {current_year}."
        )

    # Search for genuine Sentinel-2 L2A scenes.
    earlier_items = _items(
        geometry, year1, max_cloud, 100
    )

    later_items = _items(
        geometry, year2, max_cloud, 100
    )

    if not earlier_items or not later_items:

        return {
            "status": "no_data",
            "message": (
                "No suitable Sentinel-2 L2A scenes were found "
                "for one or both selected years. Try increasing "
                "the cloud threshold or selecting different years."
            ),
            "years": {
                "earlier": year1,
                "later": year2
            },
            "scene_counts": {
                str(year1): len(earlier_items),
                str(year2): len(later_items)
            },
            "limitations": [
                "No comparison was generated because suitable real satellite imagery was unavailable."
            ]
        }

    item1 = _choose_scene(earlier_items)
    item2 = _choose_scene(later_items)

    ndvi1, ndbi1, valid1, inside1 = _read_scene(
        item1, geometry
    )

    ndvi2, ndbi2, valid2, inside2 = _read_scene(
        item2, geometry
    )

    # Both scenes use the same target CRS, transform and dimensions.
    if ndvi1.shape != ndvi2.shape:
        raise RuntimeError(
            "The two satellite images could not be aligned to the same grid."
        )

    valid = (
        valid1
        & valid2
        & inside1
        & inside2
    )

    valid_count = int(valid.sum())
    area_pixels = int((inside1 & inside2).sum())

    if valid_count == 0:
        raise RuntimeError(
            "No common clear pixels were available in both observations. "
            "Try another year pair or a different study area."
        )

    # Indicative spectral classes.
    vegetation1 = (ndvi1 > 0.35) & valid
    vegetation2 = (ndvi2 > 0.35) & valid

    built1 = (
        (ndbi1 > 0.05)
        & (ndvi1 < 0.35)
        & valid
    )

    built2 = (
        (ndbi2 > 0.05)
        & (ndvi2 < 0.35)
        & valid
    )

    water1 = (
        (ndvi1 < 0)
        & (ndbi1 < 0)
        & valid
    )

    water2 = (
        (ndvi2 < 0)
        & (ndbi2 < 0)
        & valid
    )

    def percentage(mask):

        return round(
            100.0 * int(mask.sum()) / valid_count,
            2
        )

    def make_metric(first, second):

        p1 = percentage(first)
        p2 = percentage(second)

        return {
            "earlier": p1,
            "later": p2,
            "change_pp": round(p2 - p1, 2)
        }

    vegetation = make_metric(
        vegetation1, vegetation2
    )

    built = make_metric(
        built1, built2
    )

    water = make_metric(
        water1, water2
    )

    coverage = round(
        100.0 * valid_count / max(area_pixels, 1),
        2
    )

    props1 = item1.get("properties") or {}
    props2 = item2.get("properties") or {}

    return {
        "status": "completed",

        "years": {
            "earlier": year1,
            "later": year2
        },

        "scenes": {
            "earlier": {
                "id": item1.get("id"),
                "date": _scene_date(item1)[:10],
                "cloud_cover": props1.get("eo:cloud_cover")
            },
            "later": {
                "id": item2.get("id"),
                "date": _scene_date(item2)[:10],
                "cloud_cover": props2.get("eo:cloud_cover")
            }
        },

        "valid_pixel_count": valid_count,
        "valid_coverage_percent": coverage,

        "metrics": {
            "vegetation_percent": vegetation,
            "built_up_proxy_percent": built,
            "water_proxy_percent": water
        },

        "findings": [
            f"Vegetation spectral proxy changed by {vegetation['change_pp']} percentage points.",
            f"Built-up spectral proxy changed by {built['change_pp']} percentage points.",
            f"Water spectral proxy changed by {water['change_pp']} percentage points."
        ],

        "blind_spots": {
            "valid_coverage_percent": coverage,
            "warning": (
                "SCL cloud, shadow, cirrus, snow and invalid pixels "
                "were excluded. Remaining atmospheric and classification "
                "errors may still affect the result."
            )
        },

        "limitations": [
            "Built-up proxy is not a count of houses or verified building footprints.",
            "Only one least-cloudy scene per year is used.",
            "The SWIR band has 20 m native resolution and is resampled to the 10 m grid.",
            "Different acquisition dates, seasons and atmospheric conditions can affect the comparison.",
            "Results are exploratory spectral indicators, not ground-truth land-use statistics.",
            "Research-grade results require seasonal composites and independent validation."
        ]
    }
