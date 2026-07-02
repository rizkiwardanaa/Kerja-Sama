import streamlit as st
import pandas as pd
import json
from db_config import get_db_connection

def render_riwayat():
    st.title("Database & Riwayat Dokumen")
    
    tab_pks, tab_ia = st.tabs(["Riwayat PKS (Induk)", "Riwayat IA (Turunan)"])
    
    # --- TAB PKS ---
    with tab_pks:
        st.subheader("Daftar Naskah PKS")
        try:
            conn = get_db_connection()
            df = pd.read_sql("SELECT id, judul_ks, nama_mitra, tanggal_dibuat, form_data FROM dokumen_pks ORDER BY tanggal_dibuat DESC", conn)
            
            if not df.empty:
                c1, c2, c3, c4 = st.columns([2, 3, 3, 2])
                c1.markdown("**Tanggal**"); c2.markdown("**Mitra**"); c3.markdown("**Judul**"); c4.markdown("**Aksi**")
                st.divider()
                
                for _, row in df.iterrows():
                    c1, c2, c3, ce, cd = st.columns([2, 3, 3, 1, 1])
                    c1.write(row['tanggal_dibuat'].strftime('%d-%m-%Y %H:%M'))
                    c2.write(row['nama_mitra'])
                    c3.write(row['judul_ks'])
                    
                    if ce.button("✏️", key=f"edit_pks_{row['id']}"):
                        st.session_state.pks_edit_id = row['id']
                        st.session_state.pks_edit_data = json.loads(row['form_data'])
                        st.session_state.pks_json = st.session_state.pks_edit_data.get('pasal_json', {})
                        st.session_state.menu_aktif = "📝 Modul PKS (Induk)"
                        st.rerun()
                        
                    if cd.button("🗑️", key=f"del_pks_{row['id']}"):
                        cur = conn.cursor()
                        cur.execute("DELETE FROM dokumen_pks WHERE id = %s", (row['id'],))
                        conn.commit(); cur.close()
                        st.rerun()
                st.divider()
            else: st.info("Belum ada data PKS.")
        except Exception as e: st.error(f"Error Database: {e}")

    # --- TAB IA ---
    with tab_ia:
        st.subheader("Daftar Naskah IA")
        try:
            # Join table untuk mendapatkan nama mitra dari PKS
            query = """
                SELECT a.id, a.judul_ia, a.tanggal_dibuat, b.nama_mitra 
                FROM dokumen_ia a 
                JOIN dokumen_pks b ON a.pks_id = b.id 
                ORDER BY a.tanggal_dibuat DESC
            """
            df_ia = pd.read_sql(query, conn)
            conn.close()
            
            if not df_ia.empty:
                c1, c2, c3, c4 = st.columns([2, 3, 3, 2])
                c1.markdown("**Tanggal**"); c2.markdown("**Mitra (Induk)**"); c3.markdown("**Judul IA**"); c4.markdown("**Aksi**")
                st.divider()
                
                for _, row in df_ia.iterrows():
                    c1, c2, c3, ce, cd = st.columns([2, 3, 3, 1, 1])
                    c1.write(row['tanggal_dibuat'].strftime('%d-%m-%Y %H:%M'))
                    c2.write(row['nama_mitra'])
                    c3.write(row['judul_ia'])
                    # Tombol aksi IA bisa dikembangkan lebih lanjut di sini
                    if cd.button("🗑️", key=f"del_ia_{row['id']}"):
                        conn = get_db_connection(); cur = conn.cursor()
                        cur.execute("DELETE FROM dokumen_ia WHERE id = %s", (row['id'],))
                        conn.commit(); cur.close(); conn.close()
                        st.rerun()
            else: st.info("Belum ada data IA.")
        except Exception as e: st.error(f"Error Database: {e}")
