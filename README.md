# Merchant Promo Scraper

Versi source: **v11** — pencocokan SKU exact yang memahami kesetaraan satuan fisik, alias nama produk yang harus disetujui manual, dan daftar kandidat mirip untuk pemeriksaan tanpa menerapkan harga otomatis. Lihat [CHANGELOG.md](CHANGELOG.md) dan [AUDIT_UPGRADE_V11.md](AUDIT_UPGRADE_V11.md).

Pipeline Python untuk mengambil data promo dari halaman publik Hemat.id, Katalogpromosi.com, dan Scanharga.com. Proyek ini mengambil teks/HTML serta metadata gambar yang tersedia di halaman. **Poster hanya direferensikan lewat URL; gambar tidak dibaca, tidak di-OCR, dan tidak dipakai untuk menebak harga.**

## Perubahan v10 — integritas referensi harga & laporan katalog

- Referensi harga Hemat yang merchant-nya bertentangan dengan retailer pada URL katalog tidak lagi dipakai untuk pencocokan harga. Baris lama disimpan dalam `runtime/price_reference_quarantine.csv` dan ditampilkan pada sheet `Referensi Dikarantina`.
- Karantina bersifat persisten: workbook run berikutnya tetap menampilkan seluruh record karantina sebelumnya walaupun tidak ada konflik baru pada run tersebut.
- Sheet `Promo`, `Promo Aktif - Review`, dan `Perlu Diperiksa` dibuat saling eksklusif. Laporan JSON dan console menunjukkan jumlah tiap bucket agar overlap dapat direkonsiliasi. Sheet detail `Aktif`/`Perlu Review` tetap disimpan untuk audit lengkap.
- Freshness dicatat per sumber untuk produk lintas-sumber. `fresh_deduplicated_offer_records`, jumlah baris unik dengan sumber fresh, atribusi fresh per sumber, dan overlap atribusi kini dilaporkan terpisah.
- Pencocokan referensi tetap konservatif: identitas produk, ukuran, varian, retailer/kanal, dan umur data wajib cocok. Tidak ada fuzzy matching otomatis yang dapat menggabungkan SKU berbeda.

## Perubahan v11 — Smart SKU Matching

- Pencocokan referensi harga tetap exact, tetapi kini memahami satuan metrik yang ekuivalen: `1,8 L` = `1800 ml`, `1 kg` = `1000 g`, dan `2 x 0,5 L` = `2 x 500 ml`.
- Struktur kemasan tetap dibedakan: `2 x 500 ml` tidak disamakan dengan `1 L`, dan `10 x 27 g` tidak disamakan dengan `270 g`.
- Urutan token produk boleh berbeda jika semua token, merek, model, varian, dan ukuran tetap sama. Tidak ada fuzzy similarity yang boleh langsung mengisi harga.
- Alias nama produk hanya diterapkan jika tercatat di `config/product_name_aliases.csv` dengan `approved=true`, serta ukuran/kemasan dan varian sama. File alias kosong secara default; alias perlu ditinjau manusia sebelum disetujui.
- Kandidat nama yang mirip tetapi belum cocok exact ditulis ke `runtime/price_reference_match_candidates.csv`, lengkap dengan skor kemiripan, kecocokan ukuran/varian/merchant, URL bukti, dan alasan saran. **CSV ini hanya antrean review; harga kandidat tidak ditempel ke katalog.**
- Pencocokan unit-normalized yang sama juga digunakan oleh referensi pasar dan estimasi harga normal manual, sehingga format ukuran yang ekuivalen bisa ditemukan tanpa melonggarkan aturan SKU.

Format `config/product_name_aliases.csv`:

```csv
alias,canonical_name,approved,note
Sari Wangi Teh Celup 25 bags,SariWangi Teh Celup 25 bags,true,Alias merek sudah diperiksa
```

Jangan menambahkan alias hanya karena dua nama terlihat mirip. Pastikan merek, model, varian, ukuran, isi/pack, dan konteks produknya benar-benar sama. Baris dengan `approved` selain `true/yes/1/approved/setuju`, konflik alias, atau ukuran/varian berbeda akan diabaikan.

## Struktur proyek

