import streamlit as st
import google.generativeai as genai
from db_config import init_db
from page_pks import render_pks
from page_ia import render_ia
from page_riwayat import render_riwayat
from page_arsip import render_arsip # PASTIKAN IMPORT INI ADA

st.set_page_config(page_title="Sistem Naskah Hukum Unmul", layout="wide")

# Inisialisasi Database
init_db()

# Konfigurasi AI
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
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
    st.session_state.menu_aktif = "📝 Modul PKS (Induk)"

# PASTIKAN MENU ARSIP ADA DI DALAM LIST INI
menu_options = ["📝 Modul PKS (Induk)", "⚙️ Modul IA (Turunan)", "📂 Riwayat & Database", "🗄️ Arsip Otomatis"]
current_idx = menu_options.index(st.session_state.menu_aktif)

menu = st.sidebar.radio("Navigasi Modul:", menu_options, index=current_idx)

if menu != st.session_state.menu_aktif:
    st.session_state.menu_aktif = menu
    st.rerun()

# --- ROUTING HALAMAN ---
if menu == "📝 Modul PKS (Induk)":
    render_pks(model)
elif menu == "⚙️ Modul IA (Turunan)":
    render_ia(model)
elif menu == "📂 Riwayat & Database":
    render_riwayat()
elif menu == "🗄️ Arsip Otomatis": # LOGIKA PEMANGGILAN HALAMAN ARSIP
    render_arsip()
