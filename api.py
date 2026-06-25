from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from sqlalchemy import text

from db import get_engine, get_settings, init_db
from forecast import fetch_site_forecast
from scorer import score_forecast


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Stargazing Forecast API",
    description=(
        "Score upcoming nights at any lat/lon for telescope and naked eye observing. "
        "All nights are returned; no threshold filtering is applied."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/healthz", include_in_schema=False)
def health():
    return {"status": "ok"}


@app.get("/v1/sites")
def get_sites() -> dict[str, Any]:
    """
    Bulk export of all sites in the catalog.

    Returns every site regardless of active status.
    """
    with get_engine().connect() as conn:
        rows = conn.execute(text(
            "SELECT id, name, lat, lon, bortle_class, elevation_m, notes, active, site_type "
            "FROM sites ORDER BY name"
        )).fetchall()

    sites = [dict(r._mapping) for r in rows]
    return {"count": len(sites), "sites": sites}


@app.get("/v1/forecast")
def get_forecast(
    lat: float = Query(..., ge=-90,   le=90,  description="Latitude"),
    lon: float = Query(..., ge=-180,  le=180, description="Longitude"),
    days: int  = Query(7,   ge=1,    le=16,  description="Forecast horizon in days (1–16)"),
    timezone: str | None  = Query(None, description="IANA timezone string. Defaults to the app-level setting."),
    bortle_class: int | None = Query(None, ge=1, le=9, description="Bortle class (1–9) for naked eye modifier. Omit for no penalty."),
) -> dict[str, Any]:
    """
    Return scored nights for a given location.

    Each night includes:
    - **composite** — telescope score (0–100)
    - **naked_eye** — naked eye score (0–100), Bortle-adjusted if `bortle_class` is supplied
    - **factors** — per-factor 0–100 scores used to build the composite
    - **stats** — raw averages (cloud cover, humidity, etc.) and 7timer data where available
    - **seven_timer_tier** — blended 7timer quality tier (`excellent`/`good`/`mediocre`/`no_data`) with a 0–100 score; `no_data` when 7timer data is unavailable (beyond ~3 days)

    Returns **502** if Open-Meteo is unavailable (no nights can be scored).
    7timer failures are soft — nights are still returned and `errors[]` will be non-empty.
    """
    settings = get_settings()
    tz = timezone or settings.get("timezone", "America/Chicago")

    site = {
        "name": f"{lat:.4f},{lon:.4f}",
        "lat": lat,
        "lon": lon,
        "bortle_class": bortle_class,
    }

    forecast = fetch_site_forecast(site, days, tz)

    if forecast["open_meteo"] is None:
        om_errors = [e for e in forecast.get("errors", []) if e.startswith("Open-Meteo")]
        detail = om_errors[0] if om_errors else "Open-Meteo forecast unavailable"
        raise HTTPException(status_code=502, detail=detail)

    nights = score_forecast(forecast, tz)  # no disqualifiers — return all nights

    return {
        "lat":      lat,
        "lon":      lon,
        "timezone": tz,
        "days":     days,
        "nights":   nights,
        "errors":   forecast.get("errors", []),
    }
