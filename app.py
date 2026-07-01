import streamlit as st
import google.generativeai as genai
import psycopg2
from psycopg2.errors import DuplicateColumn
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
        
        try:
            cur.execute("ALTER TABLE dokumen_pks ADD COLUMN form_data TEXT")
            conn.commit()
        except DuplicateColumn:
            conn.rollback()
            
        cur.close()
        conn.close()
    except Exception as e:
        st.sidebar.error(f"Error DB Setup: {e}")

init_db()

# --- STATE MANAGEMENT ---
if 'pasal_json' not in st.session_state:
    st.session_state.pasal_json = {}
if 'edit_id' not in st.session_state:
    st.session_state.edit_id = None
if 'edit_data' not in st.session_state:
    st.session_state.edit_data = {}
if 'menu_selector' not in st.session_state:
    st.session_state.menu_selector = "📝 Buat/Edit PKS"
if 'pdf_ready' not in st.session_state:
    st.session_state.pdf_ready = False

def get_val(key, default):
    return st.session_state.edit_data.get(key, default)

def action_edit(doc_id, form_data_str):
    st.session_state.edit_id = doc_id
    if form_data_str:
        st.session_state.edit_data = json.loads(form_data_str)
        st.session_state.pasal_json = st.session_state.edit_data.get('pasal_json', {})
    else:
        st.session_state.edit_data = {}
        st.session_state.pasal_json = {}
    st.session_state.pdf_ready = False
    st.session_state.menu_selector = "📝 Buat/Edit PKS"

