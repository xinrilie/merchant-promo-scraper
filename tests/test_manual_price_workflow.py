import csv
import pytest
from openpyxl import Workbook

import import_manual_price_references as importer


def _workbook(path, row):
    wb = Workbook()
    ws = wb.active
    ws.title = "Cari Harga"
    headers = [
        "Nama Produk", "Harga Referensi (Rp) - isi manual", "Nama Sumber", "URL Halaman Harga",
        "Bukti Harga pada Halaman", "Tanggal Cek (YYYY-MM-DD)", "Jenis Referensi (pasar/normal)",
        "Judul Halaman", "Retailer Pembanding",
        "Klasifikasi Harga (normal_before_promo/regular_no_promo/promo/historical_average_3m/historical_min/unclear)",
        "Tanggal Terakhir Dicek oleh Sumber (YYYY-MM-DD)",
        "Kecocokan SKU (exact/close/unknown)", "Catatan Verifikasi",
    ]
    ws.append(headers)
    if isinstance(row, dict):
        ws.append([row.get(header, "") for header in headers])
    else:
        ws.append(list(row) + [""] * (len(headers) - len(row)))
    wb.save(path)


def test_price_parser_indonesian():
    assert importer.price_int("Rp 22.900") == 22900
    assert importer.price_int("16.900") == 16900
    assert importer.price_int("0") is None


def test_import_manual_market_reference(tmp_path, monkeypatch):
    xlsx = tmp_path / "market.xlsx"
    db = tmp_path / "market.csv"
    _workbook(xlsx, ["Sunlight Lime 910 ml", "16900", "Toko Contoh", "https://shop.example/product", "Sunlight Lime 910 ml harga normal Rp16.900", "2026-10-25", "pasar", "Sunlight Lime 910 ml"])
    monkeypatch.setattr(importer, "XLSX", xlsx)
    monkeypatch.setattr(importer, "DB", db)
    importer.DB = db
    importer.main([str(xlsx)])
    rows = list(csv.DictReader(db.open(encoding="utf-8-sig")))
    assert len(rows) == 1
    assert rows[0]["market_price"] == "16900"
    assert rows[0]["source_kind"] == "manual_user_checked"
    assert rows[0]["verification_method"] == "page_price_verified"


def test_ai_json_is_explicitly_rejected(tmp_path):
    json_file = tmp_path / "old-estimates.json"
    json_file.write_text('{"estimates": [{"product_name": "Product X", "estimated_price": 15000}]}', encoding="utf-8")
    with pytest.raises(SystemExit, match="estimasi AI sudah dihapus"):
        importer.main([str(json_file)])


def test_incomplete_manual_market_reference_is_not_imported(tmp_path):
    xlsx = tmp_path / "market.xlsx"
    _workbook(xlsx, ["Product X 500 g", "15000", "Shop", "", "Harga 15000", "2026-10-25", "pasar", "Product X"])
    entries, errors, total = importer._read_xlsx(xlsx)
    assert total == 1
    assert entries == []
    assert any("URL harus berupa URL halaman" in error for error in errors)



def test_tokku_manual_regular_price_requires_exact_sku_and_source_checked_date(tmp_path):
    row = {
        "Nama Produk": "Sania Minyak Goreng Pouch 2 L",
        "Harga Referensi (Rp) - isi manual": "Rp23.300",
        "Nama Sumber": "Tokku",
        "URL Halaman Harga": "https://tokku.app/id/product/sania-minyak-goreng-pouch-2-l-example",
        "Bukti Harga pada Halaman": "Lotte Mart: Rp21.000 harga saat ini; harga normal tercoret Rp23.300; promo -10%",
        "Tanggal Cek (YYYY-MM-DD)": "2026-11-03",
        "Jenis Referensi (pasar/normal)": "pasar",
        "Judul Halaman": "Sania Minyak Goreng Pouch 2 L",
        "Retailer Pembanding": "Lotte Mart",
        "Klasifikasi Harga (normal_before_promo/regular_no_promo/promo/historical_average_3m/historical_min/unclear)": "normal_before_promo",
        "Tanggal Terakhir Dicek oleh Sumber (YYYY-MM-DD)": "2026-11-01",
        "Kecocokan SKU (exact/close/unknown)": "exact",
        "Catatan Verifikasi": "Ukuran dan varian cocok.",
    }
    normalized, error = importer._normalize_input_row(row, 2)
    assert error is None
    assert normalized["price_kind"] == "regular"
    assert normalized["source_kind"] == "manual_tokku_checked"
    assert normalized["retailer_name"] == "Lotte Mart"
    assert normalized["source_checked_at"] == "2026-11-01"


