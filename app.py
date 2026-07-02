import streamlit as st
import google.generativeai as genai
from db_config import init_db

# (Nantinya buat file page_pks.py dan page_riwayat.py lalu import di sini)
# from page_pks import render_pks 
# from page_riwayat import render_riwayat
from page_ia import render_ia

st.set_page_config(page_title="Generator Naskah Hukum Unmul", layout="wide")

# Inisialisasi Database
init_db()

# Konfigurasi AI di tingkat aplikasi utama
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

menu = st.sidebar.radio(
    "Navigasi Modul:", 
    ["📝 Modul PKS (Induk)", "⚙️ Modul IA (Turunan)", "📂 Riwayat & Database"]
)

if menu == "📝 Modul PKS (Induk)":
    st.info("Pindahkan kode UI PKS Anda ke dalam fungsi render_pks() di file page_pks.py")
    # render_pks(model)
    
elif menu == "⚙️ Modul IA (Turunan)":
    # Memanggil antarmuka IA dari file page_ia.py
    render_ia(model)
    
elif menu == "📂 Riwayat & Database":
    st.info("Pindahkan kode UI Riwayat Anda ke dalam fungsi render_riwayat() di file page_riwayat.py")
    # render_riwayat()
