"""Grouped regression tests. Cases are organized by functional area."""



from __future__ import annotations

import csv

import sys

from pathlib import Path

import enrich_existing_promo_catalog_multisource as enhancer

from enrich_existing_promo_catalog_multisource import (  # noqa: E402
    SIMPLE_EXCEL_COLUMNS,
    make_simple_excel_row,
    write_simple_catalog_csv,
)

from promo_multisource_collector import parse_offer_text

from enrich_existing_promo_catalog_multisource import partition_current_review_rows

from promo_multisource_collector import (  # noqa: E402
    build_source_health_report,
    dedupe_rows,
)



# --- from test_freshness_partition.py ---
SRC = Path(__file__).resolve().parents[1] / "src"

# --- from test_freshness_partition.py ---
sys.path.insert(0, str(SRC))

# --- from test_freshness_partition.py ---
def test_carried_forward_classifier_recognizes_only_nonfresh_rows():
    assert enhancer.row_is_carried_forward({"retained_from_previous_run": "true"})
    assert enhancer.row_is_carried_forward({"freshness_status": "preserved_previous"})
    assert enhancer.row_is_carried_forward({"freshness_status": "mixed:preserved_previous"})
    assert not enhancer.row_is_carried_forward({"freshness_status": "mixed:fresh|preserved_previous"})
    assert not enhancer.row_is_carried_forward({"freshness_status": "fresh"})

# --- from test_freshness_partition.py ---
def test_simple_catalog_csv_active_only_excludes_review_and_preserved(tmp_path):
    rows = [
        base_row(product_text="Fresh clean product 100 g", normal_price=10000, promo_price=9000, freshness_status="fresh"),
        base_row(product_text="Fresh review product 100 g", promo_price=None, freshness_status="fresh"),
        base_row(product_text="Preserved product 100 g", promo_price=9000, freshness_status="preserved_previous"),
    ]
    path = tmp_path / "catalog.csv"
    count = enhancer.write_simple_catalog_csv(path, rows, active_only=True)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        data = list(csv.DictReader(handle))
    assert count == 1
    assert [row["Nama Produk"] for row in data] == ["Fresh clean product 100 g"]

# --- from test_freshness_partition.py ---
def test_excel_summary_and_freshness_tabs_are_mutually_exclusive(tmp_path, monkeypatch):
    from openpyxl import load_workbook

    fresh_clean = base_row(
        product_text="Fresh Clean Product 100 g", normal_price=10000, promo_price=9000,
        freshness_status="fresh", scraped_at="2026-11-04T09:00:00+07:00",
    )
    fresh_review = base_row(
        product_text="Fresh Review Product 100 g", promo_price=None,
        freshness_status="fresh", product_validation_status="review",
        scraped_at="2026-11-04T09:00:00+07:00",
    )
    preserved = base_row(
        product_text="Preserved Product 100 g", normal_price=10000, promo_price=9000,
        freshness_status="preserved_previous", retained_from_previous_run=True,
        scraped_at="2026-11-01T09:00:00+07:00",
    )
    review_outside = base_row(
        product_text="Outside Review Product 100 g", promo_price=None,
        freshness_status="fresh", promo_status="expired", product_validation_status="review",
    )
    path = tmp_path / "catalog.xlsx"
    assert enhancer.write_excel_catalog(
        path,
        current_rows=[fresh_clean, fresh_review, preserved],
        confirmed_rows=[fresh_clean],
        review_rows=[fresh_review, review_outside],
        name_variant_rows=[],
        possible_duplicate_rows=[],
        rejected_rows=[],
        export_gate_report={"status": "passed", "routed_to_review_rows": 1, "issue_counts": {}},
    )
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        assert "Promo" in wb.sheetnames
        assert "Promo Aktif - Review" in wb.sheetnames
        assert "Promo Dipertahankan" in wb.sheetnames
        assert "Perlu Diperiksa" in wb.sheetnames
        def products(sheet):
            ws = wb[sheet]
            headers = [cell.value for cell in ws[1]]
            return [dict(zip(headers, row))["Nama Produk"] for row in ws.iter_rows(min_row=2, values_only=True)]
        assert products("Promo") == ["Fresh Clean Product 100 g"]
        assert products("Promo Aktif - Review") == ["Fresh Review Product 100 g"]
        assert products("Promo Dipertahankan") == ["Preserved Product 100 g"]
        assert products("Perlu Diperiksa") == ["Outside Review Product 100 g"]

        summary = wb["Mulai Di Sini"]
        values = {summary.cell(row, 1).value: summary.cell(row, 2).value for row in range(2, summary.max_row + 1)}
        assert values["Promo fresh tanpa review tambahan"] == 1
        assert values["Promo fresh yang perlu review"] == 1
        assert values["Promo aktif dipertahankan dari run sebelumnya"] == 1
        assert values["Total promo aktif (fresh + dipertahankan)"] == 3
    finally:
        wb.close()

