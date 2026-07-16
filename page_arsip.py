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
import re
from datetime import datetime
from fpdf import FPDF
from db_config import get_db_connection

# Library Google Drive API
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

API_KEY = st.secrets.get("GEMINI_API_KEY", "").strip().strip('"').strip("'")
FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "")

# --- FUNGSI UPLOAD GOOGLE DRIVE ---
def upload_to_drive(file_bytes, file_name):
    """Mengunggah file ke Google Drive menggunakan Service Account dan mengembalikan URL."""
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=['https://www.googleapis.com/auth/drive.file']
        )
        service = build('drive', 'v3', credentials=creds)
        
        file_metadata = {'name': file_name, 'parents': [FOLDER_ID]}
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype='application/pdf', resumable=True)
        
        # Eksekusi unggah file
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        file_id = file.get('id')
        
        # Buka izin agar siapapun yang punya link bisa melihat/mengunduh
        service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        
        return file.get('webViewLink')
    except Exception as e:
        raise Exception(f"Gagal mengunggah ke Google Drive: {str(e)}")

# --- FUNGSI AI GEMINI (Tetap Sama) ---
def get_available_models(api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            valid_models = [m['name'] for m in data.get('models', []) if 'generateContent' in m.get('supportedGenerationMethods', []) and 'gemini' in m['name']]
            valid_models.sort(key=lambda x: ('1.5-flash' in x, '1.5-pro' in x, 'latest' in x), reverse=True)
            return valid_models
        return []
    except Exception:
        return ['models/gemini-1.5-flash-latest']

def panggil_gemini_api(file_bytes, api_key):
    headers = {'Content-Type': 'application/json'}
    b64_file = base64.b64encode(file_bytes).decode('utf-8')
    payload = {
        "contents": [{
            "parts": [
                {
                    "text": """
                    Baca dokumen ini dengan teliti. Ekstrak informasi berikut dan berikan HANYA format JSON murni.
                    {
                        "jenis_dokumen": "Tulis 'PKS' atau 'IA'",
                        "nomor_unmul": "Nomor pihak UNMUL (mengandung 'UN17'). Jika tidak ada tulis 'Tidak Ada'",
                        "nomor_mitra": "Nomor pihak mitra. Jika tidak ada tulis 'Tidak Ada'",
                        "nama_mitra": "Nama instansi mitra spesifik",
                        "tanggal_mulai": "Wajib kalender Indonesia 'DD Bulan YYYY'",
                        "tanggal_selesai": "Wajib kalender Indonesia 'DD Bulan YYYY'. Hitung tahunnya jika hanya disebut durasi. Atau 'Tidak disebutkan'",
                        "prodi": "Program Studi kampus. Atau 'Tidak disebutkan'",
                        "koor_prodi": "Nama pejabat perwakilan Prodi (Khusus IA). Atau 'Tidak disebutkan'"
                    }
                    """
                },
                {"inline_data": {"mime_type": "application/pdf", "data": b64_file}}
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
            if response.status_code == 200: return response.json()
            if response.status_code in [404, 429, 503]:
                last_error_msg = f"Model {model_name} dilewati (Kode {response.status_code})"
                continue 
            if response.status_code == 400: raise Exception(f"Ditolak: {response.text}")
        except requests.exceptions.RequestException:
            last_error_msg = f"Koneksi ke {model_name} terputus."
            continue
    raise Exception(f"Gagal memproses AI. Error terakhir: {last_error_msg}")

def render_arsip():
    st.title("🗄️ Arsip & Ekstraksi Dokumen Otomatis")
    st.write("Sistem ini didukung Google Drive terintegrasi. Dokumen fisik disimpan di awan, server tetap ringan.")

    # --- 1. FITUR UPLOAD MASSAL ---
    uploaded_files = st.file_uploader("Unggah Dokumen (Otomatis masuk Drive)", type=["pdf"], accept_multiple_files=True)
    
    if st.button("Proses & Ekstrak Data", type="primary") and uploaded_files:
        if not API_KEY or not FOLDER_ID:
            st.error("API Key atau Folder ID belum dikonfigurasi di secrets.")
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
                
            with st.status(f"Memproses '{file.name}'...", expanded=False) as status_ui:
                try:
                    # Langkah 1: Ekstrak Teks dengan AI
                    st.write("Menganalisis dokumen dengan AI...")
                    result_json = panggil_gemini_api(file_bytes, API_KEY)
                    res_text = result_json['candidates'][0]['content']['parts'][0]['text']
                    data_ekstrak = json.loads(res_text.replace('```json', '').replace('```', '').strip())
                    
                    # Logika Prodi PKS
                    jenis_dokumen = data_ekstrak.get('jenis_dokumen', 'Tidak disebutkan')
                    tgl_mulai = data_ekstrak.get('tanggal_mulai', 'Tidak disebutkan')
                    prodi = data_ekstrak.get('prodi', 'Tidak disebutkan')
                    
                    if 'PKS' in jenis_dokumen.upper() and prodi.lower() in ['tidak disebutkan', 'tidak ada', '-', 'nan', '']:
                        year_match = re.search(r'\d{4}', tgl_mulai)
                        if year_match:
                            tahun = int(year_match.group(0))
                            if tahun < 2025: prodi = "Sastra Indonesia, Sastra Inggris, Etnomusikologi"
                            elif tahun == 2025: prodi = "Sastra Indonesia, Sastra Inggris, Etnomusikologi, Tari"
                            else: prodi = "Sastra Indonesia, Sastra Inggris, Etnomusikologi, Tari, S2 Kajian Budaya"

                    # Langkah 2: Unggah fisik ke Google Drive
                    st.write("Mengamankan dokumen ke Google Drive...")
                    bersih_mitra = re.sub(r'[^a-zA-Z0-9]', '_', data_ekstrak.get('nama_mitra', 'Mitra'))
                    drive_file_name = f"{jenis_dokumen}_{bersih_mitra}.pdf"
                    drive_url = upload_to_drive(file_bytes, drive_file_name)

                    # Langkah 3: Simpan URL dan Meta Data ke Database Neon (file_pdf dibiarkan NULL untuk hemat ruang)
                    st.write("Menyimpan tautan ke Database...")
                    cur.execute("""
                        INSERT INTO arsip_dokumen 
                        (file_hash, jenis_dokumen, nomor_dokumen, nomor_mitra, nama_mitra, tgl_mulai, tgl_selesai, prodi, koor_prodi, file_url, tanggal_diunggah) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        file_hash, 
                        jenis_dokumen,
                        data_ekstrak.get('nomor_unmul', 'Tidak Ada'),
                        data_ekstrak.get('nomor_mitra', 'Tidak Ada'),
                        data_ekstrak.get('nama_mitra', 'Tidak disebutkan'),
                        tgl_mulai,
                        data_ekstrak.get('tanggal_selesai', 'Tidak disebutkan'),
                        prodi,
                        data_ekstrak.get('koor_prodi', 'Tidak disebutkan'),
                        drive_url, # Simpan Tautan Drive
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
    query_hirarki = """
        SELECT id, jenis_dokumen, nomor_dokumen, nomor_mitra, nama_mitra, prodi, koor_prodi, tgl_mulai, tgl_selesai, file_url 
        FROM arsip_dokumen 
        ORDER BY nama_mitra ASC, 
                 CASE WHEN jenis_dokumen ILIKE '%PKS%' THEN 1 ELSE 2 END ASC, 
                 tanggal_diunggah DESC
    """
    df_arsip = pd.read_sql(query_hirarki, conn)
    df_arsip = df_arsip.fillna("Tidak disebutkan")
    
    if not df_arsip.empty:
        
        # --- FITUR HAPUS MASAL ---
        st.markdown("##### 🗑️ Hapus Dokumen Massal")
        delete_options = { f"{row['jenis_dokumen']} - {row['nama_mitra']} (ID: {row['id']})": row['id'] for _, row in df_arsip.iterrows() }
        selected_to_delete = st.multiselect("Pilih satu atau lebih dokumen untuk dihapus:", options=list(delete_options.keys()))
        
        if selected_to_delete:
            if st.button("Hapus Permanen Dokumen Terpilih", type="primary"):
                ids_to_delete = [delete_options[k] for k in selected_to_delete]
                cur_hapus = conn.cursor()
                format_strings = ','.join(['%s'] * len(ids_to_delete))
                cur_hapus.execute(f"DELETE FROM arsip_dokumen WHERE id IN ({format_strings})", tuple(ids_to_delete))
                conn.commit()
                cur_hapus.close()
                st.success(f"{len(ids_to_delete)} dokumen berhasil dihapus!")
                st.rerun()
                
        st.write("")
        
        # --- TOMBOL UNDUH REKAPITULASI ---
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            if st.button("Unduh PDF"):
                pdf = FPDF(orientation='L', unit='mm', format='A4')
                pdf.add_page()
                pdf.set_font("Arial", 'B', 14)
                pdf.cell(0, 10, "REKAPITULASI ARSIP KERJA SAMA", 0, 1, 'C')
                pdf.ln(5)
                
                pdf.set_font("Arial", 'B', 9)
                pdf.cell(15, 10, "Jenis", 1); pdf.cell(40, 10, "Nomor Unmul", 1); pdf.cell(40, 10, "Nomor Mitra", 1)
                pdf.cell(50, 10, "Mitra", 1); pdf.cell(45, 10, "Program Studi", 1); pdf.cell(45, 10, "Koor. IA", 1)
                pdf.cell(40, 10, "Masa Berlaku", 1); pdf.ln()
                
                pdf.set_font("Arial", '', 8)
                for _, row in df_arsip.iterrows():
                    pdf.cell(15, 8, str(row['jenis_dokumen'])[:10], 1)
                    pdf.cell(40, 8, str(row['nomor_dokumen'])[:25], 1)
                    pdf.cell(40, 8, str(row.get('nomor_mitra', 'Tidak Ada'))[:25], 1)
                    pdf.cell(50, 8, str(row['nama_mitra'])[:35], 1)
                    pdf.cell(45, 8, str(row['prodi'])[:30], 1)
                    pdf.cell(45, 8, str(row['koor_prodi'])[:30], 1)
                    pdf.cell(40, 8, f"{row['tgl_mulai'][:10]} s.d {row['tgl_selesai'][:10]}", 1)
                    pdf.ln()
                    
                pdf.output("Rekap_Arsip.pdf")
                with open("Rekap_Arsip.pdf", "rb") as f:
                    st.download_button("Simpan PDF", f, "Rekap_Arsip.pdf", "application/pdf")
                    
        with col_btn2:
            output_excel = io.BytesIO()
            with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
                # Memastikan URL Drive juga terkespor ke Excel untuk kemudahan akses
                df_export = df_arsip.drop(columns=['id'])
                df_export.columns = ['Jenis Dokumen', 'Nomor UNMUL', 'Nomor Mitra', 'Nama Mitra', 'Program Studi', 'Koor. Prodi', 'Tanggal Mulai', 'Tanggal Selesai', 'Link Berkas']
                df_export.to_excel(writer, index=False, sheet_name='Arsip_Kerja_Sama')
            excel_data = output_excel.getvalue()
            st.download_button(label="Unduh Rekap (Excel)", data=excel_data, file_name="Rekap_Arsip_Kerjasama.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
        st.write("")
        
        # --- TABEL DASHBOARD TAMPILAN UI ---
        h1, h2, h3, h4, h5 = st.columns([1.5, 2.5, 3, 2, 1.5])
        h1.markdown("**Jenis**")
        h2.markdown("**Nomor Dokumen**")
        h3.markdown("**Mitra & Informasi Prodi**")
        h4.markdown("**Masa Berlaku**")
        h5.markdown("**Akses File**")
        st.divider()
        
        prev_mitra = ""
        
        for _, row in df_arsip.iterrows():
            c1, c2, c3, c4, c5 = st.columns([1.5, 2.5, 3, 2, 1.5])
            
            if row['nama_mitra'] == prev_mitra and "IA" in str(row['jenis_dokumen']).upper():
                c1.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp; └── **{row['jenis_dokumen']}**")
            else:
                c1.write(f"**{row['jenis_dokumen']}**")
                
            c2.write(f"**Unmul:** {row['nomor_dokumen']}\n\n**Mitra:** {row.get('nomor_mitra', 'Tidak Ada')}")
            
            detail_mitra = f"**Mitra:** {row['nama_mitra']}\n\n**Prodi:** {row['prodi']}"
            if "IA" in str(row['jenis_dokumen']).upper() and row['koor_prodi'] not in ["Tidak disebutkan", "Bukan IA", "Tidak Ada"]:
                detail_mitra += f"\n\n**Koor. Prodi:** {row['koor_prodi']}"
            c3.markdown(detail_mitra)
            
            c4.write(f"**Mulai:** {row['tgl_mulai']}\n\n**Selesai:** {row['tgl_selesai']}")
            
            with c5:
                # Tombol sekarang berubah menjadi Link yang langsung mengarah ke Google Drive
                link_drive = row.get('file_url', '')
                if link_drive and link_drive != "Tidak disebutkan":
                    st.link_button("🌐 Buka Dokumen", link_drive)
                else:
                    st.info("File lokal lama") # Fallback untuk file lama yang masih pakai BYTEA
                        
            st.divider()
            prev_mitra = row['nama_mitra']
            
    else:
        st.info("Database arsip masih kosong. Silakan unggah dokumen di atas.")
        
    conn.close()
