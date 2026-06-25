the# StarWolf — Bortle Lookup Feature (Claude Code Prompt)

## Goal

Add a Bortle class lookup capability to the "Add New Site" flow in StarWolf. The user **must** enter a Bortle value to save a site, but a **"Look Up Bortle"** button should let them auto-populate it from satellite sky brightness data based on the site's lat/lon.

---

## Data Source

**World Atlas of Artificial Night Sky Brightness (Falchi et al. 2016)**
- GeoTIFF file (~2.9 GB), global coverage, 30 arc-second resolution (~900m/pixel)
- Download URL: `http://doi.org/10.5880/GFZ.1.4.2016.001`
- Direct file: `World_Atlas_2015.tif` (inside the zip from the GFZ Data Services DOI above)
- License: CC BY-NC 4.0
- Values are **artificial sky brightness in mcd/m²** (not including natural background)

Store the extracted GeoTIFF at a fixed path on the server, e.g.:
```
/opt/stargazing-app/data/World_Atlas_2015.tif
```

> **Note on currency:** This is 2016 data. It remains authoritative for fixed rural/dark-sky sites in Texas. The Permian Basin region (Midland/Odessa) has gotten significantly brighter since 2016 due to oilfield development — flag this in the UI for sites in that area if desired.

---

## Python Dependencies

Add to `requirements.txt` if not already present:
```
rasterio>=1.3
```

Activate the existing venv before installing:
```bash
source /opt/stargazing-app/venv/bin/activate
pip install rasterio
```

---

## Backend: Bortle Lookup Utility

Create `/opt/stargazing-app/bortle_lookup.py`:

```python
import math
import rasterio
from rasterio.transform import rowcol

WORLD_ATLAS_PATH = "/opt/stargazing-app/data/World_Atlas_2015.tif"

# Natural sky background brightness (mcd/m²) per Falchi et al. and lightpollutionmap.info
NATURAL_SKY_MCD = 0.171168465

def mcd_to_sqm(artificial_brightness_mcd: float) -> float:
    """Convert artificial brightness (mcd/m²) to SQM (mag/arcsec²)."""
    total = artificial_brightness_mcd + NATURAL_SKY_MCD
    return math.log10(total / 108_000_000) / -0.4

def sqm_to_bortle(sqm: float) -> int:
    """
    Convert SQM (mag/arcsec²) to Bortle class (1–9).
    Thresholds from Unihedron / lightpollutionmap.info.
    """
    if sqm >= 21.99:
        return 1
    elif sqm >= 21.89:
        return 2
    elif sqm >= 21.69:
        return 3
    elif sqm >= 20.49:
        return 4
    elif sqm >= 19.50:
        return 5
    elif sqm >= 18.94:
        return 6
    elif sqm >= 18.38:
        return 7
    elif sqm >= 17.80:
        return 8
    else:
        return 9

def lookup_bortle(lat: float, lon: float) -> dict:
    """
    Look up Bortle class for a lat/lon coordinate using the World Atlas GeoTIFF.

    Returns:
        {
            "bortle": int (1–9),
            "sqm": float,
            "artificial_brightness_mcd": float,
            "source": str
        }

    Raises:
        FileNotFoundError if the GeoTIFF is not present.
        ValueError if the coordinate falls outside the raster bounds.
    """
    with rasterio.open(WORLD_ATLAS_PATH) as src:
        # Convert geographic coordinates to raster row/col
        row, col = rowcol(src.transform, lon, lat)

        # Bounds check
        if not (0 <= row < src.height and 0 <= col < src.width):
            raise ValueError(
                f"Coordinates ({lat}, {lon}) are outside the raster extent."
            )

        # Read pixel value (band 1); value is artificial brightness in mcd/m²
        pixel_value = src.read(1)[row, col]

        # NoData check (common sentinel values)
        nodata = src.nodata
        if nodata is not None and pixel_value == nodata:
            raise ValueError(
                f"No data available for coordinates ({lat}, {lon})."
            )

    sqm = mcd_to_sqm(float(pixel_value))
    bortle = sqm_to_bortle(sqm)

    return {
        "bortle": bortle,
        "sqm": round(sqm, 2),
        "artificial_brightness_mcd": round(float(pixel_value), 4),
        "source": "World Atlas of Artificial Night Sky Brightness (Falchi et al. 2016)"
    }
```

