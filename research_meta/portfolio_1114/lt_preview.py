"""Local preview of the Long Term Investment page on its own (no scanner, no warmers):
streamlit run research_meta/portfolio_1114/lt_preview.py --server.port 8766   (add ?admin=1 to see the real-fills view)"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
try:                      # the home PC sits behind a VPN that needs the system trust store
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass
import streamlit as st

st.set_page_config(page_title="Long Term Investment (preview)", layout="wide")
import longterm_page

longterm_page.render(None, admin=st.query_params.get("admin") == "1")
