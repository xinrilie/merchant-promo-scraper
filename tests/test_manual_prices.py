"""Grouped regression tests. Cases are organized by functional area."""



import csv

import export_manual_price_search as exporter

import pytest

from openpyxl import Workbook

import import_manual_price_references as importer



# --- from test_export_manual_price_search.py ---
def _write_csv(path, rows):
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

# --- from test_export_manual_price_search.py ---
def test_market_search_excludes_generic_review_and_non_catalog_rows_but_keeps_new_categories(tmp_path, monkeypatch):
    source = tmp_path / "products.csv"
    catalog = tmp_path / "Katalog_Promo_Final_Ringkas.csv"
    _write_csv(source, [
        {"product_text": "Sunlight Lime 910 ml", "promo_price": "16900", "normal_price": "", "merchant_name": "Shop A", "source_name": "Shop A", "product_validation_status": "eligible", "source_url": "https://example.test/promo"},
        {"product_text": "All Fruit", "promo_price": "12000", "normal_price": "", "merchant_name": "Shop B", "product_validation_status": "eligible", "source_url": "https://example.test/promo2"},
        {"product_text": "Harga spesial", "promo_price": "50000", "normal_price": "", "merchant_name": "Foodhall", "product_validation_status": "eligible", "source_url": "https://example.test/promo3"},
        {"product_text": "All Sayur", "promo_price": "9000", "normal_price": "", "merchant_name": "Shop C", "product_validation_status": "review", "source_url": "https://example.test/promo4"},
        {"product_text": "Produk tidak ada di katalog", "promo_price": "10000", "normal_price": "", "merchant_name": "Shop D", "product_validation_status": "eligible", "source_url": "https://example.test/promo5"},
    ])
    _write_csv(catalog, [
        {"Nama Produk": "Sunlight Lime 910 ml"},
        {"Nama Produk": "All Fruit"},
        {"Nama Produk": "Harga spesial"},
        {"Nama Produk": "All Sayur"},
    ])
    monkeypatch.setattr(exporter, "SOURCE", source)
    monkeypatch.setattr(exporter, "CATALOG_CANDIDATES", (catalog,))

    products, stats = exporter.read_products()

    assert {row["Nama Produk"] for row in products} == {"Sunlight Lime 910 ml", "All Fruit"}
    assert stats["excluded_generic"] == 1
    assert stats["excluded_not_eligible"] == 1
    assert stats["excluded_not_in_catalog"] == 1
    assert "All Fruit" in {row["Nama Produk"] for row in products}

# --- from test_export_manual_price_search.py ---
def test_image_reference_cannot_supply_a_normal_price(tmp_path, monkeypatch):
    source = tmp_path / "products.csv"
    catalog = tmp_path / "Katalog_Promo_Final_Ringkas.csv"
    _write_csv(source, [
        {
            "product_text": "Sunlight Lime 910 ml", "promo_price": "16900", "normal_price": "",
            "merchant_name": "Shop A", "source_name": "Shop A", "product_validation_status": "eligible",
            "source_url": "https://example.test/promo", "image_url": "https://example.test/poster.jpg",
            "image_alt": "Harga normal Rp20.000",
        },
    ])
    _write_csv(catalog, [{"Nama Produk": "Sunlight Lime 910 ml"}])
    monkeypatch.setattr(exporter, "SOURCE", source)
    monkeypatch.setattr(exporter, "CATALOG_CANDIDATES", (catalog,))

    products, stats = exporter.read_products()

    assert len(products) == 1
    assert products[0]["Nama Produk"] == "Sunlight Lime 910 ml"
    assert products[0]["Harga Referensi (Rp) - isi manual"] == ""
    assert stats["excluded_with_normal_price"] == 0

# --- from test_export_manual_price_search.py ---
def test_generated_manual_workbook_contains_tokku_verification_fields(tmp_path, monkeypatch):
    from openpyxl import load_workbook
    source = tmp_path / "products.csv"
    catalog = tmp_path / "catalog.csv"
    output = tmp_path / "Daftar_Cari_Harga_Manual.xlsx"
    _write_csv(source, [{
        "product_text": "Sania Minyak Goreng Pouch 2 L", "promo_price": "20000",
        "normal_price": "", "merchant_name": "Shop A", "product_validation_status": "eligible",
        "source_url": "https://example.test/promo",
    }])
    _write_csv(catalog, [{"Nama Produk": "Sania Minyak Goreng Pouch 2 L"}])
    monkeypatch.setattr(exporter, "SOURCE", source)
    monkeypatch.setattr(exporter, "CATALOG_CANDIDATES", (catalog,))
    monkeypatch.setattr(exporter, "OUT", output)
    exporter.main()
    wb = load_workbook(output, read_only=True, data_only=True)
    try:
        ws = wb["Cari Harga"]
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        assert "Retailer Pembanding" in headers
        assert "Tanggal Terakhir Dicek oleh Sumber (YYYY-MM-DD)" in headers
        assert "Kecocokan SKU (exact/close/unknown)" in headers
        assert ws.max_row == 2
        assert "Tokku" not in str(ws.cell(2, 7).value or "")  # no source is prefilled as a claim.
        help_text = " ".join(str(row[0]) for row in wb["Petunjuk"].iter_rows(values_only=True))
        assert "Tidak ada collector otomatis Tokku" in help_text
    finally:
        wb.close()