```text
.
├── src/          # collector, validasi, referensi harga, health check, dan ekspor
├── tests/        # tes regresi offline
├── config/       # konfigurasi kategori dan alias SKU yang disetujui manual
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



### Integritas status promo, merchant, dan identitas produk (v9)

- Label `Expired`/`Kedaluwarsa` yang ditemukan pada konteks kartu produk disimpan sebagai bukti sumber dan mengalahkan tanggal akhir yang hanya hasil estimasi. Penawaran tersebut tidak dibawa kembali ke snapshot aktif.
- Konteks kartu Hemat dibatasi agar label status dari kartu tetangga tidak bocor ke produk lain.
- Untuk Hemat, prefix retailer pada URL item seperti `/katalog/alfamart.popok-dewasa-celana/` menjadi bukti merchant yang lebih kuat daripada label retailer pada wrapper halaman perbandingan. URL kategori generik seperti `/katalog/buah-mangga/` tidak digunakan untuk menebak merchant.
- Placeholder brand di awal nama (`None`, `null`, `undefined`, `nan`, `n/a`) dibuang dari nama produk yang dinormalisasi; teks mentah tetap tersimpan di field audit.
- Penawaran yang sama dengan beberapa tanggal estimasi berbeda tidak diperpanjang otomatis. Baris estimasi diturunkan menjadi `unknown` dan diarahkan ke review; periode eksplisit yang lebih kuat tetap dipertahankan.
- Penawaran `expired` tidak digabung dengan penawaran `active` lintas sumber. Dua catatan expired yang setara tetap boleh digabung sebagai bukti historis.

### Routing URL Hemat.id

Collector Hemat.id memulai pengambilan dari tujuh halaman retailer tunggal: Alfamart, Indomaret, Alfamidi, Super Indo, Hypermart, Yogya, dan Tip Top. Discovery hanya menerima slug retailer yang didukung tersebut (termasuk jalur `/promo-promo/` di bawah katalog retailer). URL perbandingan beberapa retailer seperti `/katalog-alfamart,yogya/` dan slug retailer yang belum didukung tidak diikuti agar atribusi merchant tidak tercampur.

Untuk URL yang ditampilkan di katalog, sistem mengutamakan `source_item_url` Hemat yang valid di `/harga/<slug>/`, `/harga-<slug>/`, atau `/katalog/<slug>/`. Jika record lama hanya memiliki URL perbandingan, katalog menggunakan halaman katalog tunggal berdasarkan merchant yang teridentifikasi. Jika merchant tidak dikenal, URL asli dipertahankan. Field provenance mentah tetap ada di snapshot dan audit; pemilihan ini hanya memengaruhi URL yang ditampilkan di katalog bersih.

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
run.bat --rebuild-from-last-snapshot
```

Bangun ulang katalog dari snapshot terakhir tanpa mengulang scraping live (berguna setelah memperbarui aturan validasi/normalisasi):

```bat
run.bat --rebuild-from-last-snapshot
```

Mode ini menjalankan pra-tes terlebih dahulu, lalu memproses `runtime/promo_multisource_products_all.csv`, membuat ulang workbook pencarian harga, dan memverifikasi output. Snapshot runtime lama harus tersedia.

Jalankan tes, scraping teks/HTML, health-check, konsolidasi, dan ekspor katalog:

```bat
run.bat
```

## Riwayat promo: snapshot versus history

Versi ini memisahkan **snapshot katalog berjalan** dari **riwayat promo permanen**:

- `runtime/promo_multisource_products_all.csv` berisi promo yang baru ditemukan dan promo lama yang masih layak dibawa ke snapshot.
- `state/promo_history.csv` adalah database permanen seluruh versi penawaran yang pernah ditemukan. Record di-upsert berdasarkan identitas produk, merchant, periode, harga, dan syarat penawaran; run berulang tidak membuat salinan identik.
- `output/Riwayat_Promo.csv` adalah ekspor yang mudah dibuka dari database riwayat. Promo `expired` dan versi `superseded` tetap ada di sini, bukan di daftar promo berjalan. Kolom `history_status_as_of` menunjukkan tanggal status itu dihitung.

Aturan retensi berbeda per sumber:

1. `Hemat.id`: maksimal 21 hari sejak terakhir terlihat.
2. `Katalogpromosi.com`: maksimal 14 hari.
3. `Scanharga.com`: maksimal 7 hari. Scanharga lebih banyak menghasilkan artikel dan referensi gambar daripada produk teks segar pada run yang dievaluasi; karena itu data yang hanya bersumber dari Scanharga tidak ditahan selama sumber produk utama.
4. Jika satu penawaran memiliki bukti dari beberapa sumber, batas retensi terpanjang yang relevan digunakan (misalnya Hemat + Scanharga = 21 hari); sumber tambahan tidak otomatis memendekkan umur data yang didukung Hemat.
5. Promo tanpa periode yang dapat dipastikan hanya dibawa maksimal 14 hari dan tidak pernah melewati batas sumber yang berlaku. Baris tetap berstatus `unknown`/review.
6. Promo yang sudah melewati tanggal akhir tidak masuk snapshot berjalan, tetapi tetap disimpan dengan `history_promo_status=expired`.
7. Penawaran yang tidak dibawa karena stale atau melewati masa review tetap ada di riwayat dengan `presence_status` dan `retention_reason` yang menjelaskan keputusan.
8. Jika produk, merchant, dan periode sama muncul lagi dengan harga/penawaran berbeda, versi lama ditandai `superseded` dan versi terbaru dipakai untuk snapshot.
9. Jika semua sumber gagal dan tidak ada data yang masih layak dibawa, snapshot terakhir tidak ditimpa file kosong. Riwayat tetap disimpan.