# --- from test_simple_excel.py ---
ENGINE = Path(__file__).resolve().parents[1] / "src"

# --- from test_simple_excel.py ---
sys.path.insert(0, str(ENGINE))

# --- from test_simple_excel.py ---
def base_row(**overrides):
    row = {
        "product_text": "Contoh Produk 100 g",
        "original_product_text": "Contoh Produk 100 g",
        "merchant_name": "Indomaret",
        "normal_price": None,
        "promo_price": None,
        "discount_percent": None,
        "discount_percent_basis": "not_available",
        "discount_percent_confidence": "unknown",
        "discount_savings_rp": None,
        "reference_normal_price": None,
        "reference_price_low": None,
        "reference_price_high": None,
        "reference_price_unit": None,
        "reference_price_record_origin": None,
        "reference_primary_display_allowed": False,
        "price_quality_flag": None,
        "price_basis": "offer_price",
        "purchase_condition": None,
        "deal_type": None,
        "offer_text": "",
        "raw_line": "",
        "promo_status": "active",
        "valid_from": "2026-10-23",
        "valid_until": "2026-10-28",
        "period_precision": "range",
        "period_certainty": "confirmed",
        "product_validation_status": "eligible",
        "verification_status": "aggregator_only",
        "source_verification_label": "Agregator; belum diverifikasi retailer",
        "source_url": "https://example.invalid/promo",
        "source_name": "Test",
        "source_type": "aggregator",
        "freshness_status": "fresh",
        "campaign_title": "Promo contoh",
    }
    row.update(overrides)
    return row

# --- from test_simple_excel.py ---
def test_explicit_nominal_discount_is_not_misread_as_product_price():
    parsed = parse_offer_text(
        "Yummy Choice Fried Chicken",
        "Beli 5 pcs Diskon Rp. 10.000",
        "article",
    )
    assert parsed["promo_price"] is None
    assert parsed["normal_price"] is None
    assert parsed["discount_savings_rp"] == 10000
    assert parsed["discount_basis"] == "explicit_amount_discount"
    assert parsed["price_basis"] == "discount_amount_offer"

# --- from test_simple_excel.py ---
def test_simple_sheet_does_not_use_legacy_estimate_for_nominal_savings():
    row = base_row(
        product_text="Yummy Choice Fried Chicken",
        original_product_text="Yummy Choice Fried Chicken",
        promo_price=10000,  # legacy bad parse; display helper must repair it
        price_basis="bundle_offer_amount",
        purchase_condition="Beli 5 pcs",
        offer_text="Beli 5 pcs Diskon Rp. 10.000",
        raw_line="Yummy Choice Fried Chicken -> Beli 5 pcs Diskon Rp. 10.000",
        reference_normal_price=15000,
        reference_price_low=12000,
        reference_price_high=18000,
        reference_price_unit="per potong",
        reference_price_record_origin="user_supplied_estimate",
    )
    simple = make_simple_excel_row(row)
    assert simple["Harga Promo (Rp)"] == "—"
    assert simple["Hemat (Rp)"] == 10000
    assert simple["Harga Normal/Acuan (Rp)"] == "—"
    assert simple["Diskon (%)"] == "Belum bisa dihitung"
    assert "Estimasi" not in simple["Status Diskon"]

