import csv
import export_manual_price_search as exporter


def _write_csv(path, rows):
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


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
