import streamlit as st
import pandas as pd
import json
from fpdf import FPDF
from datetime import datetime
import os
import tempfile
from db_config import get_db_connection

def render_ia(model):
    st.title("Generator Implementation Arrangement (IA)")
    
    if 'ia_json' not in st.session_state: st.session_state.ia_json = {}
    if 'ia_pdf_ready' not in st.session_state: st.session_state.ia_pdf_ready = False
    
    conn = get_db_connection()
    df_pks = pd.read_sql("SELECT id, judul_ks, nama_mitra, form_data FROM dokumen_pks ORDER BY tanggal_dibuat DESC", conn)
    conn.close()
    
    if df_pks.empty:
        st.warning("Belum ada dokumen PKS. Buat PKS terlebih dahulu.")
        return

    pks_options = df_pks.apply(lambda r: f"{r['nama_mitra']} - {r['judul_ks']} (ID: {r['id']})", axis=1).tolist()
    st.markdown("### 1. Pilih Dokumen Induk (PKS)")
    selected_pks = st.selectbox("PKS Induk:", pks_options)
    
    idx = pks_options.index(selected_pks)
    pks_data = df_pks.iloc[idx]
    pks_id = pks_data['id']
    form_pks = json.loads(pks_data['form_data'])
    
    with st.form("form_ia"):
        st.markdown("### 2. Detail Spesifik IA (Bahasa Inggris)")
        col1, col2 = st.columns(2)
        with col1:
            no_ia = st.text_input("IA Number", placeholder="856/UN17.13/HK.07.01/2024")
            prodi_unmul = st.text_input("Study Program (Unmul)", value="Indonesian Literature Study Program")
            tgl_ia_str = st.text_input("Signed Date (e.g., 4th October 2024)", value="4th October 2024")
            
            st.subheader("First Party (Mitra)")
            pic_nama_p1 = st.text_input("First Party PIC Name", placeholder="Prof. Shermanov Eldor")
            pic_jabatan_p1 = st.text_input("First Party Title", placeholder="Rector of the Uzbek...")
        with col2:
            judul_ia = st.text_input("IA Subject/Title", placeholder="Implementation of Academic Collaboration")
            st.write("") 
            st.write("")
            
            st.subheader("Second Party (Unmul)")
            pic_nama_p2 = st.text_input("Second Party PIC Name", placeholder="Dr. Ahmad Mubarok")
            pic_jabatan_p2 = st.text_input("Second Party Title", placeholder="Head of Indonesian Literature Department")
            
        detail = st.text_area("Activity Details (Prompt AI)", placeholder="Jelaskan secara ringkas kegiatan, objektif, pendanaan, dsb dalam bahasa Indonesia atau Inggris...")
        
        teks_pembuka = f"This Implementation of Arrangements is developed as a derivative of the Cooperation Agreement between {form_pks.get('nama_mitra', '')} and the {form_pks.get('lembaga_p1', 'Faculty')}, Mulawarman University, specifically for collaborative activities involving the {prodi_unmul} at Mulawarman University."

        btn_gen = st.form_submit_button("Generate AI Sections (English)", type="primary")
        edited_ia = {}
        btn_save = btn_pdf = False
        
        if st.session_state.ia_json:
            st.markdown("### 3. Editor (English Sections)")
            st.info(teks_pembuka)
            for jdl, isi in st.session_state.ia_json.items():
                edited_ia[jdl] = st.text_area(jdl, value=isi, height=200)
            
            cs, cp = st.columns(2)
            with cs: btn_save = st.form_submit_button("Simpan IA")
            with cp: btn_pdf = st.form_submit_button("Siapkan PDF IA")

    if btn_gen:
        with st.spinner("AI is generating English sections..."):
            prompt = f"""
            Write the articles for an Implementation Arrangement in English. 
            Context: {detail}. 
            Output strictly valid JSON with these exact keys:
            {{
                "1. OBJECTIVES": "Explain academic, research, and cultural objectives.",
                "2. RESPONSIBILITIES": "Explain program coordination and implementation.",
                "3. FINANCIAL ARRANGEMENTS": "Explain travel, accommodation, and operational costs.",
                "4. DURATION": "Explain the duration (e.g. 5 years).",
                "5. EVALUATION AND REVIEW": "Explain annual review.",
                "6. TERMINATION": "Explain termination notice period."
            }}
            """
            try:
                res = model.generate_content(prompt)
                st.session_state.ia_json = json.loads(res.text.replace('```json', '').replace('```', '').strip())
                st.session_state.ia_pdf_ready = False
                st.rerun()
            except Exception as e: st.error(f"Error AI: {e}")

    if btn_save:
        try:
            full_doc = teks_pembuka + "\n\n" + "\n\n".join([f"{k}\n{v}" for k,v in edited_ia.items()])
            data_ia = {'no_ia': no_ia, 'prodi_unmul': prodi_unmul, 'tgl_ia': tgl_ia_str, 'pic_nama_p1': pic_nama_p1, 'pic_jabatan_p1': pic_jabatan_p1, 'pic_nama_p2': pic_nama_p2, 'pic_jabatan_p2': pic_jabatan_p2, 'ia_json': edited_ia}
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO dokumen_ia (pks_id, judul_ia, tanggal_dibuat, isi_dokumen, form_data) VALUES (%s, %s, %s, %s, %s)", (pks_id, judul_ia, datetime.now(), full_doc, json.dumps(data_ia)))
            conn.commit(); cur.close(); conn.close()
            st.success("IA Tersimpan!")
        except Exception as e: st.error(f"DB Error: {e}")

    if btn_pdf:
        try:
            class PDF_IA(FPDF):
                def footer(self):
                    self.set_y(-15); self.set_font('Arial', '', 10)
                    self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

            pdf = PDF_IA('P', 'mm', 'A4'); pdf.add_page(); pdf.set_auto_page_break(True, 20); pdf.set_margins(25, 20, 25)
            
            pdf.set_font("Arial", 'B', 12)
            for t in ["IMPLEMENTATION OF ARRANGEMENTS", f"BETWEEN {form_pks.get('nama_mitra', '').upper()}", "AND", f"{form_pks.get('lembaga_p1', 'FACULTY').upper()}, MULAWARMAN UNIVERSITY", f"SPECIFIC TO THE {prodi_unmul.upper()}", "", f"Number: {no_ia}"]:
                pdf.cell(0, 6, t, 0, 1, 'C') if t else pdf.ln(5)
            
            pdf.ln(10)
            pdf.set_font("Arial", '', 11)
            pdf.multi_cell(0, 6, teks_pembuka.encode('latin-1', 'replace').decode('latin-1'), align='J')
            pdf.ln(5)
            
            for jdl, isi in edited_ia.items():
                pdf.set_font("Arial", 'B', 11); pdf.multi_cell(0, 6, jdl, align='L')
                pdf.set_font("Arial", '', 11); pdf.multi_cell(0, 6, isi.encode('latin-1', 'replace').decode('latin-1'), align='J')
                pdf.ln(5)
            
            pdf.ln(10); pdf.set_font("Arial", '', 11); pdf.cell(0, 6, f"Signed on {tgl_ia_str},", 0, 1, 'L'); pdf.ln(5)
            
            pdf.cell(0, 6, "First Party:", 0, 1, 'L'); pdf.cell(0, 6, form_pks.get('nama_mitra', ''), 0, 1, 'L'); pdf.ln(20)
            pdf.set_font("Arial", 'B', 11); pdf.cell(0, 6, pic_nama_p1, 0, 1, 'L')
            pdf.set_font("Arial", '', 11); pdf.cell(0, 6, pic_jabatan_p1, 0, 1, 'L'); pdf.ln(10)
            
            pdf.cell(0, 6, "Second Party:", 0, 1, 'L'); pdf.cell(0, 6, f"The {prodi_unmul}, {form_pks.get('lembaga_p1', '')}, Mulawarman University", 0, 1, 'L'); pdf.ln(20)
            pdf.set_font("Arial", 'B', 11); pdf.cell(0, 6, pic_nama_p2, 0, 1, 'L')
            pdf.set_font("Arial", '', 11); pdf.cell(0, 6, pic_jabatan_p2, 0, 1, 'L')
            
            pdf.output("Draft_IA.pdf")
            st.session_state.ia_pdf_ready = True
        except Exception as e: st.error(f"PDF Error: {e}")

    if st.session_state.ia_pdf_ready and os.path.exists("Draft_IA.pdf"):
        with open("Draft_IA.pdf", "rb") as f: st.download_button("Unduh PDF IA", f, "IA_Document.pdf", "application/pdf", type="primary")
