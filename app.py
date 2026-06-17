import streamlit as st

from api_routes import build_api_routes

app = st.App(
    "ui.py",
    routes=build_api_routes(),
)
