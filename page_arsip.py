import streamlit as st
import pandas as pd
import json
import hashlib
import tempfile
import os
import requests
import base64
import psycopg2
import io
from datetime import datetime
from fpdf import FPDF
from db_config import get_db_connection

API_KEY = st.secrets.get("GEMINI_API_KEY", "").strip().strip('"').strip("'")

def get_available_models(api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            valid_models = [
                m['name'] for m in data.get('models', []) 
                if 'generateContent' in m.get('supportedGenerationMethods', [])
                and 'gemini' in m['name']
            ]
            valid_models.sort(
                key=lambda x: ('1.5-flash' in x, '1.5-pro' in x, 'latest' in x), 
                reverse=True
            )
            return valid_models
        return []
    except Exception:
        return ['models/gemini-1.5-flash-latest']

def panggil_gemini_api(file_bytes, api_key):
    headers = {'Content-Type': 'application/json'}
    b64_file = base64.b64encode(file_bytes).decode('utf-8')
    
    # PROMPT DIPERBARUI: Instruksi ketat untuk Tanggal Indonesia, Prodi, dan Koordinator
    payload = {
        "contents": [{
            "parts": [
                {
                    "text": """
                    Baca dokumen ini dengan sangat teliti. Ekstrak informasi berikut dan berikan HANYA dalam format JSON murni.
                    Gunakan pedoman struktur JSON ini secara ketat:
                    {
                        "jenis_dokumen": "Tulis 'PKS' atau 'IA'",
                        "nomor_dokumen": "Tuliskan nomor dokumen secara lengkap",
                        "nama_mitra": "Tuliskan nama instansi mitra secara spesifik (misal: SDN 020 TANJUNG REDEB KABUPATEN BERAU)",
                        "tanggal_mulai": "Ekstrak tanggal penandatanganan dan WAJIB format ke kalender Indonesia 'DD Bulan YYYY' (Contoh: 30 April 2026).",
                        "tanggal_selesai": "Ekstrak tanggal berakhir dan WAJIB format ke kalender Indonesia 'DD Bulan YYYY' (Contoh: 30 April 2026). Jika tidak disebutkan, tulis 'Tidak disebutkan'",
                        "prodi": "Cari teks yang menyebutkan Program Studi pihak kampus (contoh: Program Studi S2 Kajian Budaya). Jika tidak ditemukan, tulis 'Tidak disebutkan'",
                        "koor_prodi": "Cari nama pejabat yang mewakili Prodi tersebut, biasanya setelah kata 'diwakili' atau 'selaku Koordinator' (contoh: Alamsyah). Jika tidak ada, tulis 'Tidak disebutkan'"
                    }
                    """
                },
                {
                    "inline_data": {
                        "mime_type": "application/pdf", 
                        "data": b64_file
                    }
                }
            ]
        }]
    }
    
    available_models = get_available_models(api_key)
    if not available_models: available_models = ['models/gemini-1.5-flash-latest']
        
    last_error_msg = ""
    for model_name in available_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={api_key}"
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                return response.json()
            if response.status_code in [404, 429, 503]:
                last_error_msg = f"Model {model_name} dilewati (Kode {response.status_code})"
                continue 
            if response.status_code == 400:
                raise Exception(f"Permintaan ditolak: {response.text}")
        except requests.exceptions.RequestException as e:
            last_error_msg = f"Koneksi ke {model_name} terputus."
            continue
            
    raise Exception(f"Gagal memproses AI. Error terakhir: {last_error_msg}")


def render_arsip():
    st.title("🗄️ Arsip & Ekstraksi Dokumen Otomatis")
    st.write("Unggah file PDF PKS atau IA. Sistem akan mendeteksi Program Studi, Pejabat, dan memformat tanggal secara otomatis.")

    # --- 1. FITUR UPLOAD MASSAL ---
    uploaded_files = st.file_uploader("Unggah Dokumen (Bisa lebih dari 1 file)", type=["pdf"], accept_multiple_files=True)
    
    if st.button("Proses & Ekstrak Data", type="primary") and uploaded_files:
        if not API_KEY:
            st.error("API Key belum dikonfigurasi.")
            st.stop()
            
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
                try:
                    result_json = panggil_gemini_api(file_bytes, API_KEY)
                    res_text = result_json['candidates'][0]['content']['parts'][0]['text']
                    clean_json = res_text.replace('```json', '').replace('```', '').strip()
                    data_ekstrak = json.loads(clean_json)
                    
                    cur.execute("""
                        INSERT INTO arsip_dokumen 
                        (file_hash, jenis_dokumen, nomor_dokumen, nama_mitra, tgl_mulai, tgl_selesai, prodi, koor_prodi, file_pdf, tanggal_diunggah) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        file_hash, 
                        data_ekstrak.get('jenis_dokumen', 'Tidak disebutkan'),
                        data_ekstrak.get('nomor_dokumen', 'Tidak disebutkan'),
                        data_ekstrak.get('nama_mitra', 'Tidak disebutkan'),
                        data_ekstrak.get('tanggal_mulai', 'Tidak disebutkan'),
                        data_ekstrak.get('tanggal_selesai', 'Tidak disebutkan'),
                        data_ekstrak.get('prodi', 'Tidak disebutkan'),
                        data_ekstrak.get('koor_prodi', 'Tidak disebutkan'),
                        psycopg2.Binary(file_bytes),
                        datetime.now()
                    ))
                    conn.commit()
                    berhasil += 1
                    status_ui.update(label=f"Selesai: {file.name}", state="complete")
                except Exception as e:
                    status_ui.update(label=f"Gagal memproses {file.name}", state="error")
                    st.error(f"Error: {str(e)}")
            
            progress_bar.progress((i + 1) / total_files)
            
        cur.close()
        conn.close()
        st.success(f"Pemrosesan Selesai! Berhasil: {berhasil} file. Duplikat: {duplikat} file.")
        
    st.markdown("---")

    # --- 2. DASHBOARD & TABEL HIRARKI ---
    st.subheader("📋 Database Arsip Kerja Sama (Hirarki)")
    
    conn = get_db_connection()
    # Logika SQL Hirarki: Mengelompokkan berdasarkan Nama Mitra, lalu PKS diprioritaskan di atas IA
    query_hirarki = """
        SELECT id, jenis_dokumen, nomor_dokumen, nama_mitra, prodi, koor_prodi, tgl_mulai, tgl_selesai 
        FROM arsip_dokumen 
        ORDER BY nama_mitra ASC, 
                 CASE WHEN jenis_dokumen ILIKE '%PKS%' THEN 1 ELSE 2 END ASC, 
                 tanggal_diunggah DESC
    """
    df_arsip = pd.read_sql(query_hirarki, conn)
    # Membersihkan NaN dari Pandas menjadi teks ramah pengguna
    df_arsip = df_arsip.fillna("Tidak disebutkan")
    
    if not df_arsip.empty:
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            if st.button("Unduh PDF"):
                pdf = FPDF(orientation='L', unit='mm', format='A4')
                pdf.add_page()
                pdf.set_font("Arial", 'B', 14)
                pdf.cell(0, 10, "REKAPITULASI ARSIP KERJA SAMA", 0, 1, 'C')
                pdf.ln(5)
                
                pdf.set_font("Arial", 'B', 9)
                pdf.cell(15, 10, "Jenis", 1); pdf.cell(50, 10, "Nomor", 1); pdf.cell(65, 10, "Mitra", 1); pdf.cell(55, 10, "Program Studi", 1); pdf.cell(50, 10, "Koordinator IA", 1); pdf.cell(40, 10, "Masa Berlaku", 1); pdf.ln()
                
                pdf.set_font("Arial", '', 8)
                for _, row in df_arsip.iterrows():
                    pdf.cell(15, 8, str(row['jenis_dokumen'])[:10], 1)
                    pdf.cell(50, 8, str(row['nomor_dokumen'])[:35], 1)
                    pdf.cell(65, 8, str(row['nama_mitra'])[:40], 1)
                    pdf.cell(55, 8, str(row['prodi'])[:35], 1)
                    pdf.cell(50, 8, str(row['koor_prodi'])[:30], 1)
                    pdf.cell(40, 8, f"{row['tgl_mulai'][:10]} s/d {row['tgl_selesai'][:10]}", 1)
                    pdf.ln()
                    
                pdf.output("Rekap_Arsip.pdf")
                with open("Rekap_Arsip.pdf", "rb") as f:
                    st.download_button("Simpan PDF", f, "Rekap_Arsip.pdf", "application/pdf")
                    
        with col_btn2:
            # --- FITUR UNDUH EXCEL ---
            output_excel = io.BytesIO()
            with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
                df_export = df_arsip.drop(columns=['id'])
                df_export.columns = ['Jenis Dokumen', 'Nomor Dokumen', 'Nama Mitra', 'Program Studi', 'Koor. Prodi', 'Tanggal Mulai', 'Tanggal Selesai']
                df_export.to_excel(writer, index=False, sheet_name='Arsip_Kerja_Sama')
            excel_data = output_excel.getvalue()
            st.download_button(label="Unduh Rekap (Excel)", data=excel_data, file_name="Rekap_Arsip.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
        st.write("")
        
        # Header Tabel
        h1, h2, h3, h4, h5 = st.columns([1.5, 2, 3, 2, 1.5])
        h1.markdown("**Jenis**")
        h2.markdown("**Nomor**")
        h3.markdown("**Mitra & Informasi Prodi**")
        h4.markdown("**Masa Berlaku**")
        h5.markdown("**Aksi**")
        st.divider()
        
        cur = conn.cursor()
        
        # Logika visual hirarki (indentasi jika nama mitra sama)
        prev_mitra = ""
        
        for _, row in df_arsip.iterrows():
            c1, c2, c3, c4, c5 = st.columns([1.5, 2, 3, 2, 1.5])
            
            # Indentasi Visual untuk IA yang merupakan anak dari PKS di atasnya
            if row['nama_mitra'] == prev_mitra and "IA" in str(row['jenis_dokumen']).upper():
                c1.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp; └── **{row['jenis_dokumen']}**")
            else:
                c1.write(f"**{row['jenis_dokumen']}**")
                
            c2.write(row['nomor_dokumen'])
            
            # Tampilan Informasi Mitra & Prodi
            detail_mitra = f"**Mitra:** {row['nama_mitra']}\n\n**Prodi:** {row['prodi']}"
            if "IA" in str(row['jenis_dokumen']).upper() and row['koor_prodi'] != "Tidak disebutkan":
                detail_mitra += f"\n\n**Koor. Prodi:** {row['koor_prodi']}"
            c3.markdown(detail_mitra)
            
            # Tampilan Tanggal Format Indonesia
            c4.write(f"{row['tgl_mulai']}\ns.d\n{row['tgl_selesai']}")
            
            with c5:
                # Mengambil file PDF biner untuk baris ini
                cur.execute("SELECT file_pdf FROM arsip_dokumen WHERE id = %s", (row['id'],))
                raw_data = cur.fetchone()[0]
                pdf_data = bytes(raw_data) if raw_data else b""
                
                # Tombol Unduh Spesifik
                st.download_button(
                    label="⬇️ Unduh File",
                    data=pdf_data,
                    file_name=f"{row['jenis_dokumen']}_{row['nama_mitra'][:15]}.pdf",
                    mime="application/pdf",
                    key=f"dl_real_{row['id']}"
                )
                
                # --- FITUR HAPUS DENGAN KONFIRMASI ---
                hapus_cek = st.checkbox("Hapus Data?", key=f"cek_hapus_{row['id']}")
                if hapus_cek:
                    if st.button("🗑️ Konfirmasi", key=f"btn_hapus_{row['id']}", type="primary"):
                        cur_hapus = conn.cursor()
                        cur_hapus.execute("DELETE FROM arsip_dokumen WHERE id = %s", (row['id'],))
                        conn.commit()
                        cur_hapus.close()
                        st.rerun()
                        
            st.divider()
            prev_mitra = row['nama_mitra']
            
        cur.close()
    else:
        st.info("Database arsip masih kosong. Silakan unggah dokumen di atas.")
        
    conn.close()
