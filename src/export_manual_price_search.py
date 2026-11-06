"""Export product rows that still need a sourced manual market-price check.

This workflow does not generate or consume AI price estimates. Poster images are
stored as references only; this workflow compares prices from direct text/page evidence.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from promo_price_reference import identity_key
from promo_names import clean_product_name

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "runtime" / "promo_multisource_products_all.csv"
OUT = ROOT / "output" / "Daftar_Cari_Harga_Manual.xlsx"
CATALOG_CANDIDATES = (
    ROOT / "output" / "Katalog_Promo_Final_Ringkas.csv",
    ROOT / "output" / "Katalog_Promo_Final.csv",
)
GENERIC_NON_PRODUCT_NAME_RE = re.compile(
    r"^(?:produk(?:\s+(?:belum\s+teridentifikasi|pilihan|tertentu))?|item\s+pilihan|"
    r"potongan(?:\s+harga)?|harga\s+(?:promo|spesial|normal)|promo(?:si)?|diskon|"
    r"min(?:imum)?\.?\s*(?:belanja|pembelanjaan|transaksi)|syarat\s+belanja|"
    r"penawaran\s+(?:menarik|spesial))$", re.I,
)
HEADERS = [
    "ID Produk", "Nama Produk", "Merchant Promo", "Harga Promo (Rp)",
    "Kata Kunci Pencarian (copy)", "Harga Referensi (Rp) - isi manual",
    "Nama Sumber", "URL Halaman Harga", "Bukti Harga pada Halaman",
    "Tanggal Cek (YYYY-MM-DD)", "Jenis Referensi (pasar/normal)",
    "Retailer Pembanding", "Klasifikasi Harga (normal_before_promo/regular_no_promo/promo/historical_average_3m/historical_min/unclear)",
    "Tanggal Terakhir Dicek oleh Sumber (YYYY-MM-DD)",
    "Kecocokan SKU (exact/close/unknown)", "Catatan Verifikasi", "Status"
]


def _main_catalog_product_keys():
    for path in CATALOG_CANDIDATES:
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                headers = set(reader.fieldnames or [])
                field = "Nama Produk" if "Nama Produk" in headers else ("product_text" if "product_text" in headers else None)
                if not field:
                    continue
                keys = {identity_key(row.get(field, "")) for row in reader if identity_key(row.get(field, ""))}
                if keys:
                    return keys, True
        except (OSError, csv.Error):
            continue
    return set(), False


def _make_search_row(name: str, merchant: str, promo: str, idx: int, status: str = "BELUM DICARI", note: str = ""):
    return {
        "ID Produk": f"{idx:05d}",
        "Nama Produk": name,
        "Merchant Promo": merchant,
        "Harga Promo (Rp)": promo,
        "Kata Kunci Pencarian (copy)": f'"{name}" harga',
        "Harga Referensi (Rp) - isi manual": "",
        "Nama Sumber": "",
        "URL Halaman Harga": "",
        "Bukti Harga pada Halaman": "",
        "Tanggal Cek (YYYY-MM-DD)": "",
        "Jenis Referensi (pasar/normal)": "pasar",
        "Retailer Pembanding": "",
        "Klasifikasi Harga (normal_before_promo/regular_no_promo/promo/historical_average_3m/historical_min/unclear)": "",
        "Tanggal Terakhir Dicek oleh Sumber (YYYY-MM-DD)": "",
        "Kecocokan SKU (exact/close/unknown)": "unknown",
        "Catatan Verifikasi": note,
        "Status": status,
    }


def read_products():
    if not SOURCE.exists():
        raise SystemExit(f"Data produk belum ada: {SOURCE}\nJalankan scraping terlebih dahulu.")
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    out, seen_source_rows, seen_products = [], set(), set()
    catalog_keys, catalog_gate_enabled = _main_catalog_product_keys()
    stats = {
        "source_candidates": 0, "duplicate_products": 0, "excluded_not_in_catalog": 0,
        "excluded_not_eligible": 0, "excluded_generic": 0,
        "excluded_with_normal_price": 0, "catalog_gate_enabled": catalog_gate_enabled,
        "outside_catalog_rows": [],
    }
    for row in rows:
        name = str(row.get("product_text") or "").strip()
        promo = str(row.get("promo_price") or "").strip()
        merchant = str(row.get("merchant_name") or "").strip()
        if not name or not promo:
            continue
        key = (identity_key(name), merchant.casefold(), promo)
        if key in seen_source_rows:
            continue
        seen_source_rows.add(key)
        if str(row.get("normal_price") or "").strip():
            stats["excluded_with_normal_price"] += 1
            continue
        stats["source_candidates"] += 1
        status = str(row.get("product_validation_status") or "").strip().casefold()
        if status and status != "eligible":
            stats["excluded_not_eligible"] += 1
            continue
        clean_name = clean_product_name(name).strip().strip(" .:-–—")
        if not clean_name or GENERIC_NON_PRODUCT_NAME_RE.fullmatch(clean_name):
            stats["excluded_generic"] += 1
            continue
        if catalog_gate_enabled and identity_key(name) not in catalog_keys:
            stats["excluded_not_in_catalog"] += 1
            stats["outside_catalog_rows"].append(_make_search_row(
                clean_name, merchant, promo, len(stats["outside_catalog_rows"]) + 1,
                status="DI LUAR KATALOG - REVIEW",
                note="Produk ditemukan di snapshot sumber tetapi tidak masuk katalog utama saat run ini. Jangan impor sebelum memeriksa status, periode, dan kelayakan produknya.",
            ))
            continue
        slot = (identity_key(name), merchant.casefold(), promo)
        if slot in seen_products:
            stats["duplicate_products"] += 1
            continue
        seen_products.add(slot)
        out.append(_make_search_row(name, merchant, promo, len(out) + 1))
    return out, stats


def main():
    products, stats = read_products()
    outside_catalog_rows = stats.pop("outside_catalog_rows", [])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    existing_outside = {}
    if OUT.exists():
        try:
            old = load_workbook(OUT, read_only=True, data_only=True)
            for sheet_name, target in (("Cari Harga", existing), ("Di Luar Katalog", existing_outside)):
                if sheet_name not in old.sheetnames:
                    continue
                ws_old = old[sheet_name]
                header = [cell.value for cell in ws_old[1]]
                for values in ws_old.iter_rows(min_row=2, values_only=True):
                    old_row = dict(zip(header, values))
                    key = (
                        str(old_row.get("Nama Produk") or "").casefold(),
                        str(old_row.get("Merchant Promo") or "").casefold(),
                        str(old_row.get("Harga Promo (Rp)") or ""),
                    )
                    if key[0]:
                        target[key] = old_row
            old.close()
        except Exception:
            pass
    merged = []
    seen = set()
    for row in products:
        key = (row["Nama Produk"].casefold(), row["Merchant Promo"].casefold(), str(row["Harga Promo (Rp)"]))
        if key in seen:
            continue
        seen.add(key)
        old_row = existing.get(key)
        if old_row and any(old_row.get(field) for field in (
            "Harga Referensi (Rp) - isi manual", "URL Halaman Harga", "Bukti Harga pada Halaman"
        )):
            row.update({header: old_row.get(header, row.get(header, "")) for header in HEADERS})
            complete = all(str(row.get(field) or "").strip() for field in (
                "Harga Referensi (Rp) - isi manual", "Nama Sumber", "URL Halaman Harga",
                "Bukti Harga pada Halaman", "Tanggal Cek (YYYY-MM-DD)"
            ))
            row["Status"] = "SIAP DIIMPOR" if complete else "PERIKSA ISIAN"
        merged.append(row)

    wb = Workbook()
    ws = wb.active
    ws.title = "Cari Harga"
    ws.append(HEADERS)
    for row in merged:
        ws.append([row.get(header, "") for header in HEADERS])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    ws.row_dimensions[1].height = 32
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="244062")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    widths = [12, 38, 23, 18, 48, 24, 24, 48, 54, 20, 25, 24, 55, 31, 24, 42, 18]
    for idx, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column in {2, 5, 7, 8, 9})

    outside_merged = []
    outside_seen = set()
    for row in outside_catalog_rows:
        key = (row["Nama Produk"].casefold(), row["Merchant Promo"].casefold(), str(row["Harga Promo (Rp)"]))
        if key in outside_seen:
            continue
        outside_seen.add(key)
        old_row = existing_outside.get(key)
        if old_row and any(old_row.get(field) for field in (
            "Harga Referensi (Rp) - isi manual", "URL Halaman Harga", "Bukti Harga pada Halaman"
        )):
            row.update({header: old_row.get(header, row.get(header, "")) for header in HEADERS})
            complete = all(str(row.get(field) or "").strip() for field in (
                "Harga Referensi (Rp) - isi manual", "Nama Sumber", "URL Halaman Harga",
                "Bukti Harga pada Halaman", "Tanggal Cek (YYYY-MM-DD)"
            ))
            row["Status"] = "PERIKSA ISIAN" if not complete else "REVIEW DI LUAR KATALOG"
        outside_merged.append(row)

    outside_ws = wb.create_sheet("Di Luar Katalog")
    outside_ws.append(HEADERS)
    for row in outside_merged:
        outside_ws.append([row.get(header, "") for header in HEADERS])
    outside_ws.freeze_panes = "A2"
    outside_ws.auto_filter.ref = outside_ws.dimensions
    outside_ws.row_dimensions[1].height = 32
    for cell in outside_ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="8064A2")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for idx, width in enumerate(widths, 1):
        outside_ws.column_dimensions[get_column_letter(idx)].width = width
    for row in outside_ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column in {2, 5, 7, 8, 9, 16})

    helpws = wb.create_sheet("Petunjuk")
    help_text = [
        "CARA PAKAI DAFTAR CARI HARGA PASAR",
        "1. Daftar ini hanya untuk produk yang belum memiliki harga normal eksplisit dari teks sumber promo.",
        "2. Prioritaskan halaman detail Hemat.id /harga/ untuk SKU, varian, ukuran dan isi yang sama persis.",
        "3. Harga normal sebelum promo hanya boleh dicatat jika sumber menampilkan harga tersebut secara eksplisit.",
        "4. Rata-rata historis 3 bulan Hemat.id dapat dicatat sebagai historical_average_3m, tetapi keyakinannya rendah karena periode historis dapat mencakup harga promo.",
        "5. Jika Hemat.id tidak menyediakan bukti yang cukup, Tokku hanya boleh diperiksa manual untuk sejumlah kecil produk yang belum memiliki harga. Tidak ada collector otomatis Tokku.",
        "6. Untuk Tokku, gunakan halaman produk /id/product/ yang cocok persis; catat satu retailer per baris, tanggal terakhir dicek oleh Tokku, klasifikasi harga dan URL halaman.",
        "7. Harga Tokku yang terakhir dicek lebih dari 30 hari lalu tetap boleh dicatat untuk arsip, tetapi tidak dipakai sebagai estimasi harga normal terkini.",
        "8. Harga promo, harga terendah historis dan harga yang klasifikasinya tidak jelas tidak boleh diperlakukan sebagai harga normal.",
        "9. Harga referensi/estimasi disimpan terpisah dan tidak menimpa Harga Asli dari sumber promo atau menghitung diskon resmi.",
        "10. Gandakan baris untuk retailer/domain independen. Cocokkan merek, SKU, varian, ukuran, isi, serta kondisi kemasan sebelum mengisi.",
        r"11. Simpan dan tutup Excel, kemudian jalankan: python src\import_manual_price_references.py output\Daftar_Cari_Harga_Manual.xlsx",
        "12. Sheet Di Luar Katalog berisi kandidat dari snapshot sumber yang tidak masuk katalog utama; sheet ini hanya untuk review, bukan antrean impor otomatis.",
        "13. Tidak ada pembacaan OCR poster/gambar. URL gambar hanya disimpan sebagai referensi visual.",
    ]
    for line in help_text:
        helpws.append([line])
    helpws.column_dimensions["A"].width = 150
    from openpyxl.worksheet.datavalidation import DataValidation
    classification_col = HEADERS.index("Klasifikasi Harga (normal_before_promo/regular_no_promo/promo/historical_average_3m/historical_min/unclear)") + 1
    match_col = HEADERS.index("Kecocokan SKU (exact/close/unknown)") + 1
    dv_class = DataValidation(type="list", formula1='"normal_before_promo,regular_no_promo,promo,historical_average_3m,historical_min,unclear"', allow_blank=True)
    dv_match = DataValidation(type="list", formula1='"exact,close,unknown"', allow_blank=True)
    ws.add_data_validation(dv_class)
    ws.add_data_validation(dv_match)
    dv_class.add(f"{get_column_letter(classification_col)}2:{get_column_letter(classification_col)}2000")
    dv_match.add(f"{get_column_letter(match_col)}2:{get_column_letter(match_col)}2000")
    for row in helpws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    wb.save(OUT)
    print(f"Daftar pencarian harga pasar dibuat: {OUT}")
    print(f"Produk tanpa harga normal untuk diteliti: {len(merged)}")
    print(f"Produk yang sudah punya harga normal disaring: {stats['excluded_with_normal_price']}")
    print(f"Produk di luar katalog utama dipisahkan ke sheet review: {stats['excluded_not_in_catalog']}")
    print(f"Produk non-eligible/review dilewati: {stats['excluded_not_eligible']}")
    print(f"Nama generik/non-SKU dilewati: {stats['excluded_generic']}")
    print("Tidak ada antrean AI atau file prompt estimasi yang dibuat.")


if __name__ == "__main__":
    main()
