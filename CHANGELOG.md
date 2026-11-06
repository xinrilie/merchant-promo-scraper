# Riwayat Perubahan

## 6 November 2026
- Menggabungkan 27 modul tes menjadi 13 modul tematik; seluruh 219 kasus pytest tetap dipertahankan.
- Menghapus dua fungsi `main()` ad-hoc di file tes karena seluruh eksekusi tes sudah dilakukan oleh pytest.
- Memperbarui paket lokal dengan seluruh file output terbaru dari arsip output yang diberikan; folder runtime dan state lama tetap dipertahankan.
- Paket source untuk GitHub tetap bersih dari output, runtime, state, cache, dan virtual environment.

## 6 November 2026
- Percepatan pencocokan referensi harga dengan indeks SKU yang dinormalisasi sekali per batch, bukan menormalisasi seluruh referensi untuk setiap baris katalog.
- Pencarian kandidat SKU memakai inverted token index agar hanya membandingkan referensi yang memiliki token produk yang relevan. Kandidat fuzzy tetap untuk review dan tidak pernah memasang harga otomatis.
- LIVE 3/4 kini menampilkan durasi pembaruan database, pencocokan SKU, pembandingan harga, quality gate, ekspor, dan total proses.
- Menghapus ekspor CSV aktif/review mentah yang menduplikasi snapshot utama, serta CSV confirmed/review turunan yang sudah tersedia di workbook dan audit penuh.
- Workbook tidak lagi membuat tab audit penuh yang menduplikasi CSV katalog lengkap; pemformatan sel dibuat lebih efisien dengan style yang dipakai ulang.
- Nama file tes dibuat deskriptif tanpa akhiran nomor rilis.

## Fitur yang dipertahankan
- Scraping teks/HTML dan pencatatan URL gambar tanpa OCR.
- Riwayat promo permanen, carry-forward berbatas waktu, dan pemisahan expired dari katalog aktif.
- Validasi bukti harga, merchant, periode, kategori, dan quality gate sebelum ekspor.
- Referensi harga manual, karantina referensi bermasalah, alias SKU yang disetujui, dan kandidat pencocokan fuzzy untuk review.
- Launcher Windows yang memakai Python global dan tidak membuat virtual environment atau memasang dependency otomatis.
