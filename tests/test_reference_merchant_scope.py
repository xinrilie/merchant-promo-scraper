from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from promo_merchant_utils import (  # noqa: E402
    hemat_merchant_scope_issue,
    hemat_retailer_scope_from_url,
)
from promo_price_reference import (  # noqa: E402
    REFERENCE_FIELDS,
    load_reference_database,
    update_reference_database,
)

TODAY = date(2026, 11, 4)


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


def _write_db(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REFERENCE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def test_hemat_catalog_url_exposes_its_retailer_scope():
    assert hemat_retailer_scope_from_url("https://www.hemat.id/katalog-alfamart/") == {"Alfamart"}
    assert hemat_retailer_scope_from_url("https://www.hemat.id/katalog-alfamart,courts/promo-promo/") == {"Alfamart", "Courts"}
    assert hemat_retailer_scope_from_url("https://www.hemat.id/katalog/biore.pembersih-wajah/") is None


def test_hemat_reference_outside_comparison_scope_is_quarantined(tmp_path):
    path = tmp_path / "reference.csv"
    row = _record(merchant_name="AEON")
    _write_db(path, [row])
    diagnostics: list[dict] = []
    records = load_reference_database(path, diagnostics=diagnostics)
    assert records == []
    assert len(diagnostics) == 1
    assert diagnostics[0]["reference_diagnostic"] == "merchant_not_in_hemat_catalogue_scope"


def test_merchant_inside_comparison_scope_remains_usable(tmp_path):
    path = tmp_path / "reference.csv"
    _write_db(path, [_record(merchant_name="Courts")])
    records = load_reference_database(path)
    assert len(records) == 1
    assert records[0]["merchant_name"] == "Courts"


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


def test_single_retailer_scope_rejects_other_retailer_but_unknown_source_is_untouched():
    assert hemat_merchant_scope_issue("Indomaret", "https://www.hemat.id/katalog-alfamart/") == "merchant_not_in_hemat_catalogue_scope"
    assert hemat_merchant_scope_issue("Alfamart", "https://www.hemat.id/katalog-alfamart/") is None
    assert hemat_merchant_scope_issue("AEON", "https://example.test/catalog/aeon/") is None