# --- from test_simple_excel.py ---
def test_simple_sheet_calculates_explicit_same_offer_price_pair():
    row = base_row(
        product_text="Sedaap Mie Instant 90 g",
        promo_price=7900,
        normal_price=None,
        price_basis="bundle_offer_amount",
        purchase_condition="Beli 3",
        offer_text="Beli 3 Lebih Hemat harga spesial Rp7.900 dari harga normalnya Rp.9.000",
        raw_line="Beli 3 Lebih Hemat harga spesial Rp7.900 dari harga normalnya Rp.9.000",
    )
    simple = make_simple_excel_row(row)
    assert simple["Harga Normal/Acuan (Rp)"] == 9000
    assert simple["Harga Promo (Rp)"] == 7900
    assert simple["Hemat (Rp)"] == 1100
    assert simple["Diskon (%)"] == 12.2
    assert "tertulis" in simple["Status Diskon"].casefold()

# --- from test_simple_excel.py ---
def test_simple_sheet_does_not_use_legacy_estimate_for_bundle_discount():
    row = base_row(
        product_text="Frisian Flag Susu Cair UHT Cokelat 225 ml",
        promo_price=9900,
        price_basis="bundle_offer_amount",
        purchase_condition="Beli 2",
        offer_text="Beli 2 Rp. 9.900",
        raw_line="Beli 2 Rp. 9.900",
        reference_normal_price=6000,
        reference_price_low=5500,
        reference_price_high=6500,
        reference_price_unit="pack",
        reference_price_record_origin="user_supplied_estimate",
    )
    simple = make_simple_excel_row(row)
    assert simple["Harga Normal/Acuan (Rp)"] == "—"
    assert simple["Harga Promo (Rp)"] == 9900
    assert simple["Diskon (%)"] == "Belum bisa dihitung"
    assert "Estimasi" not in simple["Status Diskon"]

# --- from test_simple_excel.py ---
def test_simple_sheet_does_not_calculate_implausibly_low_bundle_price():
    row = base_row(
        product_text="Indomaret Air Mineral 600 ml",
        promo_price=2500,
        price_basis="bundle_offer_amount",
        purchase_condition="Beli 2",
        offer_text="Beli 2 Rp. 2.500",
        raw_line="Beli 2 Rp. 2.500",
        reference_normal_price=4250,
        reference_price_low=3000,
        reference_price_high=5500,
        reference_price_unit="pack",
        reference_price_record_origin="user_supplied_estimate",
    )
    simple = make_simple_excel_row(row)
    assert simple["Diskon (%)"] == "Belum bisa dihitung"
    assert "pembanding" in simple["Status Diskon"].casefold()

# --- from test_simple_excel.py ---
def test_every_simple_row_has_discount_cell_and_period_after_discount():
    row = base_row(
        promo_price=9000,
        offer_text="Rp9.000",
        raw_line="Rp9.000",
    )
    simple = make_simple_excel_row(row)
    assert simple["Diskon (%)"] not in (None, "")
    assert SIMPLE_EXCEL_COLUMNS.index("Masa Berlaku") == SIMPLE_EXCEL_COLUMNS.index("Diskon (%)") + 1
    assert simple["Masa Berlaku"] == "23–28 Okt 2026"

