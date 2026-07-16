import streamlit as st
import google.generativeai as genai
import os
from db_config import init_db
from page_pks import render_pks
from page_ia import render_ia
from page_riwayat import render_riwayat
from page_arsip import render_arsip
from page_dashboard import render_dashboard

st.set_page_config(page_title="Sistem Naskah Hukum Unmul", layout="wide")

init_db()

# --- HARD OVERRIDE API KEY ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"].strip().strip('"').strip("'")
    os.environ["GOOGLE_API_KEY"] = API_KEY
    genai.configure(api_key=API_KEY)
except KeyError:
    st.error("API Key Gemini tidak ditemukan di st.secrets.")
    st.stop()

@st.cache_resource
def get_ai_model():
    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    priority = ['models/gemini-1.5-flash-latest', 'models/gemini-1.5-flash']
    selected = next((m for m in priority if m in available_models), available_models[0])
    return genai.GenerativeModel(selected)

model = get_ai_model()

# --- NAVIGASI MULTI-MODUL ---
st.sidebar.title("Sistem Naskah Kerja Sama")
st.sidebar.markdown("Universitas Mulawarman")

if 'menu_aktif' not in st.session_state:
    st.session_state.menu_aktif = "📈 Modul Dashboard"

menu_options = ["📈 Modul Dashboard", "📝 Modul PKS (Induk)", "⚙️ Modul IA (Turunan)", "📂 Riwayat & Database", "🗄️ Arsip Otomatis"]
current_idx = menu_options.index(st.session_state.menu_aktif)

menu = st.sidebar.radio("Navigasi Modul:", menu_options, index=current_idx)

if menu != st.session_state.menu_aktif:
    st.session_state.menu_aktif = menu
    st.rerun()

# --- ROUTING HALAMAN ---
if menu == "📈 Modul Dashboard":
    render_dashboard()
elif menu == "📝 Modul PKS (Induk)":
    render_pks(model)
elif menu == "⚙️ Modul IA (Turunan)":
    render_ia(model)
elif menu == "📂 Riwayat & Database":
    render_riwayat()
elif menu == "🗄️ Arsip Otomatis":
    render_arsip()
