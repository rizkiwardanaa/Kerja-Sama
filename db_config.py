import psycopg2
import streamlit as st
from psycopg2.errors import DuplicateColumn

def get_db_connection():
    return psycopg2.connect(st.secrets["NEON_CONNECTION_STRING"])

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Tabel PKS (Sudah ada, IF NOT EXISTS akan mengamankan)
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
        
        # 2. Tabel Baru untuk IA (Berelasi dengan PKS lewat pks_id)
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
        
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        st.error(f"Error Konfigurasi DB: {e}")