def test_tokku_manual_reference_rejects_non_exact_or_missing_source_date():
    base = {
        "Nama Produk": "Sania Minyak Goreng Pouch 2 L",
        "Harga Referensi (Rp) - isi manual": "23300",
        "Nama Sumber": "Tokku",
        "URL Halaman Harga": "https://tokku.app/id/product/sania-example",
        "Bukti Harga pada Halaman": "Lotte Mart harga normal Rp23.300",
        "Tanggal Cek (YYYY-MM-DD)": "2026-11-03",
        "Jenis Referensi (pasar/normal)": "pasar",
        "Retailer Pembanding": "Lotte Mart",
        "Klasifikasi Harga (normal_before_promo/regular_no_promo/promo/historical_average_3m/historical_min/unclear)": "normal_before_promo",
        "Tanggal Terakhir Dicek oleh Sumber (YYYY-MM-DD)": "",
        "Kecocokan SKU (exact/close/unknown)": "close",
    }
    normalized, error = importer._normalize_input_row(base, 2)
    assert normalized is None
    assert "tanggal 'Dicek'" in error
    assert "cocok exact" in error


def test_tokku_source_price_older_than_30_days_is_not_used_for_current_estimate():
    from datetime import date
    from promo_market_prices import _normalize_record, estimate_normal_prices_from_references
    from promo_price_reference import identity_key
    from promo_names import product_name_size_signature, product_name_variant_signature

    name = "Sania Minyak Goreng Pouch 2 L"
    reference = _normalize_record({
        "product_text": name, "product_key": identity_key(name),
        "size_signature": "|".join(product_name_size_signature(name)),
        "variant_signature": "|".join(sorted(product_name_variant_signature(name))),
        "market_price": "23300", "observed_at": "2026-11-03",
        "source_name": "Tokku", "source_domain": "tokku.app",
        "source_url": "https://tokku.app/id/product/sania-example",
        "evidence_text": "Lotte Mart harga normal Rp23.300", "price_kind": "regular",
        "source_kind": "manual_tokku_checked", "verification_method": "page_price_verified",
        "retailer_name": "Lotte Mart", "source_checked_at": "2026-07-20",
        "price_classification": "normal_before_promo", "product_match_status": "exact",
    })
    row = {"product_text": name, "promo_price": 20000, "normal_price": None,
           "reference_normal_price": None, "product_validation_status": "eligible"}
    summary = estimate_normal_prices_from_references([row], [reference], today=date(2026, 11, 3))
    assert summary["rows_estimated"] == 0
    assert row.get("estimated_normal_price") is None


def test_tokku_regular_exact_prices_estimate_normal_market_price_without_overwriting_original():
    from datetime import date
    from promo_market_prices import _normalize_record, estimate_normal_prices_from_references
    from promo_price_reference import identity_key
    from promo_names import product_name_size_signature, product_name_variant_signature

    name = "Sania Minyak Goreng Pouch 2 L"
    references = []
    for retailer, price in (("Lotte Mart", 23300), ("Segari", 23400), ("Yogya Online", 23750)):
        references.append(_normalize_record({
            "product_text": name, "product_key": identity_key(name),
            "size_signature": "|".join(product_name_size_signature(name)),
            "variant_signature": "|".join(sorted(product_name_variant_signature(name))),
            "market_price": str(price), "observed_at": "2026-11-03",
            "source_name": "Tokku", "source_domain": "tokku.app",
            "source_url": "https://tokku.app/id/product/sania-example",
            "evidence_text": f"{retailer}: harga normal Rp{price:,}", "price_kind": "regular",
            "source_kind": "manual_tokku_checked", "verification_method": "page_price_verified",
            "retailer_name": retailer, "source_checked_at": "2026-11-02",
            "price_classification": "normal_before_promo", "product_match_status": "exact",
        }))
    row = {"product_text": name, "promo_price": 20000, "normal_price": None,
           "reference_normal_price": None, "product_validation_status": "eligible"}
    summary = estimate_normal_prices_from_references([row], references, today=date(2026, 11, 3))
    assert summary["rows_estimated"] == 1
    assert row["estimated_normal_price"] == 23400
    assert row["estimated_normal_low"] == 23300
    assert row["estimated_normal_high"] == 23750
    assert row["estimated_normal_confidence"] == "medium"
    assert row["normal_price"] is None  # Never masquerade as the promo's official original price.


