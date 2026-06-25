import pathlib
import re

import streamlit as st
from utils import render_sidebar

st.set_page_config(page_icon="🔭", page_title="API Guide — StarWolf")
render_sidebar()

st.title("Stargazing Forecast API")

# Construct Swagger URL from the request host (same server, port 8000)
_host = st.context.headers.get("Host", "localhost").split(":")[0]
st.link_button("🔬 Try it out — Swagger UI →", f"http://{_host}:8000/docs")
st.divider()

# Split API_GUIDE.md into tabs: each ### section → one tab, rest → Overview.
# Adding a new endpoint only requires a new ### section in API_GUIDE.md.
_md = pathlib.Path("API_GUIDE.md").read_text()
_parts = re.split(r"\n(?=### )", _md)

_overview, _endpoints = [], {}
for _part in _parts:
    _m = re.match(r"### (.+?)\n", _part)
    # Only promote ### sections that are endpoint definitions (label contains a path)
    if _m and "/" in _m.group(1):
        _endpoints[_m.group(1)] = _part
    else:
        _overview.append(_part)

_tabs = st.tabs(["Overview"] + list(_endpoints.keys()))

with _tabs[0]:
    st.markdown("\n".join(_overview))

for _i, (_label, _content) in enumerate(_endpoints.items(), start=1):
    with _tabs[_i]:
        st.markdown(_content)
