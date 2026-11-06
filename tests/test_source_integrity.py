"""Grouped regression tests. Cases are organized by functional area."""



from __future__ import annotations

import csv

from datetime import date

from pathlib import Path

from bs4 import BeautifulSoup

import enrich_existing_promo_catalog_multisource as enhancer

import promo_history

import promo_multisource_collector as collector

from promo_merchant_utils import infer_hemat_retailer_from_item_url

from promo_names import clean_product_name

import sys

from promo_merchant_utils import (  # noqa: E402
    hemat_merchant_scope_issue,
    hemat_retailer_scope_from_url,
)

from promo_price_reference import (  # noqa: E402
    REFERENCE_FIELDS,
    load_reference_database,
    update_reference_database,
)



# --- from test_source_integrity_guardrails.py ---
def test_leading_missing_brand_placeholders_are_removed_but_raw_text_can_be_kept():
    assert clean_product_name("None Mangga Alpukat 100 g") == "Mangga Alpukat 100 g"
    assert clean_product_name("null Mangga Manalagi 100 gr") == "Mangga Manalagi 100 g"
    assert clean_product_name("undefined Anggur Shine Muscat 1 pcs") == "Anggur Shine Muscat 1 pcs"
    assert clean_product_name("Mangga None Brand 100 g") == "Mangga None Brand 100 g"

# --- from test_source_integrity_guardrails.py ---
def test_hemat_item_url_prefix_is_strong_merchant_evidence_only_on_item_detail_urls():
    assert infer_hemat_retailer_from_item_url(
        "https://www.hemat.id/katalog/alfamart.popok-dewasa-celana/"
    ) == "Alfamart"
    assert infer_hemat_retailer_from_item_url(
        "https://www.hemat.id/harga/lottemart.sania-minyak-2-l/"
    ) == "Lotte Mart"
    assert infer_hemat_retailer_from_item_url(
        "https://www.hemat.id/katalog/buah-mangga/"
    ) is None
    assert infer_hemat_retailer_from_item_url(
        "https://www.hemat.id/katalog-alfamart,yogya/"
    ) is None

# --- from test_source_integrity_guardrails.py ---
def test_hemat_item_url_overrides_wrong_comparison_page_merchant_and_cleans_placeholder(tmp_path):
    raw = {
        "product_text": "Alfamart Adult Diapers Pants M-8 8 pcs",
        "original_product_text": "Alfamart Adult Diapers Pants M-8 8 pcs",
        "merchant_name": "AEON",
        "campaign_title": "Promo Unggulan Alfamart VS Courts minggu ini",
        "normal_price": "49900",
        "promo_price": "37900",
        "offer_text": "Harga Promo Rp37.900 Harga Normal Rp49.900",
        "valid_from": "2026-11-01",
        "valid_until": "2026-11-15",
        "period_precision": "until",
        "promo_status": "active_estimated",
        "source_name": "Hemat.id",
        "source_type": "aggregator_product_listing",
        "verification_status": "aggregator_only",
        "source_url": "https://www.hemat.id/katalog-alfamart,courts/",
        "source_page_url": "https://www.hemat.id/katalog-alfamart,courts/",
        "source_item_url": "https://www.hemat.id/katalog/alfamart.popok-dewasa-celana/",
        "raw_line": "Alfamart Adult Diapers Pants M-8 8 pcs Harga Promo Rp37.900 Harga Normal Rp49.900",
    }
    path = tmp_path / "source.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(raw))
        writer.writeheader()
        writer.writerow(raw)

    rows = enhancer.load_source(path, "hemat.csv")
    assert len(rows) == 1
    assert rows[0]["merchant_name"] == "Alfamart"
    assert rows[0]["merchant_resolution_method"] == "hemat_item_url_prefix"
    assert rows[0]["merchant_evidence_text"] == raw["source_item_url"]

    raw["product_text"] = "None Mangga Alpukat 100 g"
    raw["original_product_text"] = raw["product_text"]
    raw["merchant_name"] = "Tip Top"
    raw["source_item_url"] = "https://www.hemat.id/katalog/buah-mangga/"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(raw))
        writer.writeheader()
        writer.writerow(raw)
    cleaned = enhancer.load_source(path, "hemat.csv")
    assert cleaned[0]["product_text"] == "Mangga Alpukat 100 g"
    assert cleaned[0]["merchant_name"] == "Tip Top"
    assert cleaned[0]["merchant_resolution_method"] != "hemat_item_url_prefix"

