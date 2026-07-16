import psycopg2
import streamlit as st

def get_db_connection():
    return psycopg2.connect(st.secrets["NEON_CONNECTION_STRING"])

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # ... (Tabel PKS dan IA biarkan sama seperti sebelumnya) ...
        
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
        
        # --- MIGRASI DATA OTOMATIS ---
        alter_queries = [
            "ALTER TABLE arsip_dokumen ADD COLUMN prodi VARCHAR(255)",
            "ALTER TABLE arsip_dokumen ADD COLUMN koor_prodi VARCHAR(255)",
            "ALTER TABLE arsip_dokumen ADD COLUMN nomor_mitra VARCHAR(255)",
            "ALTER TABLE arsip_dokumen ADD COLUMN file_url VARCHAR(500)" # Kolom baru untuk Link Drive
        ]
        
        for query in alter_queries:
            try:
                cur.execute(query)
                conn.commit()
            except Exception:
                conn.rollback() 
                
        cur.close()
        conn.close()
    except Exception as e:
        st.error(f"Error Konfigurasi DB: {e}")
