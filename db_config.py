import psycopg2
import streamlit as st
from psycopg2.errors import DuplicateColumn

def get_db_connection():
    return psycopg2.connect(st.secrets["NEON_CONNECTION_STRING"])

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Tabel PKS (Induk)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dokumen_pks (
                id SERIAL PRIMARY KEY,
                judul_ks VARCHAR(255),
                nama_mitra VARCHAR(255),
                tanggal_dibuat TIMESTAMP,
                isi_dokumen TEXT,
                form_data TEXT
            )
        """)
        
        # 2. Tabel IA (Turunan)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dokumen_ia (
                id SERIAL PRIMARY KEY,
                pks_id INTEGER REFERENCES dokumen_pks(id) ON DELETE CASCADE,
                judul_ia VARCHAR(255),
                tanggal_dibuat TIMESTAMP,
                isi_dokumen TEXT,
                form_data TEXT
            )
        """)
        
        # 3. Tabel Ekstraksi & Arsip PDF
        cur.execute("""
            CREATE TABLE IF NOT EXISTS arsip_dokumen (
                id SERIAL PRIMARY KEY,
                file_hash VARCHAR(255) UNIQUE,
                jenis_dokumen VARCHAR(50),
                nomor_dokumen VARCHAR(255),
                nama_mitra VARCHAR(255),
                tgl_mulai VARCHAR(50),
                tgl_selesai VARCHAR(50),
                file_pdf BYTEA,
                tanggal_diunggah TIMESTAMP
            )
        """)
        
        conn.commit()
        
        # Pengecekan aman untuk penambahan kolom jika update dari versi lama
        try:
            cur.execute("ALTER TABLE dokumen_pks ADD COLUMN form_data TEXT")
            conn.commit()
        except DuplicateColumn:
            conn.rollback()
            
        cur.close()
        conn.close()
    except Exception as e:
        st.error(f"Error Konfigurasi DB: {e}")