# --- from test_source_integrity_guardrails.py ---
def test_hemat_card_explicit_expired_label_is_preserved_as_source_evidence():
    html = """<html><head><title>Promo Unggulan Alfamart VS Courts minggu ini</title></head>
    <body><div class="product-card">
      <a href="/katalog/alfamart.popok-dewasa-celana/">Alfamart Adult Diapers Pants M-8 8 pcs Harga Promo Rp37.900 Harga Normal Rp49.900</a>
      <span class="status">Expired</span><a href="/store/alfamart">Alfamart</a>
    </div></body></html>"""
    rows = collector.extract_hemat_cards(
        BeautifulSoup(html, "html.parser"),
        "https://www.hemat.id/katalog-alfamart,courts/",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["merchant_name"] == "Alfamart"
    assert row["source_explicit_expired"] is True
    assert row["source_status_evidence_text"] == "Expired"

# --- from test_source_integrity_guardrails.py ---
def test_explicit_expired_source_label_overrides_future_estimated_end_date():
    status = enhancer.current_status(
        "2026-11-01", "2026-11-30", "until", None,
        source_status="expired", source_explicit_expired=True,
    )
    assert status == "expired"

    history_status = promo_history.current_promo_status(
        {
            "promo_status": "expired",
            "source_explicit_expired": "true",
            "valid_from": "2026-11-01",
            "valid_until": "2026-11-30",
            "period_precision": "until",
        },
        today=date(2026, 11, 4),
    )
    assert history_status == "expired"

# --- from test_source_integrity_guardrails.py ---
def test_same_offer_conflicting_estimated_dates_are_quarantined_not_extended():
    base = {
        "merchant_name": "Tip Top",
        "product_text": "Mangga Alpukat 100 g",
        "offer_text": "Harga Promo Rp1.950",
        "promo_price": 1950,
        "normal_price": 3722,
        "deal_type": "Diskon Harga",
        "campaign_title": "Promo Unggulan Tip Top minggu ini",
        "period_precision": "until",
        "period_certainty": "estimated",
        "promo_status": "active_estimated",
        "valid_from": "",
        "source_explicit_expired": False,
    }
    first = {**base, "valid_until": "2026-11-15"}
    second = {**base, "valid_until": "2026-12-27"}
    marked = enhancer.mark_overlapping_offers([first, second])

    assert len(marked) == 2
    assert all(row["promo_status"] == "unknown" for row in marked)
    assert all(row["period_certainty"] == "unknown" for row in marked)
    assert all(
        "same_offer_conflicting_estimated_periods" in (row.get("period_flags") or "")
        for row in marked
    )
    assert all(enhancer.has_material_period_conflict(row) for row in marked)

# --- from test_source_integrity_guardrails.py ---
def test_expired_offer_is_not_merged_with_active_offer_from_another_source():
    base = {
        "merchant_name": "Alfamart",
        "product_text": "Alfamart Adult Diapers Pants M-8 8 pcs",
        "offer_text": "Harga Promo Rp37.900 Harga Normal Rp49.900",
        "promo_price": 37900,
        "normal_price": 49900,
        "deal_type": "Diskon Persentase",
        "valid_from": "2026-11-01",
        "valid_until": "2026-11-15",
        "period_precision": "range",
        "period_flags": "",
    }
    expired = {
        **base,
        "promo_status": "expired",
        "source_explicit_expired": True,
        "source_name": "Hemat.id",
        "source_url": "https://www.hemat.id/harga/alfamart.popok-dewasa-celana/",
    }
    active = {
        **base,
        "promo_status": "active",
        "source_explicit_expired": False,
        "source_name": "Katalogpromosi.com",
        "source_url": "https://katalogpromosi.com/promo/alfamart/",
    }
    assert not enhancer._equivalent_offer_rows(expired, active)

# --- from test_source_integrity_guardrails.py ---
def test_expired_label_from_one_hemat_card_does_not_leak_to_neighbor_card():
    html = """<html><head><title>Promo Unggulan Alfamart VS Courts minggu ini</title></head>
    <body><div class="product-grid">
      <div class="product-card">
        <a href="/katalog/alfamart.popok-dewasa-celana/">Alfamart Adult Diapers Pants M-8 8 pcs Harga Promo Rp37.900</a>
        <span class="status">Expired</span>
      </div>
      <div class="product-card">
        <a href="/katalog/alfamart.susu-uht-1l/">Alfamart Fresh Milk 1 L Harga Promo Rp18.900</a>
        <span class="status">Promo</span>
      </div>
    </div></body></html>"""
    rows = collector.extract_hemat_cards(
        BeautifulSoup(html, "html.parser"),
        "https://www.hemat.id/katalog-alfamart,courts/",
    )
    assert len(rows) == 2
    by_name = {row["product_text"]: row for row in rows}
    expired = by_name["Alfamart Adult Diapers Pants M-8 8 pcs"]
    current = next(row for name, row in by_name.items() if "Fresh Milk" in name)
    assert expired["source_explicit_expired"] is True
    assert expired["promo_status"] == "expired"
    assert current.get("source_explicit_expired") in (None, False)
    assert current["promo_status"] != "expired"

# --- from test_source_integrity_guardrails.py ---
def test_explicitly_expired_future_offer_is_not_carried_forward_from_history():
    rows = promo_history.seed_history_from_snapshot(
        [{
            "product_text": "Alfamart Adult Diapers Pants M-8 8 pcs",
            "merchant_name": "Alfamart",
            "promo_status": "expired",
            "source_explicit_expired": "true",
            "valid_from": "2026-11-01",
            "valid_until": "2026-11-30",
            "period_precision": "until",
            "source_name": "Hemat.id",
            "source_url": "https://www.hemat.id/harga/alfamart.popok-dewasa-celana/",
            "scraped_at": "2026-11-04T08:00:00+07:00",
        }],
        today=date(2026, 11, 4),
    )
    assert len(rows) == 1
    assert rows[0]["history_promo_status"] == "expired"
    assert promo_history.carry_forward_rows(rows, [], today=date(2026, 11, 4)) == []

# --- from test_source_integrity_guardrails.py ---
def test_launcher_has_offline_rebuild_mode_and_keeps_live_collector_out_of_rebuild_branch():
    run_bat = Path(__file__).resolve().parents[1] / "run.bat"
    text = run_bat.read_text(encoding="utf-8")
    assert '"--rebuild-from-last-snapshot" set "MODE=rebuild"' in text
    rebuild_start = text.index("\n:rebuild_last_snapshot\n")
    rebuild_end = text.index("\n:snapshot_missing\n", rebuild_start)
    rebuild_block = text[rebuild_start:rebuild_end]
    assert "enrich_existing_promo_catalog_multisource.py" in rebuild_block
    assert "promo_multisource_collector.py" not in rebuild_block
    assert "Tidak mengambil data live" in rebuild_block or "tanpa mengambil data live" in rebuild_block.casefold()

# --- from test_reference_merchant_scope.py ---
SRC = Path(__file__).resolve().parents[1] / "src"

# --- from test_reference_merchant_scope.py ---
sys.path.insert(0, str(SRC))

# --- from test_reference_merchant_scope.py ---
TODAY = date(2026, 11, 4)

# --- from test_reference_merchant_scope.py ---
def _record(**overrides):
    row = {field: "" for field in REFERENCE_FIELDS}
    row.update({
        "merchant_name": "AEON",
        "product_text": "Sania Minyak Goreng 2 L",
        "normal_price": "43900",
        "observed_at": "2026-11-03T10:00:00+07:00",
        "source_name": "Hemat.id",
        "source_url": "https://www.hemat.id/katalog-alfamart,courts/",
        "evidence_text": "Harga Normal Rp43.900",
        "record_origin": "observed_scrape",
        "verification_status": "aggregator_only",
    })
    row.update(overrides)
    return row

# --- from test_reference_merchant_scope.py ---
def _write_db(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REFERENCE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

# --- from test_reference_merchant_scope.py ---
def test_hemat_catalog_url_exposes_its_retailer_scope():
    assert hemat_retailer_scope_from_url("https://www.hemat.id/katalog-alfamart/") == {"Alfamart"}
    assert hemat_retailer_scope_from_url("https://www.hemat.id/katalog-alfamart,courts/promo-promo/") == {"Alfamart", "Courts"}
    assert hemat_retailer_scope_from_url("https://www.hemat.id/katalog/biore.pembersih-wajah/") is None

# --- from test_reference_merchant_scope.py ---
def test_hemat_reference_outside_comparison_scope_is_quarantined(tmp_path):
    path = tmp_path / "reference.csv"
    row = _record(merchant_name="AEON")
    _write_db(path, [row])
    diagnostics: list[dict] = []
    records = load_reference_database(path, diagnostics=diagnostics)
    assert records == []
    assert len(diagnostics) == 1
    assert diagnostics[0]["reference_diagnostic"] == "merchant_not_in_hemat_catalogue_scope"

# --- from test_reference_merchant_scope.py ---
def test_merchant_inside_comparison_scope_remains_usable(tmp_path):
    path = tmp_path / "reference.csv"
    _write_db(path, [_record(merchant_name="Courts")])
    records = load_reference_database(path)
    assert len(records) == 1
    assert records[0]["merchant_name"] == "Courts"

# --- from test_reference_merchant_scope.py ---
def test_reference_database_update_rejects_new_merchant_scope_conflict(tmp_path):
    path = tmp_path / "state" / "product_price_reference.csv"
    row = {
        "merchant_name": "AEON",
        "product_text": "Sania Minyak Goreng 2 L",
        "normal_price": 43900,
        "promo_price": 39900,
        "price_basis": "offer_price",
        "normal_price_evidence_text": "Harga Normal Rp43.900",
        "promo_price_evidence_text": "Harga Promo Rp39.900",
        "product_validation_status": "eligible",
        "freshness_status": "fresh",
        "scraped_at": "2026-11-04T10:00:00+07:00",
        "source_name": "Hemat.id",
        "source_type": "aggregator",
        "source_page_url": "https://www.hemat.id/katalog-alfamart,courts/",
        "source_url": "https://www.hemat.id/katalog-alfamart,courts/",
        "verification_status": "aggregator_only",
        "region_or_channel": "",
        "campaign_title": "Promo Alfamart vs Courts",
        "retained_from_previous_run": False,
        "price_quality_flag": None,
    }
    summary = update_reference_database(path, [row], TODAY)
    assert summary["observations_added"] == 0
    assert summary["rejected_merchant_scope_conflicts"] == 1
    assert load_reference_database(path) == []

# --- from test_reference_merchant_scope.py ---
def test_single_retailer_scope_rejects_other_retailer_but_unknown_source_is_untouched():
    assert hemat_merchant_scope_issue("Indomaret", "https://www.hemat.id/katalog-alfamart/") == "merchant_not_in_hemat_catalogue_scope"
    assert hemat_merchant_scope_issue("Alfamart", "https://www.hemat.id/katalog-alfamart/") is None
    assert hemat_merchant_scope_issue("AEON", "https://example.test/catalog/aeon/") is None
