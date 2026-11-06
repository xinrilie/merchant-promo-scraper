"""Grouped regression tests. Cases are organized by functional area."""



from __future__ import annotations

import csv

import sys

from datetime import date, datetime

from pathlib import Path

import enrich_existing_promo_catalog_multisource as enhancer

import promo_multisource_collector as collector

from bs4 import BeautifulSoup

from promo_product_validation import pipe_sources_for_validation

from promo_evidence import (
    find_amount_evidence,
    find_discount_evidence,
    period_certainty,
    source_verification_label,
)



# --- from test_evidence_quality.py ---
ENGINE_DIR = Path(__file__).resolve().parents[1] / "src"

# --- from test_evidence_quality.py ---
sys.path.insert(0, str(ENGINE_DIR))

# --- from test_evidence_quality.py ---
def _write_feed(path: Path, row: dict) -> None:
    fields = list(row)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(row)

# --- from test_evidence_quality.py ---
def test_evidence_extractors_return_literal_source_text():
    offer = "Harga Promo Rp12.900, Harga Normal Rp15.900, Diskon 18,9%"
    promo = find_amount_evidence(offer, 12900, "promo")
    normal = find_amount_evidence(offer, 15900, "normal")
    discount = find_discount_evidence(offer, 18.9)
    assert promo and "Rp12.900" in promo and "Promo" in promo
    assert normal and "Rp15.900" in normal and "Normal" in normal
    assert discount and "18,9%" in discount
    assert find_amount_evidence("Hanya diskon produk tanpa nominal harga", 12900, "promo") is None

# --- from test_evidence_quality.py ---
def test_load_source_reconstructs_evidence_and_keeps_new_merchant():
    with __import__("tempfile").TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "feed.csv"
        _write_feed(path, {
            "product_text": "All Fruit Fuji Apples 1 kg",
            "merchant_name": "All Fruit",
            "campaign_title": "Promo All Fruit 23-25 Oktober 2026",
            "offer_text": "Harga Promo Rp12.900, Harga Normal Rp15.900",
            "normal_price": "15900",
            "promo_price": "12900",
            "price_basis": "offer_price",
            "valid_from": "2026-10-23",
            "valid_until": "2026-10-25",
            "period_precision": "range",
            "source_name": "Hemat.id",
            "source_type": "aggregator_product_listing",
            "verification_status": "aggregator_only",
            "source_url": "https://example.test/all-fruit/promo",
            "raw_line": "All Fruit Fuji Apples 1 kg — Harga Promo Rp12.900, Harga Normal Rp15.900",
        })
        rows = enhancer.load_source(path, "promo_multisource_products_all.csv")

    assert len(rows) == 1
    row = rows[0]
    assert row["merchant_name"] == "All Fruit"
    assert "Rp12.900" in row["promo_price_evidence_text"]
    assert "Rp15.900" in row["normal_price_evidence_text"]
    assert row["discount_percent_basis"] == "calculated_from_unit_prices"
    assert row["discount_evidence_text"]
    assert row["period_evidence_text"]
    assert row["period_certainty"] == "confirmed"
    assert row["source_verification_label"] == "Agregator; belum diverifikasi retailer"

# --- from test_evidence_quality.py ---
def test_uniqlo_editorial_fragment_with_rp199000_is_rejected_by_final_import():
    with __import__("tempfile").TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "uniqlo_editorial.csv"
        _write_feed(path, {
            "product_text": "Jangan Sampai Kelewatan Promo Uniqlo Limited Offers Mulai",
            "merchant_name": "Uniqlo Limited Offers",
            "campaign_title": "Promo UNIQLO Weekly Limited Offers 23-29 Oktober 2026",
            "promo_status": "active",
            "valid_from": "2026-10-23",
            "valid_until": "2026-10-29",
            "period_precision": "range",
            "promo_price": "199000",
            "price_basis": "offer_price",
            "offer_text": "Rp199.000 ini. Berlaku mulai tanggal 23-29 Oktober 2026, buruan ke toko atau belanja online di UNIQLO!",
            "source_name": "Katalogpromosi.com",
            "source_url": "https://katalogpromosi.com/promo-uniqlo-limited-offers-minggu-ini/",
        })
        rows = enhancer.load_source(path, "promo_multisource_products_all.csv")
    assert len(rows) == 1
    assert rows[0]["product_validation_status"] == "rejected"
    assert rows[0]["product_rejection_reason"] == "editorial_heading_misparsed_as_product"