# --- from test_export_manual_price_search.py ---
def test_outside_catalog_candidates_are_kept_in_separate_review_sheet(tmp_path, monkeypatch):
    from openpyxl import load_workbook
    source = tmp_path / "products.csv"
    catalog = tmp_path / "catalog.csv"
    output = tmp_path / "Daftar_Cari_Harga_Manual.xlsx"
    _write_csv(source, [
        {"product_text": "Sania Minyak Goreng 2 L", "promo_price": "45000", "normal_price": "", "merchant_name": "Shop A", "product_validation_status": "eligible", "source_url": "https://example.test/a"},
        {"product_text": "Bango Kecap Manis 700 g", "promo_price": "19000", "normal_price": "", "merchant_name": "Shop B", "product_validation_status": "eligible", "source_url": "https://example.test/b"},
    ])
    _write_csv(catalog, [{"Nama Produk": "Sania Minyak Goreng 2 L"}])
    monkeypatch.setattr(exporter, "SOURCE", source)
    monkeypatch.setattr(exporter, "CATALOG_CANDIDATES", (catalog,))
    monkeypatch.setattr(exporter, "OUT", output)

    exporter.main()
    wb = load_workbook(output, read_only=True, data_only=True)
    try:
        assert wb["Cari Harga"].max_row == 2
        assert wb["Di Luar Katalog"].max_row == 2
        headers = [cell.value for cell in wb["Di Luar Katalog"][1]]
        row = dict(zip(headers, next(wb["Di Luar Katalog"].iter_rows(min_row=2, values_only=True))))
        assert row["Nama Produk"] == "Bango Kecap Manis 700 g"
        assert row["Status"] == "DI LUAR KATALOG - REVIEW"
        assert "tidak masuk katalog utama" in row["Catatan Verifikasi"]
    finally:
        wb.close()

# --- from test_export_manual_price_search.py ---
def test_manual_values_in_outside_catalog_sheet_survive_rebuild(tmp_path, monkeypatch):
    from openpyxl import Workbook, load_workbook
    source = tmp_path / "products.csv"
    catalog = tmp_path / "catalog.csv"
    output = tmp_path / "Daftar_Cari_Harga_Manual.xlsx"
    source_rows = [{
        "product_text": "Bango Kecap Manis 700 g", "promo_price": "19000", "normal_price": "",
        "merchant_name": "Shop B", "product_validation_status": "eligible", "source_url": "https://example.test/b",
    }]
    _write_csv(source, source_rows)
    _write_csv(catalog, [{"Nama Produk": "Sania Minyak Goreng 2 L"}])
    monkeypatch.setattr(exporter, "SOURCE", source)
    monkeypatch.setattr(exporter, "CATALOG_CANDIDATES", (catalog,))
    monkeypatch.setattr(exporter, "OUT", output)

    wb = Workbook()
    ws = wb.active
    ws.title = "Cari Harga"
    ws.append(exporter.HEADERS)
    outside = wb.create_sheet("Di Luar Katalog")
    outside.append(exporter.HEADERS)
    values = {header: "" for header in exporter.HEADERS}
    values.update({
        "Nama Produk": "Bango Kecap Manis 700 g",
        "Merchant Promo": "Shop B",
        "Harga Promo (Rp)": "19000",
        "Harga Referensi (Rp) - isi manual": "23000",
        "Nama Sumber": "Tokku",
        "URL Halaman Harga": "https://tokku.app/id/product/bango-example",
        "Bukti Harga pada Halaman": "Harga normal retailer Rp23.000",
        "Tanggal Cek (YYYY-MM-DD)": "2026-11-04",
        "Status": "DI LUAR KATALOG - REVIEW",
    })
    outside.append([values.get(header, "") for header in exporter.HEADERS])
    wb.save(output)
    wb.close()

    exporter.main()
    wb = load_workbook(output, read_only=True, data_only=True)
    try:
        ws = wb["Di Luar Katalog"]
        headers = [cell.value for cell in ws[1]]
        row = dict(zip(headers, next(ws.iter_rows(min_row=2, values_only=True))))
        assert row["Harga Referensi (Rp) - isi manual"] == "23000"
        assert row["Nama Sumber"] == "Tokku"
        assert row["URL Halaman Harga"] == "https://tokku.app/id/product/bango-example"
    finally:
        wb.close()

# --- from test_manual_price_workflow.py ---
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

# --- from test_manual_price_workflow.py ---
def test_price_parser_indonesian():
    assert importer.price_int("Rp 22.900") == 22900
    assert importer.price_int("16.900") == 16900
    assert importer.price_int("0") is None

# --- from test_manual_price_workflow.py ---
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

# --- from test_manual_price_workflow.py ---
def test_ai_json_is_explicitly_rejected(tmp_path):
    json_file = tmp_path / "old-estimates.json"
    json_file.write_text('{"estimates": [{"product_name": "Product X", "estimated_price": 15000}]}', encoding="utf-8")
    with pytest.raises(SystemExit, match="estimasi AI sudah dihapus"):
        importer.main([str(json_file)])

# --- from test_manual_price_workflow.py ---
def test_incomplete_manual_market_reference_is_not_imported(tmp_path):
    xlsx = tmp_path / "market.xlsx"
    _workbook(xlsx, ["Product X 500 g", "15000", "Shop", "", "Harga 15000", "2026-10-25", "pasar", "Product X"])
    entries, errors, total = importer._read_xlsx(xlsx)
    assert total == 1
    assert entries == []
    assert any("URL harus berupa URL halaman" in error for error in errors)

# --- from test_manual_price_workflow.py ---
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

# --- from test_manual_price_workflow.py ---
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

# --- from test_manual_price_workflow.py ---
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

# --- from test_manual_price_workflow.py ---
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
    assert row["normal_price"] is None

# --- from test_manual_price_workflow.py ---
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

# --- from test_manual_price_workflow.py ---
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

# --- from test_manual_price_workflow.py ---
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

# --- from test_manual_price_workflow.py ---
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

# --- from test_manual_price_workflow.py ---
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

# --- from test_manual_price_workflow.py ---
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
