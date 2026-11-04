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

`run.bat` mencoba `PROMO_PYTHON`, lokasi instalasi Python umum, `py -3`, lalu `python`. **Kandidat diuji berdasarkan versi dan library yang benar-benar bisa diimpor**, bukan hanya nomor versi. Python minimal 3.11 (Python 3.10 sudah EOL sejak 1 Oktober 2026) harus memiliki `requests`, `beautifulsoup4` (`bs4`), dan `openpyxl`. Mode normal dan tes offline juga membutuhkan `pytest`; `--check-only` tidak membutuhkan `pytest`.

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

Buat ulang workbook pencarian harga secara offline dari snapshot yang sudah ada, tanpa mengakses situs sumber:

```bat
run.bat --prepare-price-research
run.bat --import-price-research
```

Jalankan tes, scraping teks/HTML, health-check, konsolidasi, dan ekspor katalog:

```bat
run.bat
```

## Riwayat promo: snapshot versus history

Versi ini memisahkan **snapshot katalog berjalan** dari **riwayat promo permanen**:

- `runtime/promo_multisource_products_all.csv` berisi promo yang baru ditemukan dan promo lama yang masih layak dibawa ke snapshot.
- `state/promo_history.csv` adalah database permanen seluruh versi penawaran yang pernah ditemukan. Record di-upsert berdasarkan identitas produk, merchant, periode, harga, dan syarat penawaran; run berulang tidak membuat salinan identik.
- `output/Riwayat_Promo.csv` adalah ekspor yang mudah dibuka dari database riwayat. Promo `expired` dan versi `superseded` tetap ada di sini, bukan di daftar promo berjalan. Kolom `history_status_as_of` menunjukkan tanggal status itu dihitung.

Aturan retensi:

1. Promo yang tidak ditemukan pada scrape terbaru tetap dibawa ke snapshot selama tanggal akhirnya belum lewat. Baris ditandai `retained_from_previous_run` sehingga freshness tetap terlihat.
2. Promo tanpa periode yang dapat dipastikan hanya dibawa maksimal 14 hari sejak observasi terakhir dan tetap berstatus `unknown`/review.
3. Promo yang sudah melewati tanggal akhir tidak masuk snapshot berjalan, tetapi tetap disimpan dengan `history_promo_status=expired`.
4. Jika produk, merchant, dan periode sama muncul lagi dengan harga/penawaran berbeda, versi lama ditandai `superseded` dan versi terbaru dipakai untuk snapshot.
5. Jika semua sumber gagal dan tidak ada data yang masih layak dibawa, snapshot terakhir tidak ditimpa file kosong. Riwayat tetap disimpan.

Pada upgrade pertama, jika `state/promo_history.csv` belum ada, collector memigrasikan `runtime/promo_multisource_products_all.csv` yang lama satu kali. Agar data lama tidak hilang saat pindah ke repo bersih, pulihkan folder `runtime/`, `state/`, dan `output/` dari backup lokal **sebelum menjalankan `run.bat` pertama kali**. Jangan commit folder-folder tersebut ke GitHub.

## Database harga: seed versus state

`data/product_price_reference.csv` adalah snapshot awal yang dikemas bersama proyek. Pada run pertama, file ini disalin satu kali menjadi `state/product_price_reference.csv`. Observasi harga normal yang baru dari scraping hanya menulis ke file di `state/`, sehingga menjalankan scraper tidak mengubah CSV seed yang dilacak Git. Jika file state sudah ada, program mempertahankannya dan tidak menimpanya dengan seed versi baru.

`data/product_market_price_reference.csv` adalah seed referensi pasar. Observasi manual baru disimpan ke `state/product_market_price_reference.csv` (lokal dan diabaikan Git); pada run pertama seed lama dimigrasikan satu kali jika tersedia.

### Harga normal, harga pasar, dan Tokku (manual)

Kolom `Harga Asli (Rp)` hanya boleh berisi harga normal yang dinyatakan secara eksplisit oleh sumber promo atau referensi normal yang memenuhi aturan validasi yang sudah ada. Harga pasar/estimasi tidak boleh diam-diam mengisi kolom tersebut.

Jika harga normal kosong, alurnya:

