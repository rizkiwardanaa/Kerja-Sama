import streamlit as st
import pandas as pd
import plotly.express as px
from db_config import get_db_connection

def render_dashboard():
    st.title("📊 Dasbor Kinerja Kerja Sama")
    st.write("Ringkasan eksekutif statistik payung kerja sama (PKS) dan implementasi riil (IA) pada 5 Program Studi.")

    # 1. MENGAMBIL DATA DARI DATABASE NEON
    conn = get_db_connection()
    query = "SELECT jenis_dokumen, nama_mitra, prodi FROM arsip_dokumen"
    
    try:
        df = pd.read_sql(query, conn)
    except Exception as e:
        st.error(f"Gagal mengambil data dari database: {e}")
        conn.close()
        return
        
    conn.close()

    if df.empty:
        st.info("Data arsip masih kosong. Silakan unggah dokumen di menu Arsip terlebih dahulu.")
        return

    # Normalisasi teks untuk menghindari error perbedaan huruf besar/kecil
    df['jenis_dokumen'] = df['jenis_dokumen'].astype(str).str.upper()

    # --- KARTU INDIKATOR UTAMA (SCORECARDS) ---
    total_pks = df[df['jenis_dokumen'].str.contains('PKS')].shape[0]
    total_ia = df[df['jenis_dokumen'].str.contains('IA')].shape[0]
    total_mitra = df['nama_mitra'].nunique() # Menghitung mitra tanpa duplikasi

    c1, c2, c3 = st.columns(3)
    with c1:
        st.info(f"**Total PKS**\n### {total_pks}")
    with c2:
        st.success(f"**Total IA**\n### {total_ia}")
    with c3:
        st.warning(f"**Instansi Mitra**\n### {total_mitra}")

    st.markdown("---")

    # --- ALGORITMA PEMROSESAN MATRIKS PRODI ---
    # Mendefinisikan 5 Prodi target secara pasti
    target_prodi = [
        "Sastra Indonesia", 
        "Sastra Inggris", 
        "Etnomusikologi", 
        "Tari", 
        "S2 Kajian Budaya"
    ]
    
    # Menyiapkan wadah penyimpanan perhitungan awal = 0
    data_rekap = {prodi: {'PKS': 0, 'IA': 0} for prodi in target_prodi}

    # Membaca setiap baris data dan mendistribusikannya ke masing-masing Prodi
    for _, row in df.iterrows():
        jenis = str(row['jenis_dokumen']).upper()
        teks_prodi = str(row['prodi']).lower() 
        
        # Tentukan apakah ini dokumen PKS atau IA
        kategori = 'PKS' if 'PKS' in jenis else ('IA' if 'IA' in jenis else None)
        
        if kategori:
            for prodi in target_prodi:
                # Pencarian teks: Jika prodi X disebut di dalam dokumen, tambahkan poinnya +1
                if prodi.lower() in teks_prodi:
                    data_rekap[prodi][kategori] += 1

    # Mengubah data rekapitulasi menjadi format tabel untuk grafik Plotly
    plot_data = []
    for prodi, counts in data_rekap.items():
        plot_data.append({'Program Studi': prodi, 'Jenis Dokumen': 'PKS', 'Jumlah': counts['PKS']})
        plot_data.append({'Program Studi': prodi, 'Jenis Dokumen': 'IA', 'Jumlah': counts['IA']})
        
    df_plot = pd.DataFrame(plot_data)

    # --- GRAFIK BATANG INTERAKTIF ---
    st.subheader("📈 Distribusi Keterlibatan per Program Studi")
    
    fig = px.bar(
        df_plot, 
        x='Program Studi', 
        y='Jumlah', 
        color='Jenis Dokumen',
        barmode='group', # Menjadikan batang berdampingan, bukan ditumpuk
        color_discrete_map={'PKS': '#1f77b4', 'IA': '#ff7f0e'}, # Biru untuk PKS, Oranye untuk IA
        text_auto=True # Menampilkan angka di pucuk tiang secara otomatis
    )
    
    # Membersihkan tampilan visual grafik
    fig.update_layout(
        xaxis_title="",
        yaxis_title="Jumlah Dokumen",
        legend_title="Kategori",
        hovermode="x unified",
        margin=dict(t=30, b=10)
    )
    
    # Menampilkan grafik ke dalam Streamlit
    st.plotly_chart(fig, use_container_width=True)

    st.write("")

    # --- TABEL MATRIKS REKAPITULASI ---
    st.subheader("📋 Matriks Rincian Kerja Sama")
    
    table_data = []
    for prodi, counts in data_rekap.items():
        total_keterlibatan = counts['PKS'] + counts['IA']
        table_data.append({
            'Program Studi': prodi,
            'PKS (Payung)': counts['PKS'],
            'IA (Implementasi)': counts['IA'],
            'Total Keterlibatan': total_keterlibatan
        })
        
    df_table = pd.DataFrame(table_data)
    
    # Menampilkan tabel Streamlit modern tanpa kolom index (nomor urut bawaan pandas)
    st.dataframe(
        df_table, 
        use_container_width=True, 
        hide_index=True
    )