# --- from test_evidence_quality.py ---
def test_unsubstantiated_price_is_cleared_and_sent_to_review(monkeypatch):
    # Freeze the business date so the fixture remains valid after October 2026.
    # Production status must still use the actual Asia/Jakarta date.
    monkeypatch.setattr(enhancer, "TODAY", date(2026, 10, 15))
    with __import__("tempfile").TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "feed.csv"
        _write_feed(path, {
            "product_text": "Snack Brand Potato Chips 200 g",
            "merchant_name": "Fresh Basket",
            "campaign_title": "Promo Fresh Basket Minggu Ini",
            "offer_text": "Diskon 20% untuk produk pilihan",
            "normal_price": "",
            "promo_price": "9999",
            "price_basis": "offer_price",
            "discount_percent": "20",
            "valid_from": "2026-10-01",
            "valid_until": "2026-10-31",
            "period_precision": "range",
            "source_name": "Katalogpromosi.com",
            "source_type": "aggregator_article",
            "verification_status": "aggregator_only",
            "source_url": "https://example.test/promo",
            "raw_line": "Snack Brand Potato Chips 200 g — Diskon 20% untuk produk pilihan",
        })
        rows = enhancer.load_source(path, "promo_multisource_products_all.csv")

    assert len(rows) == 1
    row = rows[0]
    assert row["promo_price"] is None
    assert "promo_price_without_matching_offer_evidence" in (row["price_quality_flag"] or "")
    assert row["product_validation_status"] == "review"
    assert "Harga promo tidak memiliki bukti teks" in (row["product_review_reason"] or "")
    assert row["period_precision"] == "unverified"
    assert row["promo_status"] == "active_estimated"
    assert row["period_certainty"] == "estimated"

# --- from test_evidence_quality.py ---
def test_unverified_promo_period_that_has_ended_is_expired(monkeypatch):
    # Even an unverified date range must not remain active after its end date.
    monkeypatch.setattr(enhancer, "TODAY", date(2026, 11, 3))
    assert enhancer.current_status(
        "2026-10-01", "2026-10-31", "unverified"
    ) == "expired"