1. Utamakan halaman detail `/harga/` Hemat.id yang cocok dengan SKU, varian, dan ukuran. Jika halaman menampilkan `Harga Normal`, catat harga itu sebagai bukti normal eksplisit. Jika hanya menampilkan `Harga rata-rata berdasarkan 3 bulan terakhir`, catat sebagai `historical_average_3m`, bukan harga asli resmi; rata-rata tersebut dapat mencakup promo.
2. Jika Hemat.id tidak menyediakan bukti yang cukup, Tokku boleh dipakai untuk pemeriksaan manual pada sedikit produk yang tersisa. Buka halaman produk secara normal, cocokkan merek/varian/ukuran, catat satu baris per retailer, harga, tanggal `Dicek` yang ditampilkan Tokku, URL halaman produk, dan bukti harga. Proyek tidak mengakses Tokku secara otomatis.
3. Pilih klasifikasi `normal_before_promo` untuk harga normal yang dicoret/ditampilkan sebelum diskon; `regular_no_promo` untuk harga retailer tanpa label promo; `promo` untuk harga setelah diskon; atau `historical_average_3m` untuk rata-rata historis tiga bulan.
4. Referensi Tokku hanya diterima untuk SKU yang ditandai `exact`, memiliki retailer, dan tanggal terakhir dicek sumber. Jika tanggal cek Tokku lebih dari 30 hari, datanya disimpan sebagai referensi tetapi tidak digunakan untuk estimasi harga normal saat ini.
5. Harga promo dan harga terendah historis tidak digunakan sebagai harga normal. Rata-rata historis tiga bulan menjadi fallback berkeyakinan rendah karena metriknya bisa mencakup penawaran promo.
6. Harga dari Tokku/halaman pasar menghasilkan kolom terpisah `Harga Normal Estimasi Pasar (Rp)`, rentang, sumber, umur data, dan keyakinan. Nilai ini **tidak** menggantikan `Harga Asli (Rp)` dan **tidak** dipakai menghitung diskon resmi.

Batasan Tokku: ketentuan Tokku menyebut harga hanya untuk referensi, pencocokan produk otomatis bisa keliru, dan pengambilan konten secara otomatis di luar penjelajahan pribadi normal tidak diperbolehkan. Karena itu integrasi ini adalah alur pemeriksaan/manual import, bukan scraper Tokku. Lihat https://tokku.app/id/terms.

## Output

- `output/Katalog_Promo_Final.xlsx` — workbook katalog dan ringkasan audit.
- `output/Katalog_Promo_Final.csv` — data katalog beserta provenance.
- `output/Katalog_Promo_Final_Ringkas.csv` — katalog ringkas.
- `output/Daftar_Cari_Harga_Manual.xlsx` — lembar untuk mengisi referensi normal/pasar, termasuk pemeriksaan manual Hemat.id atau Tokku.
- `output/Riwayat_Promo.csv` — seluruh promo yang pernah diamati, termasuk promo expired dan versi penawaran yang sudah digantikan.
- `runtime/promo_multisource_catalog_images.csv` — URL poster/gambar yang ditemukan di halaman; bukan teks hasil pembacaan gambar.
- `runtime/promo_multisource_runlog.json` — rincian request dan status collector tiap sumber.
- `runtime/source_health_summary.json` — ringkasan status sumber, jumlah produk segar/data lama yang dipakai, kelengkapan bukti harga/periode, dan peringatan sumber.
- Setelah ekspor, `src/verify_outputs.py` memeriksa workbook, CSV katalog, indeks URL gambar, serta JSON source-health. Script ini menggunakan lokasi proyek berdasarkan `__file__`, jadi aman untuk folder Windows yang mengandung spasi atau backslash di akhir path.
- `runtime/promo_catalog_multisource_quality_report.json` — laporan kualitas output dan provenance.
- `state/product_price_reference.csv` — observasi referensi harga normal dinamis.

Harga produk hanya diambil dari teks/HTML atau referensi halaman harga yang diverifikasi. Jika harga normal tidak tersedia atau tidak lolos validasi, nilainya dapat tetap kosong; proyek tidak menebak harga normal dari poster.

## Referensi harga pasar manual (opsional)

Setelah collector berjalan, `run.bat` otomatis membuat workbook pencarian harga manual. Isi workbook berdasarkan halaman harga langsung yang mencantumkan produk, ukuran/varian, harga, URL, dan bukti harga. Setelah disimpan, jalankan `run.bat --import-price-research`. Launcher memakai interpreter yang sama untuk mengimpor referensi, membangun ulang katalog dari snapshot terakhir (tanpa scraping live), membuat ulang workbook pencarian, dan memverifikasi hasilnya. Mode ini hanya memerlukan dependency runtime, bukan `pytest`. Referensi pasar tidak menggantikan harga promo sumber.

## Kualitas dan batasan

- Status health-check **partial** berarti ada sumber yang menggunakan data lama/carry-forward, tidak menghasilkan produk baru, atau mengalami error. Baris lama tetap ditandai agar tidak disangka hasil scrape terbaru. Lihat `runtime/source_health_summary.json` sebelum memakai katalog untuk keputusan penting.
- Source health menghitung konektivitas, data yang terkumpul, dan cakupan bukti; laporan tersebut bukan jaminan bahwa semua produk/ harga telah benar.
- Jika semua sumber tidak menghasilkan produk segar maupun data sebelumnya, pipeline berhenti agar katalog kosong tidak menimpa hasil yang valid sebelumnya.
- Sumber publik dapat mengubah struktur HTML atau membatasi akses. Tes offline tidak menjamin scraping live akan berhasil setiap saat.
- Proyek tidak mencoba melewati status HTTP 401/403/429 atau proteksi sumber.
