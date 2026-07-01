import streamlit as st
import google.generativeai as genai
import psycopg2
from fpdf import FPDF
from datetime import datetime
import json
import os
import tempfile
import pandas as pd

st.set_page_config(page_title="Generator PKS Unmul", layout="wide")

# --- KONFIGURASI SECRETS & AI ---
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except KeyError:
    st.error("API Key Gemini tidak ditemukan di st.secrets.")
    st.stop()

@st.cache_resource
def load_best_gemini_model():
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        priority_models = ['models/gemini-1.5-flash-latest', 'models/gemini-1.5-flash']
        selected = next((m for m in priority_models if m in available_models), available_models[0] if available_models else None)
        return genai.GenerativeModel(selected), selected
    except Exception as e:
        return None, str(e)

model, status_model = load_best_gemini_model()

# --- SETUP DATABASE ---
def get_db_connection():
    return psycopg2.connect(st.secrets["NEON_CONNECTION_STRING"])

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dokumen_pks (
                id SERIAL PRIMARY KEY,
                judul_ks VARCHAR(255),
                nama_mitra VARCHAR(255),
                tanggal_dibuat TIMESTAMP,
                isi_dokumen TEXT
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        st.sidebar.error(f"Error DB Setup: {e}")

init_db()

if 'pasal_json' not in st.session_state:
    st.session_state.pasal_json = {}

# --- SIDEBAR NAVIGASI ---
st.sidebar.title("Navigasi Sistem")
menu = st.sidebar.radio("Pilih Halaman:", ["📝 Buat PKS Baru", "📂 Riwayat Dokumen"])

# =====================================================================
# HALAMAN 1: BUAT PKS BARU
# =====================================================================
if menu == "📝 Buat PKS Baru":
    st.title("Generator Naskah PKS Universitas Mulawarman")

    with st.expander("1. Form Data PKS", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            logo_mitra = st.file_uploader("Unggah Logo Mitra (PNG/JPG)", type=["png", "jpg", "jpeg"])
            judul_ks = st.text_input("Judul Kerja Sama", value="TRIDHARMA PERGURUAN TINGGI")
            no_unit_unmul = st.text_input("Nomor Surat Pihak 1 (Unmul)")
            
            st.markdown("**Waktu Penandatanganan**")
            tgl_teks = st.text_input("Tanggal (Teks)", placeholder="Dua Puluh Dua")
            bln_teks = st.text_input("Bulan (Teks)", placeholder="April")
            thn_teks = st.text_input("Tahun (Teks)", placeholder="Dua Ribu Dua Puluh Enam")
            
            st.subheader("Pihak 1 (Universitas Mulawarman)")
            nama_p1 = st.text_input("Nama Pejabat P1", value="Prof. Dr. M. Bahri Arifin, M.Hum")
            jabatan_p1 = st.text_input("Jabatan P1", value="Dekan Fakultas Ilmu Budaya")
            lembaga_p1 = st.text_input("Nama Lembaga P1", value="Fakultas Ilmu Budaya Universitas Mulawarman")
            alamat_p1 = st.text_area("Alamat Lembaga P1", value="Jl. Ki Hajar Dewantara, Gunung Kelua, Samarinda, Kalimantan Timur 75123")
            nip_p1 = st.text_input("NIP P1")

        with col2:
            no_mitra = st.text_input("Nomor Surat Pihak 2 (Mitra)")
            
            st.subheader("Pihak 2 (Mitra)")
            nama_mitra = st.text_input("Nama Instansi Mitra", value="INSTITUT SENI INDONESIA YOGYAKARTA")
            nama_p2 = st.text_input("Nama Pejabat P2", value="Dr. I Nyoman Cau Arsana, S.Sn., M.Hum")
            jabatan_p2 = st.text_input("Jabatan P2", value="Dekan Fakultas Seni Pertunjukan")
            alamat_mitra = st.text_area("Alamat Mitra", value="Jl. Parangtritis Km. 6.5 Sewon Bantul Yogyakarta")
            nip_p2 = st.text_input("NIP P2")
            
            st.subheader("Detail untuk AI")
            ruang_lingkup = st.text_area("Ruang Lingkup & Gambaran Besar", placeholder="Jelaskan detail prodi yang terlibat, teknis pelaksanaan, dan pembagian dana...")

    teks_pembuka = f"""Pada hari ini, tanggal {tgl_teks} bulan {bln_teks}, tahun {thn_teks} yang bertanda tangan di bawah ini:
1. {nama_p1}: {jabatan_p1} oleh karena itu sah mewakili dan bertindak untuk dan atas nama {lembaga_p1}, Universitas Mulawarman, yang berkedudukan di {alamat_p1}, selanjutnya disebut sebagai PIHAK KESATU.
2. {nama_p2}: {jabatan_p2} oleh karena itu sah mewakili dan bertindak untuk dan atas nama {nama_mitra}, yang berkedudukan di {alamat_mitra}, selanjutnya disebut sebagai PIHAK KEDUA.

PIHAK KESATU dan PIHAK KEDUA selanjutnya disebut PARA PIHAK. Dengan ini sepakat untuk bersama-sama membuat Perjanjian Kerja Sama mengenai {judul_ks} yang dilaksanakan oleh PARA PIHAK seperti diatur dalam pasal sebagai berikut."""

    if st.button("Generate Pasal AI", type="primary"):
        with st.spinner("Gemini sedang memikirkan pasal-pasal..."):
            prompt = f"""
            Anda adalah asisten legal tata naskah. Susun isi pasal-pasal untuk Perjanjian Kerja Sama (PKS).
            Judul: {judul_ks}.
            Konteks: {ruang_lingkup}
            
            TUGAS: Keluarkan output HANYA dalam bentuk format JSON murni (tanpa markdown ```json).
            Gunakan struktur kunci ini:
            {{
                "Pasal 1: Maksud dan Tujuan": "(isi pasal 1 di sini...)",
                "Pasal 2: Ruang Lingkup Kegiatan": "(isi pasal 2 di sini...)",
                "Pasal 3: Pelaksanaan Program": "(isi pasal 3 di sini...)",
                "Pasal 4: Pembiayaan": "(isi pasal 4 di sini...)",
                "Pasal 5: Jangka Waktu": "(isi pasal 5 di sini...)",
                "Pasal 6: Penutup": "(isi pasal 6 di sini...)"
            }}
            """
            try:
                response = model.generate_content(prompt)
                raw_json = response.text.replace('```json', '').replace('```', '').strip()
                st.session_state.pasal_json = json.loads(raw_json)
                st.success("Berhasil! Silakan edit tiap pasal di bawah.")
            except Exception as e:
                st.error(f"Gagal memproses AI. Error: {e}")

    if st.session_state.pasal_json:
        st.markdown("---")
        st.subheader("2. Draft PKS (Editor Terpisah)")
        
        st.info("Bagian Pembuka (Komparisi) otomatis dikunci sesuai tata naskah:")
        st.write(teks_pembuka)
        
        st.markdown("### Edit Pasal-Pasal:")
        edited_pasal = {}
        for judul_pasal, isi_pasal in st.session_state.pasal_json.items():
            edited_pasal[judul_pasal] = st.text_area(judul_pasal, value=isi_pasal, height=150)
        
        full_document = teks_pembuka + "\n\n"
        for jdl, isi in edited_pasal.items():
            full_document += f"{jdl}\n{isi}\n\n"
            
        col_save, col_pdf = st.columns(2)
        
        with col_save:
            if st.button("Simpan ke Database"):
                try:
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO dokumen_pks (judul_ks, nama_mitra, tanggal_dibuat, isi_dokumen) VALUES (%s, %s, %s, %s)",
                        (judul_ks, nama_mitra, datetime.now(), full_document)
                    )
                    conn.commit()
                    cur.close()
                    conn.close()
                    st.success("Tersimpan ke database Neon! Buka tab 'Riwayat Dokumen' untuk melihat.")
                except Exception as e:
                    st.error(f"Database Error: {e}")
                    
        with col_pdf:
            if st.button("Siapkan PDF Cetak"):
                class PDF_PKS(FPDF):
                    def footer(self):
                        self.set_y(-35)
                        self.set_font('Arial', '', 10)
                        
                        # --- GAMBAR TABEL KOTAK PARAF ---
                        start_x = 25
                        col_w = 32
                        row_h = 5
                        
                        # Baris 1: Tulisan Paraf
                        self.set_x(start_x)
                        self.cell(col_w, row_h, 'Paraf', 'LTR', 0, 'C')
                        self.cell(col_w, row_h, 'Paraf', 'LTR', 1, 'C')
                        
                        # Baris 2: Nama Pihak
                        self.set_x(start_x)
                        self.cell(col_w, row_h, 'PIHAK KESATU', 'LBR', 0, 'C')
                        self.cell(col_w, row_h, 'PIHAK KEDUA', 'LBR', 1, 'C')
                        
                        # Baris 3: Kotak Kosong
                        self.set_x(start_x)
                        self.cell(col_w, 10, '', 1, 0, 'C')
                        self.cell(col_w, 10, '', 1, 0, 'C')
                        
                        # Nomor Halaman
                        self.set_y(-25)
                        self.cell(0, 10, f'Halaman {self.page_no()} dari {{nb}}', 0, 0, 'R')

                pdf = PDF_PKS(orientation='P', unit='mm', format='A4')
                pdf.alias_nb_pages()
                pdf.add_page()
                pdf.set_margins(left=25, top=10, right=25)
                
                # --- CETAK KOP LOGO ---
                if os.path.exists("logo_unmul.png"):
                    pdf.image("logo_unmul.png", x=25, y=20, w=30)
                
                if logo_mitra is not None:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                        tmp_file.write(logo_mitra.read())
                        tmp_path = tmp_file.name
                    pdf.image(tmp_path, x=155, y=20, w=30)
                
                # --- CETAK BLOK JUDUL ---
                pdf.set_y(55)
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 6, "PERJANJIAN KERJA SAMA", 0, 1, 'C')
                pdf.cell(0, 6, "ANTARA", 0, 1, 'C')
                pdf.cell(0, 6, lembaga_p1.upper(), 0, 1, 'C')
                pdf.cell(0, 6, "UNIVERSITAS MULAWARMAN", 0, 1, 'C')
                pdf.cell(0, 6, "DENGAN", 0, 1, 'C')
                if nama_mitra:
                    pdf.cell(0, 6, nama_mitra.upper(), 0, 1, 'C')
                
                pdf.ln(5)
                pdf.cell(0, 6, "TENTANG", 0, 1, 'C')
                if judul_ks:
                    pdf.cell(0, 6, judul_ks.upper(), 0, 1, 'C')
                
                pdf.ln(5)
                pdf.set_font("Arial", '', 12)
                pdf.cell(0, 6, f"Nomor : {no_unit_unmul}", 0, 1, 'C')
                pdf.cell(0, 6, f"Nomor : {no_mitra}", 0, 1, 'C')
                pdf.ln(10)
                
                # --- CETAK PEMBUKA DENGAN INDENTASI GANTUNG (HANGING INDENT) ---
                pdf.set_font("Arial", '', 11)
                pdf.multi_cell(0, 6, f"Pada hari ini, tanggal {tgl_teks} bulan {bln_teks}, tahun {thn_teks} yang bertanda tangan di bawah ini:", align='J')
                pdf.ln(3)
                
                # Indentasi Pihak 1
                pdf.set_x(25)
                pdf.cell(7, 6, "1.", 0, 0, 'L')
                pdf.set_x(32)
                teks_p1 = f"{nama_p1}: {jabatan_p1} oleh karena itu sah mewakili dan bertindak untuk dan atas nama {lembaga_p1}, Universitas Mulawarman, yang berkedudukan di {alamat_p1}, selanjutnya disebut sebagai PIHAK KESATU."
                pdf.multi_cell(0, 6, teks_p1, align='J')
                pdf.ln(3)
                
                # Indentasi Pihak 2
                pdf.set_x(25)
                pdf.cell(7, 6, "2.", 0, 0, 'L')
                pdf.set_x(32)
                teks_p2 = f"{nama_p2}: {jabatan_p2} oleh karena itu sah mewakili dan bertindak untuk dan atas nama {nama_mitra}, yang berkedudukan di {alamat_mitra}, selanjutnya disebut sebagai PIHAK KEDUA."
                pdf.multi_cell(0, 6, teks_p2, align='J')
                pdf.ln(3)
                
                # Penutup Pembuka
                pdf.set_x(25)
                teks_penutup = f"PIHAK KESATU dan PIHAK KEDUA selanjutnya disebut PARA PIHAK. Dengan ini sepakat untuk bersama-sama membuat Perjanjian Kerja Sama mengenai {judul_ks} yang dilaksanakan oleh PARA PIHAK seperti diatur dalam pasal sebagai berikut."
                pdf.multi_cell(0, 6, teks_penutup, align='J')
                pdf.ln(5)
                
                # --- CETAK PASAL-PASAL ---
                for jdl, isi in edited_pasal.items():
                    pdf.set_font("Arial", 'B', 11)
                    pdf.multi_cell(0, 6, jdl.upper(), align='C')
                    pdf.set_font("Arial", '', 11)
                    pdf.multi_cell(0, 6, isi.encode('latin-1', 'replace').decode('latin-1'), align='J')
                    pdf.ln(5)
                    
                # --- CETAK TANDA TANGAN (PERBAIKAN NIP) ---
                pdf.ln(10)
                pdf.set_font("Arial", 'B', 11)
                pdf.set_x(25)
                pdf.cell(80, 5, 'PIHAK KESATU,', 0, 0, 'L')
                pdf.cell(80, 5, 'PIHAK KEDUA,', 0, 1, 'L')
                pdf.ln(25)
                
                pdf.set_font("Arial", 'U', 11)
                pdf.set_x(25)
                pdf.cell(80, 5, nama_p1, 0, 0, 'L')
                pdf.cell(80, 5, nama_p2, 0, 1, 'L')
                
                pdf.set_font("Arial", '', 11)
                pdf.set_x(25)
                
                # Menghilangkan titik setelah NIP
                pdf.cell(80, 5, f'NIP {nip_p1}', 0, 0, 'L') 
                if nip_p2:
                    pdf.cell(80, 5, f'NIP {nip_p2}', 0, 1, 'L')
                
                file_name = "Draft_PKS_Cetak.pdf"
                pdf.output(file_name)
                
                with open(file_name, "rb") as f:
                    st.download_button("Unduh PDF", f, file_name, mime="application/pdf", type="primary")