# --- from test_evidence_quality.py ---
def test_name_cleaned_to_empty_is_reviewed_and_never_published_as_product_price():
    with __import__("tempfile").TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "generic_price_labels.csv"
        fields = [
            "product_text", "merchant_name", "campaign_title", "promo_status",
            "valid_from", "valid_until", "period_precision", "promo_price",
            "price_basis", "offer_text", "source_url", "source_name",
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows([
                {
                    "product_text": "Potongan harga", "merchant_name": "Alfamart",
                    "campaign_title": "Promo JSM Alfamart 23-25 Oktober 2026",
                    "promo_status": "active", "valid_from": "2026-10-23",
                    "valid_until": "2026-10-25", "period_precision": "range",
                    "promo_price": "5000", "price_basis": "offer_price",
                    "offer_text": "Rp5.000.", "source_url": "https://example.test/alfamart",
                    "source_name": "Katalogpromosi.com",
                },
                {
                    "product_text": "Harga spesial", "merchant_name": "Foodhall",
                    "campaign_title": "Promo THEFOODHALL 23-29 Oktober 2026",
                    "promo_status": "active", "valid_from": "2026-10-23",
                    "valid_until": "2026-10-29", "period_precision": "range",
                    "promo_price": "50000", "price_basis": "offer_price",
                    "offer_text": "Rp 50.000 dan Rp 100.000 berlaku untuk produk tertentu",
                    "source_url": "https://example.test/foodhall",
                    "source_name": "Katalogpromosi.com",
                },
            ])
        rows = enhancer.load_source(path, path.name)

    assert len(rows) == 2
    for row in rows:
        assert row["product_text"] == ""
        assert row["product_validation_status"] == "review"
        assert row["promo_price"] is None
        assert row["normal_price"] is None
        assert row["discount_percent"] is None
        assert row["product_subcategory"] == "Produk belum teridentifikasi"
        display = enhancer.make_clean_row(row, review=True)
        assert display["Nama Produk"] == "Produk belum teridentifikasi"
        assert display["Harga Promo (Rp)"] is None
        assert display["Harga Asli dari Sumber (Rp)"] is None

# --- from test_evidence_quality.py ---
def test_period_certainty_is_separate_from_retailer_verification():
    assert period_certainty("range", "active", None, "23-25 Oktober 2026") == "confirmed"
    assert period_certainty("month", "active_estimated", None, "Oktober 2026") == "estimated"
    assert period_certainty("unverified", "active_estimated", "period_evidence_missing_unverified", None) == "estimated"
    assert period_certainty("range", "active", "title_period_mismatch_with_catalog_dates", "23-25 Oktober 2026") == "conflict"
    assert source_verification_label("aggregator_only") == "Agregator; belum diverifikasi retailer"
    assert source_verification_label("unrecognized_source_type") == "Beberapa sumber; bukan verifikasi retailer"
    assert source_verification_label("retailer_verified") == "Retailer terverifikasi"
    assert source_verification_label("aggregator_only | historical_baseline_unknown") == "Beberapa sumber; sebagian asal verifikasi belum diketahui"

# --- from test_evidence_quality.py ---
def test_each_live_adapter_emits_price_and_period_evidence():
    # Hemat.id structured-card path.
    hemat_meta = collector.parse_promo_metadata(
        "Promo All Fruit 23-25 Oktober 2026", "",
        "Berlaku 23-25 Oktober 2026"
    )
    hemat_row = collector.make_product_row(
        source_name="Hemat.id",
        product_text="All Fruit Fuji Apples 1 kg",
        offer_text="Harga Promo Rp12.900, Harga Normal Rp15.900",
        title="Promo All Fruit 23-25 Oktober 2026",
        merchant="All Fruit", meta=hemat_meta,
        source_url="https://hemat.example/promo",
        source_page_url="https://hemat.example/promo",
        source_item_url="https://hemat.example/item/apple",
        raw_line="All Fruit Fuji Apples 1 kg — Harga Promo Rp12.900, Harga Normal Rp15.900",
        source_mode="hemat",
    )
    assert "Rp12.900" in hemat_row["promo_price_evidence_text"]
    assert "Rp15.900" in hemat_row["normal_price_evidence_text"]
    assert hemat_row["period_evidence_text"]

    # Katalogpromosi/Scanharga share article-line extraction but retain their source labels.
    html = BeautifulSoup(
        "<article><ul><li>Fresh Basket Fuji Apples 1 kg → Harga Promo Rp12.900, Harga Normal Rp15.900</li></ul></article>",
        "html.parser",
    )
    title = "Promo JSM Fresh Basket 23-25 Oktober 2026"
    meta = collector.parse_promo_metadata(title, "23-25 Oktober 2026")
    article_rows = collector.extract_article_rows(
        html, "Katalogpromosi.com", title,
        "https://katalogpromosi.example/promo-fresh-basket", meta
    )
    assert article_rows, "Katalogpromosi article adapter should extract the fixture offer"
    assert article_rows[0]["promo_price_evidence_text"]
    assert article_rows[0]["normal_price_evidence_text"]
    assert article_rows[0]["period_evidence_text"]

# --- from test_evidence_quality.py ---
def test_source_freshness_report_does_not_call_missing_timestamp_fresh():
    now = datetime.fromisoformat("2026-10-23T12:00:00+07:00")
    rows = [
        {"source_name": "Hemat.id", "scraped_at": "2026-10-23T11:50:00+07:00"},
        {"source_name": "Scanharga.com", "scraped_at": "2026-10-01T11:50:00+07:00"},
        {"source_name": "Katalogpromosi.com", "scraped_at": "2026-10-23T11:55:00+07:00", "retained_from_previous_run": "true"},
        {"source_dataset": "older_catalog_baseline.csv", "scraped_at": ""},
    ]
    report = enhancer.build_source_freshness_report(rows, now)
    assert report["Hemat.id"]["status"] == "fresh"
    assert report["Hemat.id"]["fresh_rows"] == 1
    assert report["Scanharga.com"]["status"] == "stale"
    assert report["Katalogpromosi.com"]["status"] == "preserved_previous"
    assert report["Source tidak diketahui"]["status"] == "historical_or_unverified"

# --- from test_evidence_quality.py ---
def test_collector_source_health_distinguishes_failure_from_empty_source():
    products = [
        {
            "source_name": "Hemat.id", "promo_price": 12900, "promo_price_evidence_text": "Harga Promo Rp12.900",
            "discount_percent": 20, "discount_evidence_text": "Diskon 20%", "period_evidence_text": "23-25 Oktober 2026",
            "retained_from_previous_run": False, "promo_status": "active",
        },
        {"source_name": "Scanharga.com", "promo_price": 10000, "retained_from_previous_run": True},
    ]
    requests = [
        {"source_name": "Hemat.id", "status": "ok"},
        {"source_name": "Scanharga.com", "status": "ok"},
        {"source_name": "Katalogpromosi.com", "status": "ok"},
    ]
    report = collector.build_source_health_report(
        ["Hemat.id", "Scanharga.com", "Katalogpromosi.com"],
        products,
        requests,
    )
    assert report["Hemat.id"]["status"] == "fresh"
    assert report["Hemat.id"]["promo_price_evidence_coverage"] == 1.0
    assert report["Scanharga.com"]["status"] == "preserved_previous"
    assert report["Katalogpromosi.com"]["status"] == "reachable_no_products"

# --- from test_evidence_quality.py ---
def test_unknown_verification_provenance_is_not_mislabeled_as_aggregator():
    assert source_verification_label("historical_baseline_unknown") == "Baseline historis; asal verifikasi belum diketahui"

# --- from test_evidence_quality.py ---
def test_storage_dataset_name_never_counts_as_independent_source():
    assert pipe_sources_for_validation({"source_dataset": "promo_baseline.csv"}) == []
    assert pipe_sources_for_validation({"source_name": "Hemat.id", "source_dataset": "promo_baseline.csv"}) == ["Hemat.id"]
    assert pipe_sources_for_validation({"source_names": "Hemat.id | Scanharga.com", "source_dataset": "promo_baseline.csv"}) == ["Hemat.id", "Scanharga.com"]

# --- from test_evidence_quality.py ---
def test_source_freshness_reports_mixed_fresh_and_historical_and_last_good_status():
    now = datetime.fromisoformat("2026-10-24T19:40:00+07:00")
    rows = [
        {"source_name": "Katalogpromosi.com", "scraped_at": "2026-10-24T19:36:00+07:00"},
        {"source_name": "Katalogpromosi.com", "scraped_at": ""},
        {"source_name": "Katalogpromosi.com", "scraped_at": None},
    ]
    report = enhancer.build_source_freshness_report(rows, now, {
        "Katalogpromosi.com": {
            "checked_at": "2026-10-24T19:36:21+07:00",
            "output_status": "preserved_previous_catalog",
            "preserved_previous_rows": 17,
            "fresh_product_rows": 0,
            "request_count": 10,
        }
    })
    source = report["Katalogpromosi.com"]
    assert source["status"] == "mixed_fresh_and_historical_or_unverified"
    assert source["fresh_rows"] == 1
    assert source["rows_missing_or_invalid_timestamp"] == 2
    assert source["all_rows_fresh"] is False
    assert source["fresh_row_percent"] == 33.3
    assert enhancer.freshness_display_label("mixed:fresh|historical_or_unverified") == "Campuran: Segar (≤7 hari) + Historis / timestamp tidak tersedia"
    assert source["current_run"]["previous_catalog_preserved"] is True
    assert source["current_run"]["previous_catalog_preserved"] is True
    assert "tidak menggantikan katalog stabil" in source["current_run"]["freshness_note"]

# --- from test_evidence_quality.py ---
def test_multi_source_provenance_does_not_copy_one_timestamp_to_every_source():
    now = datetime.fromisoformat("2026-10-24T12:00:00+07:00")
    report = enhancer.build_source_freshness_report([
        {
            "source_name": "Katalogpromosi.com",
            "source_names": "Katalogpromosi.com | Scanharga.com",
            "scraped_at": "2026-10-24T11:55:00+07:00",
        }
    ], now)
    assert report["Katalogpromosi.com"]["fresh_rows"] == 1
    assert "Scanharga.com" not in report

# --- from test_evidence_quality.py ---
def test_missing_per_source_validation_is_unknown_not_false():
    now = datetime.fromisoformat("2026-10-24T21:30:00+07:00")
    report = enhancer.build_source_freshness_report(
        [{"source_name": "Hemat.id", "scraped_at": "2026-10-24T21:29:00+07:00"}],
        now,
        {"Hemat.id": {"output_status": "updated", "source_health_status": "fresh"}},
    )
    run = report["Hemat.id"]["current_run"]
    assert run["output_status"] == "updated"
    assert run["source_health_status"] == "fresh"
    assert run["validation_passed"] is None
    assert run["validation_status"] == "not_reported"
    assert "tidak dilaporkan" in run["freshness_note"]

# --- from test_evidence_quality.py ---
def test_explicit_per_source_validation_is_preserved():
    now = datetime.fromisoformat("2026-10-24T21:30:00+07:00")
    rows = [{"source_name": "Hemat.id", "scraped_at": "2026-10-24T21:29:00+07:00"}]
    passed = enhancer.build_source_freshness_report(rows, now, {
        "Hemat.id": {"output_status": "updated", "validation": {"valid": True}}
    })["Hemat.id"]["current_run"]
    failed = enhancer.build_source_freshness_report(rows, now, {
        "Hemat.id": {"output_status": "updated", "validation": {"valid": False}}
    })["Hemat.id"]["current_run"]
    assert passed["validation_passed"] is True and passed["validation_status"] == "passed"
    assert failed["validation_passed"] is False and failed["validation_status"] == "failed"

# --- from test_evidence_quality.py ---
def test_current_source_metadata_comes_from_three_source_runlog(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(enhancer, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(enhancer, "MULTISOURCE_RUN_LOG", tmp_path / "promo_multisource_runlog.json")
    log = {
        "built_at": "2026-10-24T19:36:21+07:00",
        "reference_date": "2026-10-24",
        "source_health": {
            "Hemat.id": {"status": "fresh", "fresh_product_rows": 20, "preserved_previous_rows": 0, "request_count": 5},
            "Katalogpromosi.com": {"status": "preserved_previous", "fresh_product_rows": 0, "preserved_previous_rows": 12, "request_count": 8},
            "Scanharga.com": {"status": "request_failed", "fresh_product_rows": 0, "preserved_previous_rows": 0, "request_count": 2},
        },
    }
    (tmp_path / "promo_multisource_runlog.json").write_text(json.dumps(log), encoding="utf-8")
    metadata = enhancer.current_source_run_metadata()
    assert set(metadata) == {"Hemat.id", "Katalogpromosi.com", "Scanharga.com"}
    assert metadata["Hemat.id"]["output_status"] == "updated"
    assert metadata["Katalogpromosi.com"]["output_status"] == "preserved_previous_catalog"
    assert metadata["Scanharga.com"]["output_status"] == "request_failed"

# --- from test_evidence_quality.py ---
def test_price_mentioned_only_in_campaign_title_is_not_accepted_as_product_price():
    with __import__("tempfile").TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "headline_price.csv"
        _write_feed(path, {
            "product_text": "Snack Brand Potato Chips 200 g",
            "merchant_name": "Fresh Basket",
            "campaign_title": "Campaign headline mentioning Harga Promo Rp 99.000",
            "offer_text": "Diskon 20% untuk produk pilihan",
            "raw_line": "Snack Brand Potato Chips 200 g — Diskon 20% untuk produk pilihan",
            "promo_price": "99000",
            "normal_price": "120000",
            "price_basis": "offer_price",
            "discount_percent": "20",
            "valid_from": "2026-10-01",
            "valid_until": "2026-10-31",
            "period_precision": "range",
            "source_name": "Katalogpromosi.com",
            "source_type": "aggregator_article",
            "verification_status": "aggregator_only",
            "source_url": "https://example.test/promo",
        })
        rows = enhancer.load_source(path, "promo_multisource_products_all.csv")

    assert len(rows) == 1
    row = rows[0]
    assert row["promo_price"] is None
    assert row["normal_price"] is None
    assert "promo_price_without_matching_offer_evidence" in (row["price_quality_flag"] or "")
    assert "normal_price_without_matching_offer_evidence" in (row["price_quality_flag"] or "")
    assert row["product_validation_status"] == "review"

# --- from test_export_quality_gate.py ---
sys.path.insert(0, str(ENGINE_DIR))

# --- from test_export_quality_gate.py ---
def _candidate(**overrides):
    row = {
        "product_text": "Sunlight Jeruk 755 ml",
        "original_product_text": "Sunlight Jeruk 755 ml",
        "merchant_name": "Super Indo",
        "campaign_title": "Promo Super Indo 23-25 Oktober 2026",
        "promo_status": "active",
        "period_certainty": "confirmed",
        "period_precision": "range",
        "valid_from": "2026-10-23",
        "valid_until": "2026-10-25",
        "promo_price": 16900,
        "normal_price": 22900,
        "promo_price_evidence_text": "Harga Promo Rp16.900",
        "normal_price_evidence_text": "Harga Normal Rp22.900",
        "discount_percent": 26.2,
        "discount_percent_basis": "calculated_from_unit_prices",
        "discount_percent_confidence": "high",
        "price_basis": "offer_price",
        "offer_text": "Harga Normal Rp22.900, Harga Promo Rp16.900",
        "raw_line": "Sunlight Jeruk 755 ml: Harga Normal Rp22.900, Harga Promo Rp16.900",
        "source_url": "https://example.test/promo-sunlight",
        "source_name": "Katalogpromosi.com",
        "product_validation_status": "eligible",
        "product_review_reason": None,
        "product_rejection_reason": None,
        "price_quality_flag": None,
        "data_quality_flags": None,
    }
    row.update(overrides)
    return row

# --- from test_export_quality_gate.py ---
def test_product_validation_is_displayed_separately_from_promo_status():
    row = _candidate(promo_status="active_estimated", period_certainty="estimated")
    row["display_status"] = enhancer.display_status(row)
    cleaned = enhancer.make_clean_row(row, review=False)
    assert cleaned["Status Promo"] == "Aktif (periode estimasi)"
    assert cleaned["Status Validasi Produk"] == "Valid"

    row["product_validation_status"] = "review"
    cleaned = enhancer.make_clean_row(row, review=True)
    assert cleaned["Status Promo"] == "Aktif (periode estimasi)"
    assert cleaned["Status Validasi Produk"] == "Perlu review"

# --- from test_export_quality_gate.py ---
def test_quality_gate_routes_unknown_merchant_to_review():
    row = _candidate(merchant_name="UNKNOWN")
    current, report = enhancer.apply_export_quality_gate([row])
    assert current == []
    assert report["status"] == "passed"
    assert report["routed_to_review_rows"] == 1
    assert "merchant_missing_or_unknown" in report["routed_rows"][0]["issues"]
    assert row["product_validation_status"] == "review"

# --- from test_export_quality_gate.py ---
def test_quality_gate_routes_unclassified_category_to_review():
    row = _candidate(product_text="Novel Zeta Volume 1")
    category, _ = enhancer.classify_promo_category(row)
    if category != "Lainnya / Perlu Review":
        # Use a category which the current taxonomy deliberately leaves unresolved.
        row["product_text"] = "Barang Xyz Blorpt 1 unit"
        category, _ = enhancer.classify_promo_category(row)
    assert category == "Lainnya / Perlu Review"
    current, report = enhancer.apply_export_quality_gate([row])
    assert current == []
    assert report["status"] == "passed"
    assert "category_requires_manual_review" in report["routed_rows"][0]["issues"]

# --- from test_export_quality_gate.py ---
def test_quality_gate_clears_qris_cashback_amount_from_product_price():
    row = _candidate(
        promo_price=2000,
        promo_price_evidence_text="Pembayaran QRIS cashback Rp2.000",
        normal_price=None,
        normal_price_evidence_text=None,
        offer_text="Pembayaran QRIS cashback Rp2.000",
        raw_line="Sunlight Jeruk 755 ml — pembayaran QRIS cashback Rp2.000",
        discount_percent=None,
        discount_percent_basis="not_available",
    )
    current, report = enhancer.apply_export_quality_gate([row])
    assert current == []
    assert report["status"] == "passed"
    assert "promo_price_looks_like_payment_or_purchase_condition" in report["routed_rows"][0]["issues"]
    assert row["product_validation_status"] == "review"
    assert row["promo_price"] is None

# --- from test_export_quality_gate.py ---
def test_quality_gate_quarantines_empty_or_generic_product_name_and_clears_amounts():
    row = _candidate(product_text="Potongan harga", original_product_text="Potongan harga")
    current, report = enhancer.apply_export_quality_gate([row])
    assert current == []
    assert report["status"] == "passed"
    assert "product_identity_empty_or_generic" in report["routed_rows"][0]["issues"]
    assert row["product_validation_status"] == "review"
    assert row["promo_price"] is None
    assert row["normal_price"] is None

# --- from test_export_quality_gate.py ---
def test_valid_product_price_evidence_passes_gate():
    row = _candidate()
    current, report = enhancer.apply_export_quality_gate([row])
    assert len(current) == 1
    assert report["status"] == "passed"
    assert report["routed_to_review_rows"] == 0
    assert enhancer.export_quality_gate_issues(current[0]) == []

# --- from test_export_quality_gate.py ---
def test_discount_over_100_percent_is_quarantined_and_not_displayed_as_discount():
    row = _candidate(discount_percent=150, discount_percent_basis="explicit_offer")
    current, report = enhancer.apply_export_quality_gate([row])
    assert current == []
    assert report["status"] == "passed"
    assert "product_discount_out_of_range" in report["routed_rows"][0]["issues"]
    assert row["product_validation_status"] == "review"
    assert row["discount_percent"] is None

# --- from test_export_quality_gate.py ---
def test_gate_does_not_publish_inferred_price_even_when_amount_text_matches():
    row = _candidate(price_quality_flag="price_inferred")
    current, report = enhancer.apply_export_quality_gate([row])
    assert current == []
    assert report["status"] == "passed"
    assert "promo_price_inferred_needs_review" in report["routed_rows"][0]["issues"]
    assert row["promo_price"] is None
    assert row["product_validation_status"] == "review"

# --- from test_export_quality_gate.py ---
def test_gate_routes_cross_source_price_conflict_to_review():
    row = _candidate(price_quality_flag="cross_source_price_disagreement")
    current, report = enhancer.apply_export_quality_gate([row])
    assert current == []
    assert report["status"] == "passed"
    assert "cross_source_price_disagreement" in report["routed_rows"][0]["issues"]
    assert row["product_validation_status"] == "review"

# --- from test_export_quality_gate.py ---
def test_explicit_discount_conflicting_with_same_row_prices_routes_to_review():
    row = _candidate(
        normal_price=17900,
        promo_price=10900,
        discount_percent=35.0,
        discount_percent_basis="explicit_offer",
        discount_percent_calculated=39.1,
        discount_savings_rp=7000,
        offer_text="Diskon: Hemat 35% | Harga Normal: Rp17.900 | Harga Promo: Rp10.900",
        raw_line="Cadbury Dairy Milk Roast Almond 52 g - Hemat 35%, normal Rp17.900, promo Rp10.900",
        discount_evidence_text="Hemat 35%",
    )
    current, report = enhancer.apply_export_quality_gate([row])
    assert current == []
    assert report["status"] == "passed"
    assert "explicit_discount_price_math_disagreement" in report["routed_rows"][0]["issues"]
    assert row["source_discount_claim_percent"] == 35.0
    assert row["discount_percent"] is None
    assert row["discount_percent_basis"] == "discount_price_mismatch_review"
    assert row["discount_percent_calculated"] == 39.1
    cleaned = enhancer.make_clean_row(row, review=True)
    assert cleaned["Diskon (%)"] is None
    assert cleaned["Klaim Diskon Sumber (Review) (%)"] == 35.0
    assert "39.1%" in cleaned["Catatan"]

# --- from test_export_quality_gate.py ---
def test_maximum_discount_claim_only_flags_when_price_math_exceeds_claim():
    acceptable = _candidate(
        normal_price=20000, promo_price=15000,
        discount_percent=30, discount_percent_basis="explicit_max",
        discount_percent_calculated=25.0,
        offer_text="Diskon hingga 30%, harga normal Rp20.000, harga promo Rp15.000",
    )
    assert enhancer.discount_price_consistency_issue(acceptable) is None
    excessive = dict(acceptable, discount_percent_calculated=36.0)
    assert enhancer.discount_price_consistency_issue(excessive) == "maximum_discount_below_price_calculation"

# --- from test_export_quality_gate.py ---
def test_row_freshness_is_visible_and_not_conflated_with_verification():
    recent = enhancer.classify_row_freshness("2026-10-24T10:00:00+07:00", now_dt=__import__("datetime").datetime.fromisoformat("2026-10-24T12:00:00+07:00"))
    historic = enhancer.classify_row_freshness("")
    assert recent == "fresh"
    assert historic == "historical_or_unverified"
    assert enhancer.classify_row_freshness("bukan-timestamp") == "invalid_timestamp"
    future = enhancer.classify_row_freshness(
        "2026-10-25T00:00:00+07:00",
        now_dt=__import__("datetime").datetime.fromisoformat("2026-10-24T12:00:00+07:00"),
    )
    assert future == "invalid_timestamp"
    row = _candidate(freshness_status="historical_or_unverified", scraped_at=None)
    cleaned = enhancer.make_clean_row(row)
    assert cleaned["Kesegaran Data"] == "Historis / timestamp tidak tersedia"
    assert cleaned["Verifikasi Sumber"] != cleaned["Kesegaran Data"]

# --- from test_export_quality_gate.py ---
def test_discount_conflict_in_existing_review_row_is_sanitized_too():
    row = _candidate(
        product_validation_status="review",
        normal_price=17900,
        promo_price=10900,
        discount_percent=35.0,
        discount_percent_basis="explicit_offer",
        discount_percent_calculated=39.1,
        offer_text="Hemat 35%, Harga Normal Rp17.900, Harga Promo Rp10.900",
        discount_evidence_text="Hemat 35%",
    )
    _, report = enhancer.apply_export_quality_gate([row])
    assert report["additional_existing_review_discount_rows"] == 1
    assert "explicit_discount_price_math_disagreement" in row["export_gate_flags"]
    assert row["source_discount_claim_percent"] == 35.0
    assert row["discount_percent"] is None
