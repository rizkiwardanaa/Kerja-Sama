import streamlit as st
import pandas as pd
import json
import hashlib
import tempfile
import os
import requests
import base64
import psycopg2
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
    
    # PROMPT BARU: Instruksi cerdas untuk membedakan PKS dan IA
    payload = {
        "contents": [{
            "parts": [
                {
                    "text": """
                    Baca dokumen ini. Ekstrak informasi berikut dan berikan HANYA dalam format JSON murni tanpa markdown.
                    Jika data tidak ditemukan, isi dengan "Tidak ada".
                    Gunakan struktur JSON ini:
                    {
                        "jenis_dokumen": "PKS atau IA",
                        "nomor_dokumen": "Nomor surat dokumen tersebut",
                        "nama_mitra": "Nama institusi mitra",
                        "tanggal_mulai": "Tanggal mulai penandatanganan",
                        "tanggal_selesai": "Tanggal berakhirnya kerja sama",
                        "prodi": "Nama Program Studi dari pihak kampus yang terlibat (Berlaku untuk PKS dan IA)",
                        "koor_prodi": "Nama Koordinator Program Studi yang bertanda tangan (KHUSUS untuk IA. Jika dokumen ini PKS, isi dengan 'Bukan IA')"
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
    st.write("Unggah file PDF PKS atau IA. Sistem akan mendeteksi Program Studi dan Pejabat Penandatangan secara otomatis.")

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
                        data_ekstrak.get('jenis_dokumen', '-'),
                        data_ekstrak.get('nomor_dokumen', '-'),
                        data_ekstrak.get('nama_mitra', '-'),
                        data_ekstrak.get('tanggal_mulai', '-'),
                        data_ekstrak.get('tanggal_selesai', '-'),
                        data_ekstrak.get('prodi', '-'),
                        data_ekstrak.get('koor_prodi', '-'),
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

    st.subheader("📋 Database Arsip Kerja Sama")
    
    conn = get_db_connection()
    # Query disesuaikan dengan tambahan 2 kolom baru
    df_arsip = pd.read_sql("SELECT id, jenis_dokumen, nomor_dokumen, nama_mitra, prodi, koor_prodi, tgl_mulai, tgl_selesai FROM arsip_dokumen ORDER BY tanggal_diunggah DESC", conn)
    
    if not df_arsip.empty:
        if st.button("Unduh Rekapitulasi (PDF)"):
            pdf = FPDF(orientation='L', unit='mm', format='A4')
            pdf.add_page()
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 10, "REKAPITULASI ARSIP KERJA SAMA", 0, 1, 'C')
            pdf.ln(5)
            
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(15, 10, "Jenis", 1)
            pdf.cell(50, 10, "Nomor", 1)
            pdf.cell(65, 10, "Mitra", 1)
            pdf.cell(55, 10, "Program Studi", 1)
            pdf.cell(50, 10, "Koordinator IA", 1)
            pdf.cell(40, 10, "Masa Berlaku", 1)
            pdf.ln()
            
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
                st.download_button("Klik untuk Simpan File Rekap", f, "Rekap_Arsip.pdf", "application/pdf")
        
        st.write("")
        
        # --- PERBAIKAN TAMPILAN TABEL ---
        h1, h2, h3, h4, h5 = st.columns([1, 2, 3, 2, 1])
        h1.markdown("**Jenis**")
        h2.markdown("**Nomor**")
        h3.markdown("**Mitra & Informasi Prodi**")
        h4.markdown("**Masa Berlaku**")
        h5.markdown("**Aksi**")
        st.divider()
        
        cur = conn.cursor()
        for _, row in df_arsip.iterrows():
            c1, c2, c3, c4, c5 = st.columns([1, 2, 3, 2, 1])
            c1.write(row['jenis_dokumen'])
            c2.write(row['nomor_dokumen'])
            
            # Menampilkan Mitra, Prodi, dan Koordinator secara dinamis
            detail_mitra = f"**Mitra:** {row['nama_mitra']}\n\n**Prodi:** {row['prodi']}"
            if row['jenis_dokumen'].upper() == "IA" and row['koor_prodi'] and row['koor_prodi'] != "Bukan IA":
                detail_mitra += f"\n\n**Koor. Prodi:** {row['koor_prodi']}"
            c3.markdown(detail_mitra)
            
            c4.write(f"{row['tgl_mulai']} s.d {row['tgl_selesai']}")
            
            # --- PERBAIKAN TOMBOL UNDUH TUNGGAL ---
            with c5:
                cur.execute("SELECT file_pdf FROM arsip_dokumen WHERE id = %s", (row['id'],))
                raw_data = cur.fetchone()[0]
                pdf_data = bytes(raw_data) if raw_data else b""
                
                st.download_button(
                    label="⬇️ Unduh File",
                    data=pdf_data,
                    file_name=f"{row['jenis_dokumen']}_{row['nama_mitra']}.pdf",
                    mime="application/pdf",
                    key=f"dl_real_{row['id']}"
                )
            st.divider()
        cur.close()
    else:
        st.info("Database arsip masih kosong. Silakan unggah dokumen di atas.")
        
    conn.close()
