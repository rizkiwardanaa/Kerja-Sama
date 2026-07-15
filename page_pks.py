import streamlit as st
import json
import os
import tempfile
from fpdf import FPDF
from datetime import datetime
from db_config import get_db_connection

def terbilang(angka):
    satuan = ["", "Satu", "Dua", "Tiga", "Empat", "Lima", "Enam", "Tujuh", "Delapan", "Sembilan", "Sepuluh", "Sebelas"]
    if angka < 12: return satuan[angka]
    elif angka < 20: return satuan[angka - 10] + " Belas"
    elif angka < 100: return (satuan[angka // 10] + " Puluh " + satuan[angka % 10]).strip()
    elif angka < 200: return "Seratus " + terbilang(angka - 100).strip()
    elif angka < 1000: return (satuan[angka // 100] + " Ratus " + terbilang(angka % 100)).strip()
    elif angka < 2000: return "Seribu " + terbilang(angka - 1000).strip()
    elif angka < 1000000: return (terbilang(angka // 1000) + " Ribu " + terbilang(angka % 1000)).strip()
    return str(angka)

def get_tanggal_naratif(tgl_obj):
    if not tgl_obj: return ""
    bulan_indo = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    tgl_teks = terbilang(tgl_obj.day)
    bln_teks = bulan_indo[tgl_obj.month]
    thn_teks = terbilang(tgl_obj.year)
    tgl_format = tgl_obj.strftime("%d/%m/%Y")
    return f"tanggal {tgl_teks} bulan {bln_teks}, tahun {thn_teks} ({tgl_format})"

def render_pks(model):
    st.title("Generator Naskah PKS (Induk)")

    if 'pks_json' not in st.session_state: st.session_state.pks_json = {}
    if 'pks_edit_id' not in st.session_state: st.session_state.pks_edit_id = None
    if 'pks_edit_data' not in st.session_state: st.session_state.pks_edit_data = {}
    if 'pks_pdf_ready' not in st.session_state: st.session_state.pks_pdf_ready = False

    def get_val(key, default):
        return st.session_state.pks_edit_data.get(key, default)

    if st.session_state.pks_edit_id:
        st.warning("Sedang dalam mode Edit Dokumen PKS.")
        if st.button("Batal Edit / Buat Baru"):
            st.session_state.pks_edit_id = None
            st.session_state.pks_edit_data = {}
            st.session_state.pks_json = {}
            st.session_state.pks_pdf_ready = False
            st.rerun()

    with st.form("main_pks_form"):
        with st.expander("1. Form Data PKS", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                logo_mitra = st.file_uploader("Unggah Logo Mitra (PKS)", type=["png", "jpg", "jpeg"])
                judul_ks = st.text_input("Judul Kerja Sama", value=get_val('judul_ks', "TRIDHARMA PERGURUAN TINGGI"))
                no_unit_unmul = st.text_input("Nomor Surat Pihak 1 (Unmul)", value=get_val('no_unit_unmul', ""))
                
                st.markdown("**Waktu Penandatanganan**")
                default_tgl_str = get_val('tgl_ttd', datetime.now().strftime("%Y-%m-%d"))
                tgl_ttd = st.date_input("Pilih Tanggal Penandatanganan", value=datetime.strptime(default_tgl_str, "%Y-%m-%d").date())
                
                st.subheader("Pihak 1 (Universitas Mulawarman)")
                nama_p1 = st.text_input("Nama Pejabat P1", value=get_val('nama_p1', "Prof. Dr. M. Bahri Arifin, M.Hum"))
                jabatan_p1 = st.text_input("Jabatan P1", value=get_val('jabatan_p1', "Dekan Fakultas Ilmu Budaya"))
                lembaga_p1 = st.text_input("Nama Lembaga P1", value=get_val('lembaga_p1', "Fakultas Ilmu Budaya Universitas Mulawarman"))
                alamat_p1 = st.text_area("Alamat Lembaga P1", value=get_val('alamat_p1', "Jl. Ki Hajar Dewantara, Gunung Kelua, Samarinda, Kalimantan Timur 75123"))
                nip_p1 = st.text_input("NIP P1", value=get_val('nip_p1', ""))

            with col2:
                no_mitra = st.text_input("Nomor Surat Pihak 2 (Mitra)", value=get_val('no_mitra', ""))
                
                st.subheader("Pihak 2 (Mitra)")
                nama_mitra = st.text_input("Nama Instansi Mitra", value=get_val('nama_mitra', "INSTITUT SENI INDONESIA YOGYAKARTA"))
                nama_p2 = st.text_input("Nama Pejabat P2", value=get_val('nama_p2', "Dr. I Nyoman Cau Arsana, S.Sn., M.Hum"))
                jabatan_p2 = st.text_input("Jabatan P2", value=get_val('jabatan_p2', "Dekan Fakultas Seni Pertunjukan"))
                alamat_mitra = st.text_area("Alamat Mitra", value=get_val('alamat_mitra', "Jl. Parangtritis Km. 6.5 Sewon Bantul Yogyakarta"))
                nip_p2 = st.text_input("NIP P2", value=get_val('nip_p2', ""))
                
                st.subheader("Detail untuk AI")
                tgl_berakhir = st.text_input("Tanggal Berakhir Kerja Sama", value=get_val('tgl_berakhir', "Dua Puluh Dua April Dua Ribu Tiga Puluh"))
                ruang_lingkup = st.text_area("Ruang Lingkup & Gambaran Besar", value=get_val('ruang_lingkup', ""))

        narasi_tanggal = get_tanggal_naratif(tgl_ttd)
        teks_pembuka = f"Pada hari ini, {narasi_tanggal} yang bertanda tangan di bawah ini:\n1. {nama_p1}: {jabatan_p1} oleh karena itu sah mewakili dan bertindak untuk dan atas nama {lembaga_p1}, Universitas Mulawarman, yang berkedudukan di {alamat_p1}, selanjutnya disebut sebagai PIHAK KESATU.\n2. {nama_p2}: {jabatan_p2} oleh karena itu sah mewakili dan bertindak untuk dan atas nama {nama_mitra}, yang berkedudukan di {alamat_mitra}, selanjutnya disebut sebagai PIHAK KEDUA.\n\nPIHAK KESATU dan PIHAK KEDUA selanjutnya disebut PARA PIHAK. Dengan ini sepakat untuk bersama-sama membuat Perjanjian Kerja Sama mengenai {judul_ks} yang dilaksanakan oleh PARA PIHAK seperti diatur dalam pasal sebagai berikut."

        btn_generate = st.form_submit_button("Generate Pasal AI", type="primary")
        edited_pasal = {}
        btn_save = btn_pdf = False
        
        if st.session_state.pks_json:
            st.markdown("---")
            st.subheader("2. Draft PKS (Editor Terpisah)")
            st.info("Bagian Pembuka (Komparisi) otomatis dikunci sesuai tata naskah.")
            
            for jdl, isi in st.session_state.pks_json.items():
                edited_pasal[jdl] = st.text_area(jdl, value=isi, height=150)
            
            col_s, col_p = st.columns(2)
            with col_s: btn_save = st.form_submit_button("Simpan PKS ke Database")
            with col_p: btn_pdf = st.form_submit_button("Siapkan PDF PKS")

    if btn_generate or btn_save or btn_pdf:
        if edited_pasal: st.session_state.pks_json = edited_pasal
        st.session_state.pks_edit_data = {
            'judul_ks': judul_ks, 'no_unit_unmul': no_unit_unmul, 'tgl_ttd': tgl_ttd.strftime("%Y-%m-%d"),
            'nama_p1': nama_p1, 'jabatan_p1': jabatan_p1, 'lembaga_p1': lembaga_p1, 'alamat_p1': alamat_p1, 'nip_p1': nip_p1, 
            'no_mitra': no_mitra, 'nama_mitra': nama_mitra, 'nama_p2': nama_p2, 'jabatan_p2': jabatan_p2, 
            'alamat_mitra': alamat_mitra, 'nip_p2': nip_p2, 'tgl_berakhir': tgl_berakhir, 
            'ruang_lingkup': ruang_lingkup, 'pasal_json': edited_pasal
        }
    
    if btn_generate:
        with st.spinner("Gemini menyusun pasal PKS..."):
            prompt = f'Buat isi pasal PKS untuk "{judul_ks}". Konteks: {ruang_lingkup}. Tanggal Berakhir: {tgl_berakhir}. Output JSON murni dengan kunci: "Pasal 1: Maksud dan Tujuan", "Pasal 2: Ruang Lingkup Kegiatan", "Pasal 3: Pelaksanaan Program", "Pasal 4: Pembiayaan", "Pasal 5: Jangka Waktu", "Pasal 6: Penutup".'
            try:
                res = model.generate_content(prompt)
                st.session_state.pks_json = json.loads(res.text.replace('```json', '').replace('```', '').strip())
                st.session_state.pks_pdf_ready = False
                st.rerun()
            except Exception as e: st.error(f"Gagal generate PKS: {e}")

    if btn_save:
        try:
            full_doc = teks_pembuka + "\n\n" + "\n\n".join([f"{k}\n{v}" for k,v in st.session_state.pks_json.items()])
            form_str = json.dumps(st.session_state.pks_edit_data)
            conn = get_db_connection()
            cur = conn.cursor()
            if st.session_state.pks_edit_id:
                cur.execute("UPDATE dokumen_pks SET judul_ks=%s, nama_mitra=%s, tanggal_dibuat=%s, isi_dokumen=%s, form_data=%s WHERE id=%s", (judul_ks, nama_mitra, datetime.now(), full_doc, form_str, st.session_state.pks_edit_id))
            else:
                cur.execute("INSERT INTO dokumen_pks (judul_ks, nama_mitra, tanggal_dibuat, isi_dokumen, form_data) VALUES (%s, %s, %s, %s, %s) RETURNING id", (judul_ks, nama_mitra, datetime.now(), full_doc, form_str))
                st.session_state.pks_edit_id = cur.fetchone()[0]
            conn.commit()
            conn.close()
            st.success("Dokumen PKS tersimpan!")
        except Exception as e: st.error(f"Error DB PKS: {e}")

    if btn_pdf:
        try:
            class PDF(FPDF):
                def footer(self):
                    self.set_y(-35); self.set_font('Arial', '', 10)
                    self.set_x(25); self.cell(32, 5, 'Paraf', 'LTR', 0, 'C'); self.cell(32, 5, 'Paraf', 'LTR', 1, 'C')
                    self.set_x(25); self.cell(32, 5, 'PIHAK KESATU', 'LBR', 0, 'C'); self.cell(32, 5, 'PIHAK KEDUA', 'LBR', 1, 'C')
                    self.set_x(25); self.cell(32, 10, '', 1, 0, 'C'); self.cell(32, 10, '', 1, 1, 'C')
                    self.set_y(-25); self.cell(0, 10, f'Halaman {self.page_no()} dari {{nb}}', 0, 0, 'R')

            pdf = PDF('P', 'mm', 'A4'); pdf.alias_nb_pages(); pdf.add_page(); pdf.set_auto_page_break(True, 45); pdf.set_margins(25, 20, 25)
            
            if os.path.exists("logo_unmul.png"): pdf.image("logo_unmul.png", 25, 20, 30)
            if logo_mitra:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp: tmp.write(logo_mitra.read()); tmp_path = tmp.name
                pdf.image(tmp_path, 155, 20, 30)
            
            pdf.set_y(55); pdf.set_font("Arial", 'B', 12)
            for t in ["PERJANJIAN KERJA SAMA", "ANTARA", lembaga_p1.upper(), "UNIVERSITAS MULAWARMAN", "DENGAN", nama_mitra.upper(), "", "TENTANG", judul_ks.upper(), "", f"Nomor : {no_unit_unmul}", f"Nomor : {no_mitra}"]:
                pdf.cell(0, 6, t, 0, 1, 'C') if t else pdf.ln(5)
            
            # Format rata kiri sesuai permintaan
            pdf.ln(10); pdf.set_font("Arial", '', 11); pdf.multi_cell(0, 6, teks_pembuka.encode('latin-1', 'replace').decode('latin-1'), align='L'); pdf.ln(5)
            
            for jdl, isi in st.session_state.pks_json.items():
                pdf.set_font("Arial", 'B', 11)
                if ":" in jdl:
                    n, t = jdl.split(":", 1); pdf.multi_cell(0, 6, n.strip().upper(), align='C'); pdf.multi_cell(0, 6, t.strip().upper(), align='C')
                else: pdf.multi_cell(0, 6, jdl.upper(), align='C')
                pdf.set_font("Arial", '', 11); pdf.multi_cell(0, 6, isi.encode('latin-1', 'replace').decode('latin-1'), align='J'); pdf.ln(5)
            
            pdf.ln(10); pdf.set_font("Arial", 'B', 11); pdf.set_x(25); pdf.cell(80, 5, 'PIHAK KESATU,', 0, 0, 'L'); pdf.cell(80, 5, 'PIHAK KEDUA,', 0, 1, 'L'); pdf.ln(25)
            # Tanpa underline
            pdf.set_font("Arial", '', 11); pdf.set_x(25); pdf.cell(80, 5, nama_p1, 0, 0, 'L'); pdf.cell(80, 5, nama_p2, 0, 1, 'L')
            # NIP Bold
            pdf.set_font("Arial", 'B', 11); pdf.set_x(25); pdf.cell(80, 5, f'NIP {nip_p1}', 0, 0, 'L'); pdf.cell(80, 5, f'NIP {nip_p2}' if nip_p2 else '', 0, 1, 'L')
            
            pdf.output("Draft_PKS.pdf")
            st.session_state.pks_pdf_ready = True
        except Exception as e: st.error(f"Error PDF PKS: {e}")

    if st.session_state.pks_pdf_ready and os.path.exists("Draft_PKS.pdf"):
        with open("Draft_PKS.pdf", "rb") as f: st.download_button("Unduh PDF PKS", f, "PKS_Unmul.pdf", "application/pdf", type="primary")
