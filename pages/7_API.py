import pathlib
import streamlit as st
from utils import render_sidebar

st.set_page_config(page_icon="🔭", page_title="API Guide — StarWolf")
render_sidebar()

st.markdown(pathlib.Path("API_GUIDE.md").read_text())