def action_delete(doc_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM dokumen_pks WHERE id = %s", (doc_id,))
        conn.commit()
        cur.close()
        conn.close()
        st.sidebar.success("Dokumen berhasil dihapus!")
    except Exception as e:
        st.sidebar.error(f"Gagal menghapus: {e}")

# --- FUNGSI HELPER TANGGAL ---
def terbilang(angka):
    satuan = ["", "Satu", "Dua", "Tiga", "Empat", "Lima", "Enam", "Tujuh", "Delapan", "Sembilan", "Sepuluh", "Sebelas"]
    if angka < 12: return satuan[angka]
    elif angka < 20: return satuan[angka - 10] + " Belas"
    elif angka < 100: return (satuan[angka // 10] + " Puluh " + satuan[angka % 10]).strip()
    elif angka < 200: return "Seratus " + terbilang(angka - 100).strip()
    elif angka < 1000: return (satuan[angka // 100] + " Ratus " + terbilang(angka % 100)).strip()
    elif angka < 2000: return "Seribu " + terbilang(angka - 1000).strip()
    elif angka < 1000000: return (terbilang(angka // 1000) + " Ribu " + terbilang(angka % 1000)).strip()
    return str(angka)

def get_tanggal_naratif(tgl_obj):
    if not tgl_obj: return ""
    bulan_indo = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    tgl_teks = terbilang(tgl_obj.day)
    bln_teks = bulan_indo[tgl_obj.month]
    thn_teks = terbilang(tgl_obj.year)
    tgl_format = tgl_obj.strftime("%d/%m/%Y")
    return f"tanggal {tgl_teks} bulan {bln_teks}, tahun {thn_teks} ({tgl_format})"

# --- NAVIGATION SIDEBAR ---
st.sidebar.title("Navigasi Sistem")
menu_options = ["📝 Buat/Edit PKS", "📂 Riwayat Dokumen"]
current_idx = menu_options.index(st.session_state.menu_selector)

menu = st.sidebar.radio("Pilih Halaman:", menu_options, index=current_idx)

if menu != st.session_state.menu_selector:
    st.session_state.menu_selector = menu
    st.rerun()

if st.session_state.edit_id and menu == "📝 Buat/Edit PKS":
    st.sidebar.warning("Sedang dalam mode Edit Dokumen.")
    if st.sidebar.button("Batal Edit / Buat Baru"):
        st.session_state.edit_id = None
        st.session_state.edit_data = {}
        st.session_state.pasal_json = {}
        st.session_state.pdf_ready = False
        st.rerun()

# =====================================================================
# HALAMAN 1: BUAT / EDIT PKS
# =====================================================================
if menu == "📝 Buat/Edit PKS":
    st.title("Generator Naskah PKS Universitas Mulawarman")

    with st.form("main_pks_form"):
        with st.expander("1. Form Data PKS", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                logo_mitra = st.file_uploader("Unggah Logo Mitra (Harus diunggah ulang jika edit)", type=["png", "jpg", "jpeg"])
                judul_ks = st.text_input("Judul Kerja Sama", value=get_val('judul_ks', "TRIDHARMA PERGURUAN TINGGI"))
                no_unit_unmul = st.text_input("Nomor Surat Pihak 1 (Unmul)", value=get_val('no_unit_unmul', ""))
                
                st.markdown("**Waktu Penandatanganan**")
                default_tgl_str = get_val('tgl_ttd', datetime.now().strftime("%Y-%m-%d"))
                default_tgl_obj = datetime.strptime(default_tgl_str, "%Y-%m-%d").date()
                tgl_ttd = st.date_input("Pilih Tanggal Penandatanganan", value=default_tgl_obj)
                
                st.subheader("Pihak 1 (Universitas Mulawarman)")
                nama_p1 = st.text_input("Nama Pejabat P1", value=get_val('nama_p1', "Prof. Dr. M. Bahri Arifin, M.Hum"))
                jabatan_p1 = st.text_input("Jabatan P1", value=get_val('jabatan_p1', "Dekan Fakultas Ilmu Budaya"))
                lembaga_p1 = st.text_input("Nama Lembaga P1", value=get_val('lembaga_p1', "Fakultas Ilmu Budaya Universitas Mulawarman"))
                alamat_p1 = st.text_area("Alamat Lembaga P1", value=get_val('alamat_p1', "Jl. Ki Hajar Dewantara, Gunung Kelua, Samarinda, Kalimantan Timur 75123"))
                nip_p1 = st.text_input("NIP P1", value=get_val('nip_p1', ""))

            with col2:
                no_mitra = st.text_input("Nomor Surat Pihak 2 (Mitra)", value=get_val('no_mitra', ""))
                
                st.subheader("Pihak 2 (Mitra)")
                nama_mitra = st.text_input("Nama Instansi Mitra", value=get_val('nama_mitra', "INSTITUT SENI INDONESIA YOGYAKARTA"))
                nama_p2 = st.text_input("Nama Pejabat P2", value=get_val('nama_p2', "Dr. I Nyoman Cau Arsana, S.Sn., M.Hum"))
                jabatan_p2 = st.text_input("Jabatan P2", value=get_val('jabatan_p2', "Dekan Fakultas Seni Pertunjukan"))
                alamat_mitra = st.text_area("Alamat Mitra", value=get_val('alamat_mitra', "Jl. Parangtritis Km. 6.5 Sewon Bantul Yogyakarta"))
                nip_p2 = st.text_input("NIP P2", value=get_val('nip_p2', ""))
                
                st.subheader("Detail untuk AI")
                tgl_berakhir = st.date_input("Pilih Tanggal Penandatanganan", value=default_tgl_obj)
                ruang_lingkup = st.text_area("Ruang Lingkup & Gambaran Besar", value=get_val('ruang_lingkup', ""), placeholder="Jelaskan detail prodi yang terlibat, teknis pelaksanaan, dan pembagian dana...")

        narasi_tanggal = get_tanggal_naratif(tgl_ttd)
        teks_pembuka = f"""Pada hari ini, {narasi_tanggal} yang bertanda tangan di bawah ini:
1. {nama_p1}: {jabatan_p1} oleh karena itu sah mewakili dan bertindak untuk dan atas nama {lembaga_p1}, Universitas Mulawarman, yang berkedudukan di {alamat_p1}, selanjutnya disebut sebagai PIHAK KESATU.
2. {nama_p2}: {jabatan_p2} oleh karena itu sah mewakili dan bertindak untuk dan atas nama {nama_mitra}, yang berkedudukan di {alamat_mitra}, selanjutnya disebut sebagai PIHAK KEDUA.

PIHAK KESATU dan PIHAK KEDUA selanjutnya disebut PARA PIHAK. Dengan ini sepakat untuk bersama-sama membuat Perjanjian Kerja Sama mengenai {judul_ks} yang dilaksanakan oleh PARA PIHAK seperti diatur dalam pasal sebagai berikut."""

        btn_generate = st.form_submit_button("Generate Pasal AI", type="primary")
        
        edited_pasal = {}
        btn_save = False
        btn_pdf = False
        
        if st.session_state.pasal_json:
            st.markdown("---")
            st.subheader("2. Draft PKS (Editor Terpisah)")
            st.info("Bagian Pembuka (Komparisi) otomatis dikunci sesuai tata naskah:")
            st.write(teks_pembuka)
            
            st.markdown("### Edit Pasal-Pasal:")
            for judul_pasal, isi_pasal in st.session_state.pasal_json.items():
                edited_pasal[judul_pasal] = st.text_area(judul_pasal, value=isi_pasal, height=150)
            
            col_save, col_pdf_btn = st.columns(2)
            with col_save:
                btn_label = "Update Database" if st.session_state.edit_id else "Simpan ke Database"
                btn_save = st.form_submit_button(btn_label)
            with col_pdf_btn:
                btn_pdf = st.form_submit_button("Siapkan PDF Cetak")

    # =====================================================================
    # LOGIKA PEMROSESAN
    # =====================================================================
    if btn_generate or btn_save or btn_pdf:
        if edited_pasal:
            st.session_state.pasal_json = edited_pasal
            
        st.session_state.edit_data = {
            'judul_ks': judul_ks, 'no_unit_unmul': no_unit_unmul, 'tgl_ttd': tgl_ttd.strftime("%Y-%m-%d"),
            'nama_p1': nama_p1, 'jabatan_p1': jabatan_p1, 'lembaga_p1': lembaga_p1, 'alamat_p1': alamat_p1,
            'nip_p1': nip_p1, 'no_mitra': no_mitra, 'nama_mitra': nama_mitra,
            'nama_p2': nama_p2, 'jabatan_p2': jabatan_p2, 'alamat_mitra': alamat_mitra,
            'nip_p2': nip_p2, 'tgl_berakhir': tgl_berakhir, 'ruang_lingkup': ruang_lingkup, 
            'pasal_json': edited_pasal if edited_pasal else {}
        }
    
    if btn_generate:
        with st.spinner("Gemini sedang memikirkan pasal-pasal..."):
            prompt = f"""
            Anda adalah asisten legal tata naskah. Susun isi pasal-pasal untuk Perjanjian Kerja Sama (PKS).
            Judul: {judul_ks}.
            Konteks/Ruang Lingkup: {ruang_lingkup}
            Tanggal Berakhir Kerja Sama: {tgl_berakhir}
            
            TUGAS: Keluarkan output HANYA dalam bentuk format JSON murni.
            Gunakan struktur kunci ini:
            {{
                "Pasal 1: Maksud dan Tujuan": "(isi...)",
                "Pasal 2: Ruang Lingkup Kegiatan": "(isi...)",
                "Pasal 3: Pelaksanaan Program": "(isi...)",
                "Pasal 4: Pembiayaan": "(isi...)",
                "Pasal 5: Jangka Waktu": "(Sebutkan durasi kerja sama dan sebutkan tanggal berakhirnya {tgl_berakhir}...)",
                "Pasal 6: Penutup": "(isi...)"
            }}
            """
            try:
                response = model.generate_content(prompt)
                raw_json = response.text.replace('```json', '').replace('```', '').strip()
                st.session_state.pasal_json = json.loads(raw_json)
                st.session_state.pdf_ready = False
                st.rerun() 
            except Exception as e:
                st.error(f"Gagal memproses AI. Error: {e}")

    if btn_save:
        try:
            full_document = teks_pembuka + "\n\n"
            for jdl, isi in st.session_state.pasal_json.items():
                full_document += f"{jdl}\n{isi}\n\n"
                
            form_data_str = json.dumps(st.session_state.edit_data)
            conn = get_db_connection()
            cur = conn.cursor()
            
            if st.session_state.edit_id:
                cur.execute(
                    "UPDATE dokumen_pks SET judul_ks=%s, nama_mitra=%s, tanggal_dibuat=%s, isi_dokumen=%s, form_data=%s WHERE id=%s",
                    (judul_ks, nama_mitra, datetime.now(), full_document, form_data_str, st.session_state.edit_id)
                )
                st.success("Dokumen berhasil diperbarui!")
            else:
                cur.execute(
                    "INSERT INTO dokumen_pks (judul_ks, nama_mitra, tanggal_dibuat, isi_dokumen, form_data) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (judul_ks, nama_mitra, datetime.now(), full_document, form_data_str)
                )
                st.session_state.edit_id = cur.fetchone()[0]
                st.success("Dokumen baru berhasil disimpan!")
                
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            st.error(f"Database Error: {e}")

    if btn_pdf:
        try:
            class PDF_PKS(FPDF):
                def footer(self):
                    self.set_y(-35)
                    self.set_font('Arial', '', 10)
                    
                    start_x = 25
                    col_w = 32
                    row_h = 5
                    
                    self.set_x(start_x)
                    self.cell(col_w, row_h, 'Paraf', 'LTR', 0, 'C')
                    self.cell(col_w, row_h, 'Paraf', 'LTR', 1, 'C')
                    
                    self.set_x(start_x)
                    self.cell(col_w, row_h, 'PIHAK KESATU', 'LBR', 0, 'C')
                    self.cell(col_w, row_h, 'PIHAK KEDUA', 'LBR', 1, 'C')
                    
                    self.set_x(start_x)
                    self.cell(col_w, 10, '', 1, 0, 'C')
                    self.cell(col_w, 10, '', 1, 1, 'C')
                    
                    self.set_y(-25)
                    self.cell(0, 10, f'Halaman {self.page_no()} dari {{nb}}', 0, 0, 'R')

            pdf = PDF_PKS(orientation='P', unit='mm', format='A4')
            pdf.alias_nb_pages()
            pdf.add_page()
            
            pdf.set_auto_page_break(auto=True, margin=45) 
            pdf.set_margins(left=25, top=20, right=25)
            
            if os.path.exists("logo_unmul.png"):
                pdf.image("logo_unmul.png", x=25, y=20, w=30)
            
            if logo_mitra is not None:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                    tmp_file.write(logo_mitra.read())
                    tmp_path = tmp_file.name
                pdf.image(tmp_path, x=155, y=20, w=30)
            
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
            
            # --- CETAK PEMBUKA (Dikembalikan rata kiri biasa tanpa indentasi) ---
            pdf.set_font("Arial", '', 11)
            pdf.multi_cell(0, 6, teks_pembuka.encode('latin-1', 'replace').decode('latin-1'), align='J')
            pdf.ln(5)
            
            # --- CETAK PASAL-PASAL ---
            for jdl, isi in st.session_state.pasal_json.items():
                pdf.set_font("Arial", 'B', 11)
                
                if ":" in jdl:
                    pasal_num, pasal_title = jdl.split(":", 1)
                    pdf.multi_cell(0, 6, pasal_num.strip().upper(), align='C')
                    pdf.multi_cell(0, 6, pasal_title.strip().upper(), align='C')
                else:
                    pdf.multi_cell(0, 6, jdl.upper(), align='C')
                
                pdf.set_font("Arial", '', 11)
                pdf.multi_cell(0, 6, isi.encode('latin-1', 'replace').decode('latin-1'), align='J')
                pdf.ln(5)
                
            # --- CETAK TANDA TANGAN ---
            pdf.ln(10)
            pdf.set_font("Arial", 'B', 11)
            pdf.set_x(25)
            pdf.cell(80, 5, 'PIHAK KESATU,', 0, 0, 'L')
            pdf.cell(80, 5, 'PIHAK KEDUA,', 0, 1, 'L')
            pdf.ln(25)
            
            pdf.set_font("Arial", '', 11) 
            pdf.set_x(25)
            pdf.cell(80, 5, nama_p1, 0, 0, 'L')
            pdf.cell(80, 5, nama_p2, 0, 1, 'L')
            
            pdf.set_font("Arial", 'B', 11) 
            pdf.set_x(25)
            pdf.cell(80, 5, f'NIP {nip_p1}', 0, 0, 'L') 
            if nip_p2:
                pdf.cell(80, 5, f'NIP {nip_p2}', 0, 1, 'L')
            
            file_name = "Draft_PKS_Cetak.pdf"
            pdf.output(file_name)
            
            st.session_state.pdf_ready = True
            
        except Exception as e:
            st.error(f"Gagal menyiapkan PDF: {e}")

    if st.session_state.pdf_ready:
        if os.path.exists("Draft_PKS_Cetak.pdf"):
            with open("Draft_PKS_Cetak.pdf", "rb") as f:
                st.download_button("Unduh File PDF Anda", f, "Draft_PKS_Cetak.pdf", mime="application/pdf", type="primary")

# =====================================================================
# HALAMAN 2: RIWAYAT DOKUMEN (TABEL LISTING)
# =====================================================================
elif menu == "📂 Riwayat Dokumen":
    st.title("Riwayat Dokumen PKS")
    st.write("Daftar naskah yang telah disimpan. Klik Edit untuk mengubah dan mengunduh ulang PDF.")
    
    try:
        conn = get_db_connection()
        query = "SELECT id, judul_ks, nama_mitra, tanggal_dibuat, form_data FROM dokumen_pks ORDER BY tanggal_dibuat DESC"
        cur = conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        if rows:
            head_col1, head_col2, head_col3, head_col4 = st.columns([2, 3, 3, 2])
            head_col1.markdown("**Tanggal**")
            head_col2.markdown("**Mitra**")
            head_col3.markdown("**Judul**")
            head_col4.markdown("**Aksi**")
            st.divider()
            
            for row in rows:
                doc_id, jdl, mitra, tgl, form_data = row
                
                col1, col2, col3, col_edit, col_del = st.columns([2, 3, 3, 1, 1])
                col1.write(tgl.strftime('%d-%m-%Y %H:%M'))
                col2.write(mitra)
                col3.write(jdl)
                
                if col_edit.button("✏️ Edit", key=f"edit_{doc_id}"):
                    action_edit(doc_id, form_data)
                    
                if col_del.button("🗑️ Hapus", key=f"del_{doc_id}"):
                    action_delete(doc_id)
                    st.rerun()
                    
            st.divider()
        else:
            st.warning("Belum ada dokumen PKS yang tersimpan di database.")
            
    except Exception as e:
        st.error(f"Gagal mengambil data dari database: {e}")
