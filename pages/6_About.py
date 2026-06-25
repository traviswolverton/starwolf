import streamlit as st
from utils import render_sidebar

st.set_page_config(page_icon="🔭", page_title="About — StarWolf")
render_sidebar()

st.title("About StarWolf")

st.markdown("""
StarWolf is a personal stargazing trip planner built by Seth and Travis Wolverton.
It pulls live weather and atmospheric data, combines it with moon phase and light
pollution information, and scores each site/night combination so you can find the
best window for your next observing session.

**StarWolf is a non-commercial, personal project.** It is not affiliated with any
of the data providers listed below. Forecasts are for planning purposes only —
conditions can change. This is not a professional meteorological service.
""")

st.divider()
st.header("Data Sources")

with st.expander("☁️ Weather Forecasts — Open-Meteo", expanded=True):
    st.markdown("""
**Provider:** [Open-Meteo](https://open-meteo.com)

Open-Meteo is a free, open-source weather API that aggregates forecasts from national
weather services worldwide. StarWolf uses it for cloud cover, precipitation probability,
humidity, visibility, and atmospheric stability (lifted index).

- **License:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — attribution required
- **Update frequency:** Hourly
- **Coverage:** Global
- **Terms:** [open-meteo.com/en/terms](https://open-meteo.com/en/terms)
""")

with st.expander("🔭 Astronomical Seeing & Transparency — 7timer!", expanded=True):
    st.markdown("""
**Provider:** [7timer!](http://7timer.info) by Ye Quanzhi, Tongji University

7timer! is a free astronomical weather service purpose-built for observers. StarWolf
uses its ASTRO product for seeing (atmospheric steadiness) and sky transparency.
Both are rated on a **1–8 scale where 1 is best**. Coverage is limited to approximately
3 days ahead — nights beyond that show `—` for these fields.

- **License:** Free academic service; attribution requested
- **Update frequency:** Every 6 hours
- **Coverage:** Global, ~3-day horizon
""")

with st.expander("🌑 Dark Sky Site Catalog — IDA / DarkSky International", expanded=True):
    st.markdown("""
**Provider:** [International Dark-Sky Association / DarkSky.org](https://darksky.org)

The site catalog is seeded from the IDA's publicly published list of designated
International Dark Sky Places. Coordinates were sourced via the OpenStreetMap
Overpass API, where IDA-designated locations are tagged by the OSM community.

- **IDA designation data:** Publicly published, non-commercial use
- **Coordinate data:** [OpenStreetMap](https://www.openstreetmap.org) contributors, [ODbL](https://opendatacommons.org/licenses/odbl/)
- **© OpenStreetMap contributors**
""")

with st.expander("📍 Geocoding — Nominatim / OpenStreetMap", expanded=True):
    st.markdown("""
**Provider:** [Nominatim](https://nominatim.org) (OpenStreetMap)

Nominatim is used to convert addresses and place names to coordinates when you set
your location or add a site by address. It is operated by the OpenStreetMap Foundation
and is free for low-volume, non-commercial use.

- **License:** [ODbL](https://opendatacommons.org/licenses/odbl/) — © OpenStreetMap contributors
- **Usage policy:** [nominatim.org/release-docs/latest/api/Overview](https://nominatim.org/release-docs/latest/api/Overview/)
- **Rate:** Single lookups only; StarWolf does not perform bulk geocoding
""")

with st.expander("💡 Light Pollution Data — World Atlas of Artificial Night Sky Brightness", expanded=True):
    st.markdown("""
**Provider:** Falchi et al. (2016), GFZ German Research Centre for Geosciences

StarWolf uses this dataset to look up Bortle class estimates when adding new dark-sky
sites. The dataset maps artificial sky brightness worldwide at ~1 km resolution.

- **Full citation:**
  Fabio Falchi, Pierantonio Cinzano, Dan Duriscoe, Christopher C.M. Kyba,
  Christopher D. Elvidge, Kimberly Baugh, Boris A. Portnov, Nataliya A. Rybnikova,
  Riccardo Motta (2016): *The new world atlas of artificial night sky brightness.*
  V. 1.1. GFZ Data Services.
  [https://doi.org/10.5880/GFZ.1.4.2016.001](https://doi.org/10.5880/GFZ.1.4.2016.001)
- **License:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — attribution required
""")

with st.expander("🌙 Moon & Astronomical Calculations — astral", expanded=True):
    st.markdown("""
**Library:** [astral](https://astral.readthedocs.io) by Simon Kennedy

Astral provides moon phase, illumination, and rise/set calculations used in StarWolf's
moon scoring factor.

- **License:** [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0)
""")

with st.expander("🤖 AI Forecast Summaries — Ollama", expanded=True):
    st.markdown("""
**Runtime:** [Ollama](https://ollama.com) (MIT License)

When enabled, StarWolf generates plain-language forecast summaries using a large
language model running **locally on the host machine** via Ollama. No data is sent
to any external AI service.

- **Default model:** Llama 3.1 8B by Meta
  ([Meta Llama 3 Community License](https://www.llama.com/llama3/license/))
- **Data privacy:** All AI inference is local; your forecast data never leaves your machine
- **This feature is optional** and can be disabled in Admin → App Settings
""")

st.divider()
st.header("Disclaimer")

st.info("""
StarWolf is provided as-is for personal, non-commercial use. Forecasts are generated
from third-party data sources and are intended for planning purposes only. Actual
conditions may differ significantly. StarWolf is not responsible for decisions made
based on its forecasts. Always check current conditions before traveling to a remote site.
""", icon="⚠️")

st.divider()
st.caption(
    "StarWolf · Built with [Streamlit](https://streamlit.io) and [Claude](https://anthropic.com) · "
    "[Source](https://gitea.wolvertons.net/travis/stargazing-app)"
)