Laporan health kini membedakan peran sumber serta jumlah halaman artikel, artikel yang mengandung baris produk tekstual, jumlah produk yang diekstrak dari artikel, URL gambar, dan hasil produk segar per artikel. Jika Scanharga pada satu run menemukan setidaknya 10 artikel, maksimal 5 produk teks segar, dan memiliki URL gambar, perannya ditandai `discovery_support`; URL artikel/gambar tetap berguna untuk menemukan kampanye, tetapi tidak dianggap bukti harga produk.

### Cara membaca hitungan run

- `raw_product_rows_scraped_before_dedupe`: semua baris hasil ekstraksi pada run ini sebelum deduplikasi lintas halaman/sumber. Ini bukan jumlah produk unik.
- `fresh_deduplicated_offer_records`: penawaran unik yang benar-benar diamati pada run ini setelah deduplikasi. Ini ukuran yang lebih tepat untuk temuan baru.
- `carried_forward_rows`: penawaran lama yang dibawa ke snapshot karena masih dalam batas tanggal/retensi; bukan temuan baru.
- `product_rows_after_exact_dedup`: gabungan penawaran baru dan carry-forward setelah deduplikasi snapshot.
- `Kandidat aktif/estimasi sebelum validasi final`: hitungan tahap collector. Enricher berikutnya menerapkan konsolidasi lintas sumber dan quality gate, sehingga angka `Promo aktif/estimasi setelah konsolidasi dan gerbang kualitas` dapat lebih kecil.
- `Baris review` juga dicetak pada tahapnya masing-masing; bandingkan hanya metrik pada tahap yang sama.

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
7. Pencocokan referensi harga menerima identitas exact, token yang diurutkan ulang, satuan fisik ekuivalen dengan struktur multipack yang sama, atau alias yang disetujui manual. Kemiripan fuzzy hanya menghasilkan kandidat review; tidak pernah otomatis memasang harga. Ukuran, varian, merchant, wilayah/kanal, dan umur referensi tetap dijaga. Kolom diagnostik membedakan metode exact dan alasan tidak cocok.

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
- `runtime/price_reference_quarantine.csv` — referensi harga yang ditolak dari matching, tetapi dipertahankan sebagai bukti audit; workbook menampilkannya pada sheet `Referensi Dikarantina`.
- `runtime/price_reference_match_candidates.csv` — kandidat nama referensi yang mirip tetapi belum cocok exact; hanya untuk review manual dan tidak dipakai mengisi harga.
- `state/product_price_reference.csv` — observasi referensi harga normal dinamis.

Harga produk hanya diambil dari teks/HTML atau referensi halaman harga yang diverifikasi. Jika harga normal tidak tersedia atau tidak lolos validasi, nilainya dapat tetap kosong; proyek tidak menebak harga normal dari poster.

## Referensi harga pasar manual (opsional)

Setelah collector berjalan, `run.bat` otomatis membuat workbook pencarian harga manual. Isi workbook berdasarkan halaman harga langsung yang mencantumkan produk, ukuran/varian, harga, URL, dan bukti harga. Setelah disimpan, jalankan `run.bat --import-price-research`. Launcher memakai interpreter yang sama untuk mengimpor referensi, membangun ulang katalog dari snapshot terakhir (tanpa scraping live), membuat ulang workbook pencarian, dan memverifikasi hasilnya. Mode ini hanya memerlukan dependency runtime, bukan `pytest`. Referensi pasar tidak menggantikan harga promo sumber.

## Kualitas dan batasan

- Status health-check **partial** berarti ada sumber yang menggunakan data lama/carry-forward, tidak menghasilkan produk baru, atau mengalami error. Baris lama tetap ditandai agar tidak disangka hasil scrape terbaru. Lihat `runtime/source_health_summary.json` sebelum memakai katalog untuk keputusan penting.
- Source health menghitung konektivitas, data yang terkumpul, peran sumber, dan cakupan bukti; laporan tersebut bukan jaminan bahwa semua produk/harga telah benar.
- Produk yang dipertahankan dari run sebelumnya bukan produk baru. Selalu periksa `Kesegaran Data`, `presence_status`, dan alasan carry-forward sebelum menganggap suatu promo masih ditawarkan retailer.
- Jika semua sumber tidak menghasilkan produk segar maupun data sebelumnya, pipeline berhenti agar katalog kosong tidak menimpa hasil yang valid sebelumnya.
- Sumber publik dapat mengubah struktur HTML atau membatasi akses. Tes offline tidak menjamin scraping live akan berhasil setiap saat.
- Proyek tidak mencoba melewati status HTTP 401/403/429 atau proteksi sumber.