def test_historical_average_is_a_low_confidence_fallback_not_original_price():
    from datetime import date
    from promo_market_prices import _normalize_record, estimate_normal_prices_from_references
    from promo_price_reference import identity_key
    from promo_names import product_name_size_signature, product_name_variant_signature

    name = "Bimoli Minyak Goreng Spesial 2 L"
    reference = _normalize_record({
        "product_text": name, "product_key": identity_key(name),
        "size_signature": "|".join(product_name_size_signature(name)),
        "variant_signature": "|".join(sorted(product_name_variant_signature(name))),
        "market_price": "43271", "observed_at": "2026-11-03",
        "source_name": "Hemat.id", "source_domain": "hemat.id",
        "source_url": "https://www.hemat.id/harga/bimoli-example",
        "evidence_text": "Harga rata-rata berdasarkan 3 bulan terakhir Rp43.271",
        "price_kind": "historical_average", "source_kind": "manual_user_checked",
        "verification_method": "page_price_verified", "source_checked_at": "2026-11-03",
    })
    row = {"product_text": name, "promo_price": 41500, "normal_price": None,
           "reference_normal_price": None, "product_validation_status": "eligible"}
    summary = estimate_normal_prices_from_references([row], [reference], today=date(2026, 11, 3))
    assert summary["historical_average_estimates"] == 1
    assert row["estimated_normal_price"] == 43271
    assert row["estimated_normal_confidence"] == "low"
    assert "dapat mencakup harga promo" in row["estimated_normal_note"]



def test_tokku_multiple_retailers_on_same_product_page_are_not_overwritten(tmp_path):
    from promo_market_prices import _normalize_record, load_market_reference_database, upsert_market_reference_database
    from promo_price_reference import identity_key
    from promo_names import product_name_size_signature, product_name_variant_signature

    path = tmp_path / "state" / "market.csv"
    name = "Sania Minyak Goreng Pouch 2 L"
    rows = []
    for retailer, price in (("Lotte Mart", 23300), ("Segari", 23400)):
        rows.append(_normalize_record({
            "product_text": name, "product_key": identity_key(name),
            "size_signature": "|".join(product_name_size_signature(name)),
            "variant_signature": "|".join(sorted(product_name_variant_signature(name))),
            "market_price": str(price), "observed_at": "2026-11-03",
            "source_name": "Tokku", "source_domain": "tokku.app",
            "source_url": "https://tokku.app/id/product/sania-example",
            "evidence_text": f"{retailer}: harga normal Rp{price:,}", "price_kind": "regular",
            "source_kind": "manual_tokku_checked", "verification_method": "page_price_verified",
            "retailer_name": retailer, "source_checked_at": "2026-11-02",
            "price_classification": "normal_before_promo", "product_match_status": "exact",
        }))
    summary = upsert_market_reference_database(path, rows)
    stored = load_market_reference_database(path)
    assert summary["records_added"] == 2
    assert len(stored) == 2
    assert {item["retailer_name"] for item in stored} == {"Lotte Mart", "Segari"}


def test_promo_price_classification_is_not_used_for_normal_estimate():
    from datetime import date
    from promo_market_prices import _normalize_record, estimate_normal_prices_from_references
    from promo_price_reference import identity_key
    from promo_names import product_name_size_signature, product_name_variant_signature

    name = "Sania Minyak Goreng Pouch 2 L"
    reference = _normalize_record({
        "product_text": name, "product_key": identity_key(name),
        "size_signature": "|".join(product_name_size_signature(name)),
        "variant_signature": "|".join(sorted(product_name_variant_signature(name))),
        "market_price": "21000", "observed_at": "2026-11-03",
        "source_name": "Tokku", "source_domain": "tokku.app",
        "source_url": "https://tokku.app/id/product/sania-example",
        "evidence_text": "Lotte Mart harga promo Rp21.000 -10%", "price_kind": "promo",
        "source_kind": "manual_tokku_checked", "verification_method": "page_price_verified",
        "retailer_name": "Lotte Mart", "source_checked_at": "2026-11-02",
        "price_classification": "promo", "product_match_status": "exact",
    })
    row = {"product_text": name, "promo_price": 21000, "normal_price": None,
           "reference_normal_price": None, "product_validation_status": "eligible"}
    summary = estimate_normal_prices_from_references([row], [reference], today=date(2026, 11, 3))
    assert summary["rows_estimated"] == 0
    assert row["estimated_normal_price"] is None



