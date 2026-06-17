import streamlit as st

if not hasattr(st, "App"):
    _ver = getattr(st, "__version__", "unknown")
    raise RuntimeError(
        f"Streamlit {_ver} does not support st.App (requires >= 1.58.0).\n"
        "Use the conda environment:\n"
        "  conda activate streamlit\n"
        "  python -m pip install -U \"streamlit>=1.58.0\" -r requirements.txt\n"
        "  python -m streamlit run app.py\n"
        "UI-only fallback (no integrated REST API):\n"
        "  python -m streamlit run ui.py"
    )

from api_routes import build_api_routes

app = st.App(
    "ui.py",
    routes=build_api_routes(),
)
