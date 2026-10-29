# Merchant Promo Scraper

Pipeline Python untuk mengambil data promo dari halaman publik Hemat.id, Katalogpromosi.com, dan Scanharga.com. Proyek ini mengambil teks/HTML serta metadata gambar yang tersedia di halaman. **Poster hanya direferensikan lewat URL; gambar tidak dibaca, tidak di-OCR, dan tidak dipakai untuk menebak harga.**

## Struktur proyek

```text
.
├── src/          # collector, validasi, referensi harga, health check, dan ekspor
├── tests/        # tes regresi offline
├── config/       # konfigurasi klasifikasi/kategori
├── data/         # seed referensi awal dan referensi yang ditinjau manual
├── output/       # katalog Excel/CSV; dibuat saat dijalankan, jangan commit
├── runtime/      # hasil scraping perantara, log, health report; jangan commit
├── state/        # database observasi harga dinamis; jangan commit
├── run.bat
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

`output/`, `runtime/`, dan `state/` diabaikan oleh Git. Hanya data referensi awal dan referensi yang dikurasi manual yang berada di `data/`.

## Python tanpa virtual environment dan tanpa instalasi otomatis

`run.bat` mencoba `PROMO_PYTHON`, lokasi instalasi Python umum, `py -3`, lalu `python`. **Kandidat diuji berdasarkan versi dan library yang benar-benar bisa diimpor**, bukan hanya nomor versi. Python minimal 3.10 harus memiliki `requests`, `beautifulsoup4` (`bs4`), dan `openpyxl`. Mode normal dan tes offline juga membutuhkan `pytest`; `--check-only` tidak membutuhkan `pytest`.

Launcher tidak membuat `venv`/`.venv` dan tidak menjalankan `pip install`. Jika dependency belum tersedia, proses berhenti dengan pesan yang menjelaskan kebutuhan tersebut.

Untuk memilih Python yang library-nya sudah lengkap, jalankan perintah berikut di CMD:

```bat
set PROMO_PYTHON=D:\Python312\python.exe
run.bat --check-only
```

`PROMO_PYTHON` diisi dengan path executable tanpa tanda kutip tambahan. Pemilihan eksplisit tetap diverifikasi dan bisa ditolak jika dependency tidak lengkap.

## Menjalankan

Periksa Python dan library runtime saja:

```bat
run.bat --check-only
```

Jalankan tes offline tanpa mengakses situs sumber:

```bat
run.bat --test-only
```

Jalankan tes, scraping teks/HTML, health-check, konsolidasi, dan ekspor katalog:

```bat
run.bat
```

## Database harga: seed versus state

`data/product_price_reference.csv` adalah snapshot awal yang dikemas bersama proyek. Pada run pertama, file ini disalin satu kali menjadi `state/product_price_reference.csv`. Observasi harga normal yang baru dari scraping hanya menulis ke file di `state/`, sehingga menjalankan scraper tidak mengubah CSV seed yang dilacak Git. Jika file state sudah ada, program mempertahankannya dan tidak menimpanya dengan seed versi baru.

`data/product_market_price_reference.csv` merupakan referensi harga pasar yang diverifikasi/diimpor manual; perubahan manual pada database ini memang merupakan perubahan data terkurasi yang bisa ditinjau dan di-commit. Jangan memasukkan estimasi tidak terverifikasi sebagai referensi harga pasar.

## Output

- `output/Katalog_Promo_Final.xlsx` — workbook katalog dan ringkasan audit.
- `output/Katalog_Promo_Final.csv` — data katalog beserta provenance.
- `output/Katalog_Promo_Final_Ringkas.csv` — katalog ringkas.
- `output/Daftar_Cari_Harga_Manual.xlsx` — lembar untuk mengisi referensi harga pasar dari halaman sumber langsung.
- `runtime/promo_multisource_catalog_images.csv` — URL poster/gambar yang ditemukan di halaman; bukan teks hasil pembacaan gambar.
- `runtime/promo_multisource_runlog.json` — rincian request dan status collector tiap sumber.
- `runtime/source_health_summary.json` — ringkasan status sumber, jumlah produk segar/data lama yang dipakai, kelengkapan bukti harga/periode, dan peringatan sumber.
- Setelah ekspor, `src/verify_outputs.py` memeriksa workbook, CSV katalog, indeks URL gambar, serta JSON source-health. Script ini menggunakan lokasi proyek berdasarkan `__file__`, jadi aman untuk folder Windows yang mengandung spasi atau backslash di akhir path.
- `runtime/promo_catalog_multisource_quality_report.json` — laporan kualitas output dan provenance.
- `state/product_price_reference.csv` — observasi referensi harga normal dinamis.

Harga produk hanya diambil dari teks/HTML atau referensi halaman harga yang diverifikasi. Jika harga normal tidak tersedia atau tidak lolos validasi, nilainya dapat tetap kosong; proyek tidak menebak harga normal dari poster.

## Referensi harga pasar manual (opsional)

Setelah collector berjalan, `run.bat` otomatis membuat workbook pencarian harga manual. Isi workbook berdasarkan halaman harga langsung yang mencantumkan produk, ukuran/varian, harga, URL, dan bukti harga. Setelah disimpan, impor menggunakan interpreter yang sama dengan scraper:

```bat
python src\import_manual_price_references.py output\Daftar_Cari_Harga_Manual.xlsx
python src\enrich_existing_promo_catalog_multisource.py
```

Jika `python` di PATH bukan interpreter yang dipilih launcher, jalankan kedua perintah tersebut dengan path Python yang sama melalui `%PROMO_PYTHON%`. Referensi pasar tidak menggantikan harga promo sumber.

## Kualitas dan batasan

- Status health-check **partial** berarti setidaknya ada sumber yang datanya berasal dari cache terakhir, tidak menghasilkan produk baru, atau mengalami error. Lihat `runtime/source_health_summary.json` sebelum memakai katalog untuk keputusan penting.
- Source health menghitung konektivitas, data yang terkumpul, dan cakupan bukti; laporan tersebut bukan jaminan bahwa semua produk/ harga telah benar.
- Jika semua sumber tidak menghasilkan produk segar maupun data sebelumnya, pipeline berhenti agar katalog kosong tidak menimpa hasil yang valid sebelumnya.
- Sumber publik dapat mengubah struktur HTML atau membatasi akses. Tes offline tidak menjamin scraping live akan berhasil setiap saat.
- Proyek tidak mencoba melewati status HTTP 401/403/429 atau proteksi sumber.
