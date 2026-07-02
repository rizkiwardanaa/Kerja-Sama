import streamlit as st
import pandas as pd
import json
import google.generativeai as genai
from db_config import get_db_connection
from datetime import datetime

# Asumsi model AI dikirim dari app.py
def render_ia(model):
    st.title("Pembuatan Implementation Arrangement (IA)")
    
    # 1. Pilih PKS Induk dari Database
    conn = get_db_connection()
    df_pks = pd.read_sql("SELECT id, judul_ks, nama_mitra, form_data FROM dokumen_pks ORDER BY tanggal_dibuat DESC", conn)
    conn.close()
    
    if df_pks.empty:
        st.warning("Belum ada dokumen PKS di database. Buat PKS terlebih dahulu sebelum membuat IA.")
        return

    # Opsi dropdown PKS
    pks_options = df_pks.apply(lambda row: f"{row['nama_mitra']} - {row['judul_ks']} (ID: {row['id']})", axis=1).tolist()
    
    st.markdown("### 1. Pilih Dokumen Induk (PKS)")
    selected_pks_str = st.selectbox("Pilih PKS yang akan diturunkan menjadi IA:", pks_options)
    
    # Ambil ID dan Data dari PKS yang dipilih
    selected_index = pks_options.index(selected_pks_str)
    pks_data = df_pks.iloc[selected_index]
    pks_id = pks_data['id']
    form_pks_induk = json.loads(pks_data['form_data'])
    
    # Tampilkan read-only data induk agar user ingat konteksnya
    with st.expander("Lihat Ringkasan PKS Induk", expanded=False):
        st.info(f"**Mitra:** {form_pks_induk.get('nama_mitra', '')}\n\n**Ruang Lingkup PKS:** {form_pks_induk.get('ruang_lingkup', '')}")

    st.markdown("---")
    
    # 2. Form Input Spesifik IA
    with st.form("form_ia_input"):
        st.markdown("### 2. Detail Implementation Arrangement")
        judul_ia = st.text_input("Judul/Nama Kegiatan Spesifik", placeholder="Contoh: Program Pertukaran Mahasiswa Merdeka 2026")
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Person In Charge (Unmul)")
            pic_nama_p1 = st.text_input("Nama PIC Unmul", placeholder="Nama Dosen/Kaprodi")
            pic_jabatan_p1 = st.text_input("Jabatan PIC Unmul")
            pic_kontak_p1 = st.text_input("Kontak/Email PIC Unmul")
            
        with col2:
            st.subheader("Person In Charge (Mitra)")
            pic_nama_p2 = st.text_input("Nama PIC Mitra")
            pic_jabatan_p2 = st.text_input("Jabatan PIC Mitra")
            pic_kontak_p2 = st.text_input("Kontak/Email PIC Mitra")
            
        jadwal_pelaksanaan = st.text_input("Waktu Pelaksanaan Kegiatan", placeholder="Bulan Agustus - Desember 2026")
        detail_teknis = st.text_area("Rincian Kegiatan & Output", placeholder="Jelaskan detail apa yang akan dilakukan, pembagian tugas, dan target output...")
        detail_dana = st.text_area("Rincian Pembiayaan (Opsional)", placeholder="Sebutkan jika ada sumber dana spesifik, jika tidak isi 'Ditanggung masing-masing pihak'")
        
        btn_generate_ia = st.form_submit_button("Generate Pasal IA (AI)", type="primary")

    # State untuk menampung hasil generate IA
    if 'ia_json' not in st.session_state: st.session_state.ia_json = {}

    # 3. Logika Generate IA
    if btn_generate_ia:
        if not judul_ia or not detail_teknis:
            st.error("Mohon isi Judul Kegiatan dan Rincian Kegiatan terlebih dahulu.")
        else:
            with st.spinner("Menyusun draf IA..."):
                prompt = f"""
                Buat pasal-pasal untuk dokumen Implementation Arrangement (IA).
                IA ini adalah turunan dari Perjanjian Kerja Sama (PKS) antara Universitas Mulawarman dan {form_pks_induk.get('nama_mitra', '')}.
                
                Konteks Kegiatan Spesifik:
                - Judul IA: {judul_ia}
                - Waktu Pelaksanaan: {jadwal_pelaksanaan}
                - Rincian Kegiatan: {detail_teknis}
                - Pembiayaan: {detail_dana}
                - PIC Pihak 1: {pic_nama_p1} ({pic_jabatan_p1})
                - PIC Pihak 2: {pic_nama_p2} ({pic_jabatan_p2})
                
                Keluarkan output HANYA format JSON murni. Kunci:
                {{
                    "Pasal 1: Tujuan Pelaksanaan": "...",
                    "Pasal 2: Ruang Lingkup dan Mekanisme": "...",
                    "Pasal 3: Hak dan Kewajiban": "...",
                    "Pasal 4: Pembiayaan": "...",
                    "Pasal 5: Person In Charge (PIC)": "(Sebutkan nama dan kontak PIC secara jelas)",
                    "Pasal 6: Jangka Waktu Pelaksanaan": "...",
                    "Pasal 7: Ketentuan Lain-lain": "..."
                }}
                """
                try:
                    response = model.generate_content(prompt)
                    raw_json = response.text.replace('```json', '').replace('```', '').strip()
                    st.session_state.ia_json = json.loads(raw_json)
                    st.rerun()
                except Exception as e:
                    st.error(f"Gagal generate IA: {e}")

    # 4. Editor IA dan Simpan
    if st.session_state.ia_json:
        st.markdown("### 3. Editor Draft IA")
        
        # Pembuka IA (Bisa dikonfigurasi lebih rapi nanti)
        pembuka_ia = f"Sebagai tindak lanjut dari Perjanjian Kerja Sama antara Universitas Mulawarman dan {form_pks_induk.get('nama_mitra')}, PARA PIHAK sepakat untuk melaksanakan {judul_ia} dengan ketentuan sebagai berikut:"
        st.info(pembuka_ia)
        
        with st.form("form_ia_save"):
            edited_ia = {}
            for jdl, isi in st.session_state.ia_json.items():
                edited_ia[jdl] = st.text_area(jdl, value=isi, height=120)
            
            if st.form_submit_button("Simpan IA ke Database"):
                # Menyatukan teks
                full_ia_doc = pembuka_ia + "\n\n"
                for jdl, isi in edited_ia.items():
                    full_ia_doc += f"{jdl}\n{isi}\n\n"
                
                # Simpan form data
                form_ia_data = {
                    'judul_ia': judul_ia, 'pic_nama_p1': pic_nama_p1, 'pic_nama_p2': pic_nama_p2,
                    'jadwal': jadwal_pelaksanaan, 'teknis': detail_teknis, 'ia_json': edited_ia
                }
                
                try:
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO dokumen_ia (pks_id, judul_ia, tanggal_dibuat, isi_dokumen, form_data) VALUES (%s, %s, %s, %s, %s)",
                        (pks_id, judul_ia, datetime.now(), full_ia_doc, json.dumps(form_ia_data))
                    )
                    conn.commit()
                    cur.close()
                    conn.close()
                    st.success("Draft IA berhasil disimpan dan ditautkan ke PKS Induk!")
                except Exception as e:
                    st.error(f"Error menyimpan IA: {e}")
