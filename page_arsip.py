import streamlit as st
import pandas as pd
import json
import hashlib
import tempfile
import os
import re
import time
import psycopg2
import google.generativeai as genai
from datetime import datetime
from fpdf import FPDF
from db_config import get_db_connection

# --- 1. AUTO-STRIPPING API KEY ---
# Membersihkan API key dari kemungkinan spasi atau tanda kutip tak sengaja di file secrets
RAW_API_KEY = st.secrets.get("GEMINI_API_KEY", "").strip().strip('"').strip("'")
genai.configure(api_key=RAW_API_KEY)

# --- 2. FUNGSI SENSOR ERROR (AUTO-REDACT) ---
def sanitize_error(error_obj):
    """Menyensor API Key dari pesan error mentah agar tidak terekspos di UI"""
    err_str = str(error_obj)
    # Sensor pola URL yang mengandung 'key=...'
    err_str = re.sub(r'key=[a-zA-Z0-9_\.\-]+', 'key=***REDACTED***', err_str)
    # Sensor string API key secara langsung (jika muncul di tempat lain)
    if RAW_API_KEY and len(RAW_API_KEY) > 5:
        err_str = err_str.replace(RAW_API_KEY, "***REDACTED***")
    return err_str

def render_arsip():
    st.title("🗄️ Arsip & Ekstraksi Dokumen Otomatis")
    st.write("Unggah file PDF PKS atau IA. Sistem akan membaca isinya, mengekstrak data penting, dan menyimpannya ke database.")

    # --- 1. FITUR UPLOAD MASSAL ---
    uploaded_files = st.file_uploader("Unggah Dokumen (Bisa lebih dari 1 file)", type=["pdf"], accept_multiple_files=True)
    
    if st.button("Proses & Ekstrak Data", type="primary") and uploaded_files:
        conn = get_db_connection()
        cur = conn.cursor()
        
        progress_bar = st.progress(0)
        total_files = len(uploaded_files)
        berhasil = 0
        duplikat = 0
        
        for i, file in enumerate(uploaded_files):
            file_bytes = file.read()
            file_hash = hashlib.sha256(file_bytes).hexdigest()
            
            cur.execute("SELECT id FROM arsip_dokumen WHERE file_hash = %s", (file_hash,))
            if cur.fetchone():
                duplikat += 1
                progress_bar.progress((i + 1) / total_files)
                continue
                
            with st.status(f"Mengekstrak data dari '{file.name}'...", expanded=False) as status_ui:
                # --- 3. AUTO-RETRY MECHANISM ---
                max_retries = 3
                tmp_path = ""
                gemini_file = None
                
                for attempt in range(max_retries):
                    try:
                        # Buat file sementara
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                            tmp.write(file_bytes)
                            tmp_path = tmp.name
                        
                        st.write(f"Percobaan {attempt + 1}/{max_retries}: Mengunggah ke AI...")
                        gemini_file = genai.upload_file(tmp_path, mime_type="application/pdf")
                        
                        st.write("Menganalisis isi dokumen...")
                        prompt = """
                        Baca dokumen ini. Ekstrak informasi berikut dan berikan HANYA dalam format JSON murni tanpa markdown.
                        Jika data tidak ditemukan, isi dengan "Tidak ada".
                        Gunakan struktur JSON ini:
                        {
                            "jenis_dokumen": "PKS atau IA",
                            "nomor_dokumen": "Nomor surat dokumen tersebut",
                            "nama_mitra": "Nama institusi mitra",
                            "tanggal_mulai": "Tanggal mulai penandatanganan",
                            "tanggal_selesai": "Tanggal berakhirnya kerja sama"
                        }
                        """
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        response = model.generate_content([gemini_file, prompt])
                        
                        raw_json = response.text.replace('```json', '').replace('```', '').strip()
                        data_ekstrak = json.loads(raw_json)
                        
                        st.write("Menyimpan ke database...")
                        cur.execute("""
                            INSERT INTO arsip_dokumen 
                            (file_hash, jenis_dokumen, nomor_dokumen, nama_mitra, tgl_mulai, tgl_selesai, file_pdf, tanggal_diunggah) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            file_hash, 
                            data_ekstrak.get('jenis_dokumen', '-'),
                            data_ekstrak.get('nomor_dokumen', '-'),
                            data_ekstrak.get('nama_mitra', '-'),
                            data_ekstrak.get('tanggal_mulai', '-'),
                            data_ekstrak.get('tanggal_selesai', '-'),
                            psycopg2.Binary(file_bytes),
                            datetime.now()
                        ))
                        conn.commit()
                        berhasil += 1
                        status_ui.update(label=f"Selesai: {file.name}", state="complete")
                        
                        break # Keluar dari loop retry jika berhasil
                        
                    except Exception as e:
                        error_msg = sanitize_error(e)
                        st.write(f"Gagal pada percobaan {attempt + 1}. Detail: {error_msg}")
                        
                        if attempt < max_retries - 1:
                            time.sleep(2) # Jeda 2 detik sebelum mencoba lagi
                        else:
                            status_ui.update(label=f"Gagal memproses {file.name}", state="error")
                            st.error(f"Gagal mengekstrak '{file.name}' setelah {max_retries} percobaan. \n\n**Log Sistem:** {error_msg}")
                            
                    finally:
                        # --- PEMBERSIHAN AMAN (SAFE CLEANUP) ---
                        if gemini_file:
                            try:
                                genai.delete_file(gemini_file.name)
                            except:
                                pass
                        if os.path.exists(tmp_path):
                            try:
                                os.remove(tmp_path)
                            except:
                                pass
            
            progress_bar.progress((i + 1) / total_files)
            
        cur.close()
        conn.close()
        st.success(f"Pemrosesan Selesai! Berhasil masuk: {berhasil} file. Duplikat dilewati: {duplikat} file.")
        
    st.markdown("---")

    # --- 2. DASHBOARD & TABEL REKAPITULASI ---
    st.subheader("📋 Database Arsip Kerja Sama")
    
    conn = get_db_connection()
    df_arsip = pd.read_sql("SELECT id, jenis_dokumen, nomor_dokumen, nama_mitra, tgl_mulai, tgl_selesai FROM arsip_dokumen ORDER BY tanggal_diunggah DESC", conn)
    
    if not df_arsip.empty:
        if st.button("Unduh Rekapitulasi (PDF)"):
            pdf = FPDF(orientation='L', unit='mm', format='A4')
            pdf.add_page()
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 10, "REKAPITULASI ARSIP KERJA SAMA (PKS & IA)", 0, 1, 'C')
            pdf.ln(5)
            
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(20, 10, "Jenis", 1); pdf.cell(70, 10, "Nomor Dokumen", 1); pdf.cell(100, 10, "Nama Mitra", 1); pdf.cell(40, 10, "Mulai", 1); pdf.cell(40, 10, "Selesai", 1)
            pdf.ln()
            
            pdf.set_font("Arial", '', 9)
            for _, row in df_arsip.iterrows():
                pdf.cell(20, 8, str(row['jenis_dokumen'])[:10], 1)
                pdf.cell(70, 8, str(row['nomor_dokumen'])[:35], 1)
                pdf.cell(100, 8, str(row['nama_mitra'])[:55], 1)
                pdf.cell(40, 8, str(row['tgl_mulai'])[:20], 1)
                pdf.cell(40, 8, str(row['tgl_selesai'])[:20], 1)
                pdf.ln()
                
            pdf.output("Rekap_Arsip.pdf")
            with open("Rekap_Arsip.pdf", "rb") as f:
                st.download_button("Klik untuk Simpan File Rekap", f, "Rekap_Arsip.pdf", "application/pdf")
        
        st.write("")
        h1, h2, h3, h4, h5 = st.columns([1, 2, 3, 2, 2])
        h1.markdown("**Jenis**"); h2.markdown("**Nomor**"); h3.markdown("**Mitra**"); h4.markdown("**Masa Berlaku**"); h5.markdown("**File Dokumen**")
        st.divider()
        
        cur = conn.cursor()
        for _, row in df_arsip.iterrows():
            c1, c2, c3, c4, c5 = st.columns([1, 2, 3, 2, 2])
            c1.write(row['jenis_dokumen'])
            c2.write(row['nomor_dokumen'])
            c3.write(row['nama_mitra'])
            c4.write(f"{row['tgl_mulai']} s.d {row['tgl_selesai']}")
            
            with c5:
                if st.download_button(label="⬇️ Unduh PDF", data=b'', file_name="placeholder.pdf", key=f"btn_dl_{row['id']}"): pass 
                cur.execute("SELECT file_pdf FROM arsip_dokumen WHERE id = %s", (row['id'],))
                pdf_data = cur.fetchone()[0]
                c5.empty()
                c5.download_button(
                    label="⬇️ Unduh File",
                    data=pdf_data,
                    file_name=f"{row['jenis_dokumen']}_{row['nama_mitra']}.pdf",
                    mime="application/pdf",
                    key=f"dl_real_{row['id']}"
                )
        cur.close()
    else:
        st.info("Database arsip masih kosong. Silakan unggah dokumen di atas.")
    conn.close()
