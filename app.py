import streamlit as st
import google.generativeai as genai
import psycopg2
from fpdf import FPDF
from datetime import datetime

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Generator PKS Unmul", layout="wide")

# --- KONFIGURASI SECRETS ---
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except KeyError:
    st.error("API Key Gemini tidak ditemukan di st.secrets. Pastikan rahasia telah diatur di Streamlit Cloud.")
    st.stop()

# --- KONEKSI DATABASE NEON ---
def get_db_connection():
    try:
        conn = psycopg2.connect(st.secrets["NEON_CONNECTION_STRING"])
        return conn
    except Exception as e:
        st.error(f"Gagal terhubung ke database: {e}")
        return None

# --- LOGIKA PEMILIHAN MODEL DINAMIS ---
@st.cache_resource
def load_best_gemini_model():
    """
    Mencari model Gemini terbaik yang tersedia di API Key pengguna.
    Hasilnya di-cache oleh Streamlit agar tidak perlu mengecek API berulang kali.
    """
    try:
        available_models = [
            m.name for m in genai.list_models() 
            if 'generateContent' in m.supported_generation_methods
        ]
        
        if not available_models:
            return None, "Tidak ada model teks yang tersedia di API Key ini."

        priority_models = [
            'models/gemini-1.5-flash-latest',
            'models/gemini-1.5-flash',
            'models/gemini-1.5-pro-latest',
            'models/gemini-1.0-pro'
        ]
        
        selected_model_name = next((model for model in priority_models if model in available_models), None)
        
        if not selected_model_name:
            selected_model_name = available_models[0]
            
        model = genai.GenerativeModel(selected_model_name)
        print(f"✅ [SISTEM PKS] Model berhasil dimuat: {selected_model_name}")
        return model, selected_model_name

    except Exception as e:
        print(f"❌ [SISTEM PKS] Gagal memuat daftar model: {e}")
        return None, str(e)

# --- INISIALISASI MODEL ---
model, status_model = load_best_gemini_model()

with st.sidebar:
    st.write("### Status Sistem")
    if model:
        st.success(f"🤖 AI Aktif: `{status_model.split('/')[-1]}`")
    else:
        st.error(f"Gagal memuat AI: {status_model}")
        st.stop()

# --- INISIALISASI SESSION STATE ---
if 'draft_pks' not in st.session_state:
    st.session_state.draft_pks = ""

st.title("Generator Naskah PKS Universitas Mulawarman")

# --- BAGIAN 1: INPUT FIELD ---
with st.expander("1. Form Data PKS", expanded=True):
    col1, col2 = st.columns(2)
    
    with col1:
        logo_mitra = st.file_uploader("Unggah Logo Mitra (PNG/JPG)", type=["png", "jpg", "jpeg"])
        nama_mitra = st.text_input("Nama Mitra")
        judul_ks = st.text_input("Judul Kerja Sama")
        no_unit_unmul = st.text_input("No Surat Unit/Fakultas Pihak 1")
        no_mitra = st.text_input("No Surat Mitra Pihak 2")
        hari = st.text_input("Hari Penandatanganan (Contoh: Senin)")
        tanggal_teks = st.text_input("Tanggal, Bulan, Tahun (Teks, contoh: Dua Puluh Dua April...)")
        
        st.subheader("Pihak 1 (Universitas Mulawarman)")
        nama_p1 = st.text_input("Nama Pejabat Pihak 1")
        jabatan_p1 = st.text_input("Jabatan Pihak 1")
        nip_p1 = st.text_input("NIP Pejabat Pihak 1")
        lembaga_p1 = st.text_input("Nama Lembaga Pihak 1 (Cth: Fakultas Ilmu Budaya)")
        alamat_p1 = st.text_area("Alamat Lembaga Pihak 1")

    with col2:
        st.subheader("Pihak 2 (Mitra)")
        nama_p2 = st.text_input("Nama Pejabat Pihak 2")
        jabatan_p2 = st.text_input("Jabatan Pihak 2")
        nip_p2 = st.text_input("NIP Pejabat Pihak 2 (Kosongkan jika tidak ada)")
        alamat_mitra = st.text_area("Alamat Mitra")
        
        st.subheader("Detail Kerja Sama")
        ruang_lingkup = st.text_area("Ruang Lingkup Kerja Sama")
        prodi_terlibat = st.text_area("Prodi yang Terlibat (Pisahkan dengan koma)")
        tgl_mulai = st.date_input("Tanggal Mulai")
        tgl_selesai = st.date_input("Tanggal Selesai")
        
        gambaran_besar = st.text_area("Gambaran Besar Kerja Sama (Untuk Prompt AI)", 
                                      help="Jelaskan secara singkat tujuan dan teknis kerja sama ini agar AI bisa menyusun pasal-pasalnya.")

