import math
from pathlib import Path

import rasterio
from rasterio.transform import rowcol

WORLD_ATLAS_PATH = str(Path(__file__).parent.parent.parent / "data" / "World_Atlas_2015.tif")

# Natural sky background brightness per Falchi et al. 2016
_NATURAL_SKY_MCD = 0.171168465


def _mcd_to_sqm(artificial_mcd: float) -> float:
    total = artificial_mcd + _NATURAL_SKY_MCD
    return math.log10(total / 108_000_000) / -0.4


def _sqm_to_bortle(sqm: float) -> int:
    if sqm >= 21.99: return 1
    if sqm >= 21.89: return 2
    if sqm >= 21.69: return 3
    if sqm >= 20.49: return 4
    if sqm >= 19.50: return 5
    if sqm >= 18.94: return 6
    if sqm >= 18.38: return 7
    if sqm >= 17.80: return 8
    return 9


def lookup_bortle(lat: float, lon: float) -> dict:
    """
    Returns {"bortle": int, "sqm": float} for a lat/lon coordinate.
    Raises FileNotFoundError if the GeoTIFF is missing.
    Raises ValueError if the coordinate is outside the raster or has no data.
    """
    with rasterio.open(WORLD_ATLAS_PATH) as src:
        row, col = rowcol(src.transform, lon, lat)
        if not (0 <= row < src.height and 0 <= col < src.width):
            raise ValueError(f"Coordinates ({lat}, {lon}) are outside the raster extent.")
        pixel = float(src.read(1)[row, col])
        if src.nodata is not None and pixel == src.nodata:
            raise ValueError(f"No data available for coordinates ({lat}, {lon}).")

    sqm = _mcd_to_sqm(pixel)
    return {"bortle": _sqm_to_bortle(sqm), "sqm": round(sqm, 2)}
