# Changelog

## 2026-11-03 — Audit dan maintenance

- Hemat.id menggunakan halaman katalog per retailer; halaman comparison yang mengandung beberapa retailer ditolak dari link discovery.
- `Sumber URL` katalog diprioritaskan ke link item/kategori yang lebih spesifik; URL asal mentah tetap disimpan di data teknis.
- Menambahkan `run.bat --rebuild-from-last-snapshot` untuk membangun ulang katalog tanpa request web.
- Menghapus dua ekspor mentah collector yang duplikat dan tidak dipakai: `promo_multisource_products_active.csv` dan `promo_multisource_products_review.csv`.
- Workbook riset harga manual kini hanya dibuat saat diminta.
- Memperbarui baseline versi dependency dan minimum Python 3.11.
- Memperbaiki loop pencarian Python global pada launcher dan menghapus impor duplikat.
- Tetap scrape-only: tidak ada OCR, instalasi otomatis, atau pembuatan venv.