# --- BAGIAN 2: GENERATE AI ---
if st.button("Generate Draft AI", type="primary"):
    if gambaran_besar and nama_mitra:
        with st.spinner("Gemini sedang menyusun draf PKS..."):
            prompt = f"""
            Buatkan naskah Perjanjian Kerja Sama (PKS) antara {lembaga_p1} Universitas Mulawarman (Pihak Kesatu) dan {nama_mitra} (Pihak Kedua).
            Judul: {judul_ks}.
            Nomor Pihak 1: {no_unit_unmul}. Nomor Pihak 2: {no_mitra}.
            Ditandatangani pada hari {hari}, tanggal {tanggal_teks}.
            
            Pihak Kesatu: {nama_p1}, {jabatan_p1}, {lembaga_p1}, berkedudukan di {alamat_p1}.
            Pihak Kedua: {nama_p2}, {jabatan_p2}, berkedudukan di {alamat_mitra}.
            
            Ruang Lingkup: {ruang_lingkup}.
            Prodi Terlibat dari Unmul: {prodi_terlibat}.
            Gambaran teknis: {gambaran_besar}.
            Masa Berlaku: {tgl_mulai} sampai {tgl_selesai}.
            
            Format dokumen harus memuat:
            - Judul
            - Komparisi (Identitas Pihak 1 dan 2)
            - Pasal 1: Maksud dan Tujuan
            - Pasal 2: Ruang Lingkup Kegiatan
            - Pasal 3: Pelaksanaan Program Kerja Sama (Sebutkan prodi yang terlibat)
            - Pasal 4: Pembiayaan
            - Pasal 5: Jangka Waktu
            - Pasal 6: Penutup
            - Bagian Tanda Tangan (Sertakan NIP {nip_p1} untuk Pihak 1 dan {nip_p2} untuk Pihak 2 jika ada).
            Gunakan bahasa hukum dan tata naskah dinas universitas yang formal dan baku.
            """
            try:
                response = model.generate_content(prompt)
                st.session_state.draft_pks = response.text
                st.success("Draf berhasil di-generate! Silakan periksa dan edit di bawah.")
            except Exception as e:
                st.error(f"Terjadi kesalahan saat generate teks dari API: {e}")
    else:
        st.warning("Mohon isi minimal Nama Mitra dan Gambaran Besar Kerja Sama.")

# --- BAGIAN 3: EDITOR & PENYIMPANAN ---
if st.session_state.draft_pks:
    st.subheader("2. Draft PKS (Editor)")
    edited_draft = st.text_area("Edit Draft di sini:", value=st.session_state.draft_pks, height=500)
    
    col_save, col_pdf = st.columns(2)
    
    with col_save:
        if st.button("Simpan ke Database"):
            conn = get_db_connection()
            if conn:
                try:
                    cur = conn.cursor()
                    insert_query = """
                    INSERT INTO dokumen_pks (judul_ks, nama_mitra, tanggal_dibuat, isi_dokumen)
                    VALUES (%s, %s, %s, %s)
                    """
                    cur.execute(insert_query, (judul_ks, nama_mitra, datetime.now(), edited_draft))
                    conn.commit()
                    cur.close()
                    conn.close()
                    st.success("Draft berhasil disimpan ke Neon DB!")
                except Exception as e:
                    st.error(f"Gagal menyimpan ke database: {e}")
                
    with col_pdf:
        if st.button("Siapkan PDF"):
            try:
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", size=11)
                
                # Encode ke latin-1 untuk menghindari error karakter saat build PDF
                teks_bersih = edited_draft.encode('latin-1', 'replace').decode('latin-1')
                pdf.multi_cell(0, 5, teks_bersih)
                
                file_name = f"PKS_{nama_mitra.replace(' ', '_')}.pdf" if nama_mitra else "PKS_Draft.pdf"
                pdf.output(file_name)
                
                with open(file_name, "rb") as f:
                    st.download_button(
                        label="Unduh File PDF", 
                        data=f, 
                        file_name=file_name,
                        mime="application/pdf",
                        type="primary"
                    )
            except Exception as e:
                st.error(f"Gagal membuat PDF: {e}")
