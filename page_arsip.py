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

# --- MENGAMBIL API KEY DARI SECRETS ---
API_KEY = st.secrets.get("GEMINI_API_KEY", "").strip().strip('"').strip("'")

def get_available_models(api_key):
    """
    Bertanya langsung ke server Google untuk mendapatkan daftar seluruh model
    yang saat ini aktif dan bisa digunakan untuk generateContent.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # Saring hanya model yang mendukung pembuatan konten dan keluarga gemini
            valid_models = [
                m['name'] for m in data.get('models', []) 
                if 'generateContent' in m.get('supportedGenerationMethods', [])
                and 'gemini' in m['name']
            ]
            
            # Urutkan prioritas: 1.5-flash (cepat/murah) -> 1.5-pro (pintar) -> versi 1.0/lainnya
            valid_models.sort(
                key=lambda x: (
                    '1.5-flash' in x,
                    '1.5-pro' in x,
                    'latest' in x
                ), 
                reverse=True
            )
            return valid_models
        return []
    except Exception:
        # Jika gagal mengambil daftar, kembalikan daftar fallback manual yang paling umum
        return [
            'models/gemini-1.5-flash-latest', 
            'models/gemini-1.5-pro-latest', 
            'models/gemini-1.5-flash',
            'models/gemini-pro'
        ]

def panggil_gemini_api(file_bytes, api_key):
    """
    Memanggil API dengan sistem "Pintar".
    Otomatis mencari model yang tersedia dan pindah ke model lain jika kuota habis (429) atau tidak ditemukan (404).
    """
    headers = {'Content-Type': 'application/json'}
    b64_file = base64.b64encode(file_bytes).decode('utf-8')
    
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
                        "tanggal_selesai": "Tanggal berakhirnya kerja sama"
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
    
    # 1. Dapatkan daftar model dinamis
    available_models = get_available_models(api_key)
    if not available_models:
        available_models = ['models/gemini-1.5-flash-latest'] # Jaring pengaman terakhir
        
    last_error_msg = ""
    
    # 2. Coba model satu per satu
    for model_name in available_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={api_key}"
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            
            # Jika berhasil, langsung kembalikan datanya dan hentikan perulangan
            if response.status_code == 200:
                return response.json()
            
            # Jika Error 404 (Tidak Ditemukan), 429 (Limit Kuota), atau 503 (Server Down)
            # Sistem tidak akan crash, melainkan mencatatnya dan pindah ke model berikutnya
            if response.status_code in [404, 429, 503]:
                last_error_msg = f"Model {model_name} dilewati (Kode {response.status_code})"
                continue 
                
            # Jika error 400 (seperti API key invalid atau format data salah), tidak usah loop, langsung error
            if response.status_code == 400:
                raise Exception(f"Permintaan ditolak: {response.text}")
                
        except requests.exceptions.RequestException as e:
            # Mengabaikan error koneksi (seperti timeout) dan coba model lain
            last_error_msg = f"Koneksi ke {model_name} terputus."
            continue
            
    # Jika seluruh loop habis dan tidak ada satu pun model yang berhasil
    raise Exception(f"Semua model API Gemini kehabisan kuota atau gagal diakses. Error terakhir: {last_error_msg}")

def render_arsip():
    st.title("🗄️ Arsip & Ekstraksi Dokumen Otomatis")
    st.write("Unggah file PDF PKS atau IA. Sistem akan membaca isinya, mengekstrak data penting, dan menyimpannya ke database.")

    # --- 1. FITUR UPLOAD MASSAL ---
    uploaded_files = st.file_uploader("Unggah Dokumen (Bisa lebih dari 1 file)", type=["pdf"], accept_multiple_files=True)
    
    if st.button("Proses & Ekstrak Data", type="primary") and uploaded_files:
        if not API_KEY:
            st.error("API Key belum dikonfigurasi di st.secrets.")
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
            
            # Cek apakah file sudah pernah diunggah sebelumnya
            cur.execute("SELECT id FROM arsip_dokumen WHERE file_hash = %s", (file_hash,))
            if cur.fetchone():
                duplikat += 1
                progress_bar.progress((i + 1) / total_files)
                continue
                
            with st.status(f"Mengekstrak data dari '{file.name}'...", expanded=False) as status_ui:
                try:
                    st.write("Mengirim dokumen ke AI Gemini dan mencari model tersedia...")
                    result_json = panggil_gemini_api(file_bytes, API_KEY)
                    
                    st.write("Memproses respons AI...")
                    res_text = result_json['candidates'][0]['content']['parts'][0]['text']
                    
                    # Membersihkan teks dari format markdown JSON
                    clean_json = res_text.replace('```json', '').replace('```', '').strip()
                    data_ekstrak = json.loads(clean_json)
                    
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
                    
                except Exception as e:
                    # Menangkap error jaringan, JSON, atau penolakan API
                    status_ui.update(label=f"Gagal memproses {file.name}", state="error")
                    st.error(f"Gagal mengekstrak '{file.name}'. Detail: {str(e)}")
            
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
        # Fitur Cetak Rekapitulasi PDF
        if st.button("Unduh Rekapitulasi (PDF)"):
            pdf = FPDF(orientation='L', unit='mm', format='A4')
            pdf.add_page()
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 10, "REKAPITULASI ARSIP KERJA SAMA (PKS & IA)", 0, 1, 'C')
            pdf.ln(5)
            
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(20, 10, "Jenis", 1)
            pdf.cell(70, 10, "Nomor Dokumen", 1)
            pdf.cell(100, 10, "Nama Mitra", 1)
            pdf.cell(40, 10, "Mulai", 1)
            pdf.cell(40, 10, "Selesai", 1)
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
        
        # Header Tabel Tampilan UI
        h1, h2, h3, h4, h5 = st.columns([1, 2, 3, 2, 2])
        h1.markdown("**Jenis**")
        h2.markdown("**Nomor**")
        h3.markdown("**Mitra**")
        h4.markdown("**Masa Berlaku**")
        h5.markdown("**File Dokumen**")
        st.divider()
        
        cur = conn.cursor()
        for _, row in df_arsip.iterrows():
            c1, c2, c3, c4, c5 = st.columns([1, 2, 3, 2, 2])
            c1.write(row['jenis_dokumen'])
            c2.write(row['nomor_dokumen'])
            c3.write(row['nama_mitra'])
            c4.write(f"{row['tgl_mulai']} s.d {row['tgl_selesai']}")
            
            with c5:
                # Tombol unduh spesifik untuk dokumen pada baris ini
                if st.download_button(label="⬇️ Unduh PDF", data=b'', file_name="placeholder.pdf", key=f"btn_dl_{row['id']}"): 
                    pass 
                
                # Mengambil data biner dari DB hanya untuk baris ini agar memori tidak berat
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