---

## Streamlit Integration

In the **Add New Site** form (wherever site creation lives in `app.py` or the relevant page file), update the Bortle field as follows:

### Requirements
- Bortle is a **required field** — the Save/Submit button must be disabled or blocked if it's empty.
- A **"Look Up Bortle"** button triggers the lookup and pre-fills the number input.
- Show the resulting SQM value as supplemental info below the field.
- Show a disclaimer that this is satellite-derived and the user can override it.
- If the GeoTIFF is not present, show a clear error directing the user to download it.

### Example Streamlit snippet

```python
import streamlit as st
from bortle_lookup import lookup_bortle, WORLD_ATLAS_PATH
import os

# --- Inside the Add Site form ---

st.subheader("Light Pollution")

col1, col2 = st.columns([3, 1])

with col1:
    bortle = st.number_input(
        "Bortle Class (required)",
        min_value=1,
        max_value=9,
        step=1,
        value=st.session_state.get("bortle_prefill", None),
        help="1 = darkest skies, 9 = inner city. Required to save this site.",
        key="bortle_input"
    )

with col2:
    st.write("")  # vertical alignment spacer
    st.write("")
    lookup_clicked = st.button("🔭 Look Up", help="Estimate Bortle from satellite data")

if lookup_clicked:
    # lat/lon should already be entered above in the form
    lat = st.session_state.get("site_lat")
    lon = st.session_state.get("site_lon")

    if not lat or not lon:
        st.warning("Enter latitude and longitude first.")
    elif not os.path.exists(WORLD_ATLAS_PATH):
        st.error(
            f"World Atlas GeoTIFF not found at `{WORLD_ATLAS_PATH}`. "
            "See setup instructions to download it."
        )
    else:
        with st.spinner("Looking up sky brightness data..."):
            try:
                result = lookup_bortle(lat, lon)
                st.session_state["bortle_prefill"] = result["bortle"]
                st.success(
                    f"Estimated **Bortle {result['bortle']}** "
                    f"(SQM: {result['sqm']} mag/arcsec²)"
                )
                st.caption(
                    "⚠️ Satellite-derived estimate (2016 data). "
                    "You can override this value before saving."
                )
                st.rerun()
            except ValueError as e:
                st.error(f"Lookup failed: {e}")
            except Exception as e:
                st.error(f"Unexpected error during lookup: {e}")

# Enforce required field before form submission
bortle_valid = bortle is not None and 1 <= bortle <= 9
if not bortle_valid:
    st.warning("Bortle class is required before saving.")

# Gate the save button
save_disabled = not bortle_valid  # combine with other required field checks
if st.button("Save Site", disabled=save_disabled):
    # proceed with save logic
    pass
```

---

## One-Time GeoTIFF Setup

Include these instructions in your internal README or a `setup.md`:

```
1. Download the World Atlas zip from:
   http://doi.org/10.5880/GFZ.1.4.2016.001

   (GFZ Data Services page — look for the .zip download link)

2. Extract World_Atlas_2015.tif from the zip.

3. Place it at:
   /opt/stargazing-app/data/World_Atlas_2015.tif

4. The file is ~2.9 GB. It only needs to be downloaded once.
   rasterio reads it without loading it fully into memory.
```

---

## Validation Checklist

After implementation, test the following:

- [ ] `lookup_bortle(30.25, -104.0)` (near McDonald Observatory) returns Bortle 1 or 2
- [ ] `lookup_bortle(29.76, -95.37)` (Houston) returns Bortle 8 or 9
- [ ] Attempting to save with no Bortle entered is blocked
- [ ] "Look Up" with missing lat/lon shows a clear warning
- [ ] "Look Up" with missing GeoTIFF shows the setup error message
- [ ] Looked-up value pre-fills the number input and is editable before saving

---

## Notes

- `rasterio` uses lazy I/O — it does **not** load the full 2.9 GB file into RAM. The pixel read is fast (~milliseconds).
- The lookup is synchronous and happens at site-add time only. No caching needed.
- If you later store `sqm` in the DB alongside `bortle`, you can use it for richer site comparison UI.
- The GeoTIFF uses WGS84 (EPSG:4326) — same coordinate system as your lat/lon inputs. No projection conversion needed.