def test_tokku_importer_keeps_price_classification_and_retailer(tmp_path, monkeypatch):
    xlsx = tmp_path / "tokku.xlsx"
    db = tmp_path / "state" / "market.csv"
    row = {
        "Nama Produk": "Sania Minyak Goreng Pouch 2 L",
        "Harga Referensi (Rp) - isi manual": "23300",
        "Nama Sumber": "Tokku",
        "URL Halaman Harga": "https://tokku.app/id/product/sania-minyak-goreng-pouch-2-l-test",
        "Bukti Harga pada Halaman": "Lotte Mart: harga normal tercoret Rp23.300; dicek 2 Nov 2026",
        "Tanggal Cek (YYYY-MM-DD)": "2026-11-03",
        "Jenis Referensi (pasar/normal)": "pasar",
        "Judul Halaman": "Sania Minyak Goreng Pouch 2 L",
        "Retailer Pembanding": "Lotte Mart",
        "Klasifikasi Harga (normal_before_promo/regular_no_promo/promo/historical_average_3m/historical_min/unclear)": "normal_before_promo",
        "Tanggal Terakhir Dicek oleh Sumber (YYYY-MM-DD)": "2026-11-02",
        "Kecocokan SKU (exact/close/unknown)": "exact",
        "Catatan Verifikasi": "Varian dan ukuran sama persis.",
    }
    _workbook(xlsx, row)
    monkeypatch.setattr(importer, "DB", db)
    importer.main([str(xlsx)])
    rows = list(csv.DictReader(db.open(encoding="utf-8-sig")))
    assert len(rows) == 1
    assert rows[0]["price_kind"] == "regular"
    assert rows[0]["retailer_name"] == "Lotte Mart"
    assert rows[0]["source_checked_at"] == "2026-11-02"
    assert rows[0]["product_match_status"] == "exact"


def test_tokku_manual_category_url_is_rejected():
    row = {
        "Nama Produk": "Sania Minyak Goreng Pouch 2 L",
        "Harga Referensi (Rp) - isi manual": "23300",
        "Nama Sumber": "Tokku",
        "URL Halaman Harga": "https://tokku.app/id/category/cooking",
        "Bukti Harga pada Halaman": "Sania 2 L Rp23.300",
        "Tanggal Cek (YYYY-MM-DD)": "2026-11-03",
        "Jenis Referensi (pasar/normal)": "pasar",
        "Retailer Pembanding": "Lotte Mart",
        "Klasifikasi Harga (normal_before_promo/regular_no_promo/promo/historical_average_3m/historical_min/unclear)": "regular_no_promo",
        "Tanggal Terakhir Dicek oleh Sumber (YYYY-MM-DD)": "2026-11-02",
        "Kecocokan SKU (exact/close/unknown)": "exact",
    }
    normalized, error = importer._normalize_input_row(row, 2)
    assert normalized is None
    assert "halaman detail produk" in error


def test_market_reference_seed_migrates_to_local_state_only_once(tmp_path):
    from promo_market_prices import initialize_market_reference_database, load_market_reference_database, MARKET_REFERENCE_FIELDS
    seed = tmp_path / "data" / "product_market_price_reference.csv"
    target = tmp_path / "state" / "product_market_price_reference.csv"
    seed.parent.mkdir(parents=True)
    headers = [field for field in MARKET_REFERENCE_FIELDS if field not in {"retailer_name", "source_checked_at", "price_classification", "product_match_status"}]
    with seed.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerow({
            "product_text": "Sunlight Lime 910 ml", "market_price": "16900",
            "observed_at": "2026-11-01", "source_name": "Toko Contoh",
            "source_domain": "shop.example", "source_url": "https://shop.example/sunlight",
            "evidence_text": "Sunlight Lime 910 ml Rp16.900", "price_kind": "market",
            "verification_method": "page_price_verified",
        })
    assert initialize_market_reference_database(target, seed) == "migrated_seed"
    loaded = load_market_reference_database(target)
    assert len(loaded) == 1
    assert loaded[0]["market_price"] == "16900"
    assert initialize_market_reference_database(target, seed) == "existing"