# =====================================================================
# HALAMAN 2: RIWAYAT DOKUMEN
# =====================================================================
elif menu == "📂 Riwayat Dokumen":
    st.title("Database & Riwayat PKS")
    st.write("Akses, tinjau, dan salin draf PKS yang pernah Anda buat sebelumnya.")
    
    try:
        conn = get_db_connection()
        query = "SELECT id, judul_ks, nama_mitra, tanggal_dibuat, isi_dokumen FROM dokumen_pks ORDER BY tanggal_dibuat DESC"
        df = pd.read_sql(query, conn)
        conn.close()
        
        if not df.empty:
            # Mengubah format tanggal agar mudah dibaca
            df['tanggal_dibuat'] = pd.to_datetime(df['tanggal_dibuat']).dt.strftime('%d-%m-%Y %H:%M')
            
            # Pilihan dokumen menggunakan selectbox
            dokumen_pilihan = st.selectbox(
                "Pilih Dokumen:", 
                options=df['id'].tolist(),
                format_func=lambda x: f"{df[df['id']==x]['tanggal_dibuat'].values[0]} | {df[df['id']==x]['nama_mitra'].values[0]} - {df[df['id']==x]['judul_ks'].values[0]}"
            )
            
            # Tampilkan data yang dipilih
            if dokumen_pilihan:
                data_terpilih = df[df['id'] == dokumen_pilihan].iloc[0]
                st.subheader(f"Draf: {data_terpilih['nama_mitra']}")
                
                # Tampilkan di Text Area agar user bisa mencopy/mengedit
                teks_tersimpan = st.text_area("Isi Dokumen (Bisa disalin atau diedit untuk draf baru):", value=data_terpilih['isi_dokumen'], height=600)
                
                st.info("💡 Catatan: Untuk mencetak ulang PDF dengan kop dan layout tabel yang presisi, salin teks ini dan gunakan menu 'Buat PKS Baru'. Database menyimpan data dalam format plain-text.")
        else:
            st.warning("Belum ada dokumen PKS yang tersimpan di database.")
            
    except Exception as e:
        st.error(f"Gagal mengambil data dari database: {e}")