# --- from test_simple_excel.py ---
def test_simple_csv_uses_exact_same_values_as_excel_promo_sheet(tmp_path):
    import csv

    rows = [
        base_row(
            product_text="Sedaap Mie Instant 90 g",
            promo_price=7900,
            offer_text="Beli 3 Lebih Hemat harga spesial Rp7.900 dari harga normalnya Rp.9.000",
            raw_line="Beli 3 Lebih Hemat harga spesial Rp7.900 dari harga normalnya Rp.9.000",
        ),
        base_row(
            product_text="Contoh Produk Tanpa Harga",
            promo_price=None,
            normal_price=None,
            offer_text="Promo berlaku untuk produk pilihan",
            raw_line="Promo berlaku untuk produk pilihan",
        ),
    ]
    out = tmp_path / "Katalog_Promo_Final_Ringkas.csv"
    assert write_simple_catalog_csv(out, rows) == len(rows)
    with out.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        csv_rows = list(reader)
        assert reader.fieldnames == SIMPLE_EXCEL_COLUMNS

    expected = [make_simple_excel_row(row) for row in rows]
    for actual, exp in zip(csv_rows, expected):
        for field in SIMPLE_EXCEL_COLUMNS:
            assert actual[field] == str(exp.get(field, "—") if exp.get(field, "—") is not None else ""), (field, actual[field], exp.get(field))
    assert csv_rows[0]["Diskon (%)"] == "12.2"
    assert csv_rows[1]["Diskon (%)"] == "Belum bisa dihitung"
    assert csv_rows[0]["Masa Berlaku"] == "23–28 Okt 2026"

# --- from test_review_partition.py ---
sys.path.insert(0, str(SRC))

# --- from test_review_partition.py ---
def test_active_and_review_workbook_buckets_are_mutually_exclusive():
    active_clean = {"product_text": "Produk bersih"}
    active_review = {"product_text": "Produk aktif perlu review"}
    review_only = {"product_text": "Produk belum aktif perlu review"}

    clean, active_flagged, nonactive_review = partition_current_review_rows(
        [active_clean, active_review],
        [active_review, review_only],
    )

    assert clean == [active_clean]
    assert active_flagged == [active_review]
    assert nonactive_review == [review_only]
    assert not ({id(row) for row in clean} & {id(row) for row in active_flagged})
    assert not ({id(row) for row in clean + active_flagged} & {id(row) for row in nonactive_review})

# --- from test_source_freshness_attribution.py ---
sys.path.insert(0, str(SRC))

# --- from test_source_freshness_attribution.py ---
def _row(source, *, retained=False):
    return {
        "source_name": source,
        "source_names": source,
        "product_text": "Contoh Produk Susu 1 L",
        "offer_text": "Harga Promo Rp15.000",
        "normal_price": "20000",
        "promo_price": "15000",
        "valid_from": "2026-11-01",
        "valid_until": "2026-11-10",
        "purchase_condition": "",
        "retained_from_previous_run": retained,
    }

# --- from test_source_freshness_attribution.py ---
def test_fresh_source_not_marked_preserved_because_another_source_is_old():
    merged = dedupe_rows([
        _row("Hemat.id", retained=False),
        _row("Scanharga.com", retained=True),
    ])
    assert len(merged) == 1
    row = merged[0]
    assert row["source_fresh_names"] == "Hemat.id"
    assert row["source_preserved_names"] == "Scanharga.com"
    assert row["retained_from_previous_run"] is False

# --- from test_source_freshness_attribution.py ---
def test_source_health_counts_freshness_per_source_not_per_merged_row():
    products = dedupe_rows([
        _row("Hemat.id", retained=False),
        _row("Scanharga.com", retained=True),
    ])
    report = build_source_health_report(
        ["Hemat.id", "Scanharga.com"],
        products,
        [
            {"source_name": "Hemat.id", "status": "ok"},
            {"source_name": "Scanharga.com", "status": "ok"},
        ],
    )
    assert report["Hemat.id"]["fresh_product_rows"] == 1
    assert report["Hemat.id"]["preserved_previous_rows"] == 0
    assert report["Scanharga.com"]["fresh_product_rows"] == 0
    assert report["Scanharga.com"]["preserved_previous_rows"] == 1
