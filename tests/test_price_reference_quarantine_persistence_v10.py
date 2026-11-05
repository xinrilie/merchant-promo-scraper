from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from enrich_existing_promo_catalog_multisource import (  # noqa: E402
    load_price_reference_quarantine,
    write_price_reference_quarantine,
)


def test_quarantine_records_persist_when_later_run_has_no_new_conflicts(tmp_path):
    path = tmp_path / "runtime" / "price_reference_quarantine.csv"
    record = {
        "reference_key": "sku-1|aeon|hemat",
        "merchant_name": "AEON",
        "product_text": "Sania Minyak Goreng 2 L",
        "normal_price": "43900",
        "source_name": "Hemat.id",
        "source_url": "https://www.hemat.id/katalog-alfamart,courts/",
        "reference_diagnostic": "merchant_not_in_hemat_catalogue_scope",
    }

    assert write_price_reference_quarantine([record], path=path) == 1
    assert write_price_reference_quarantine([], path=path) == 0

    loaded = load_price_reference_quarantine(path)
    assert len(loaded) == 1
    assert loaded[0]["merchant_name"] == "AEON"
    assert loaded[0]["reference_diagnostic"] == "merchant_not_in_hemat_catalogue_scope"


def test_quarantine_upsert_deduplicates_same_reference_key(tmp_path):
    path = tmp_path / "runtime" / "price_reference_quarantine.csv"
    first = {
        "reference_key": "sku-1|aeon|hemat",
        "merchant_name": "AEON",
        "product_text": "Sania Minyak Goreng 2 L",
        "source_url": "https://www.hemat.id/katalog-alfamart,courts/",
        "reference_diagnostic": "merchant_not_in_hemat_catalogue_scope",
    }
    corrected = {**first, "reference_diagnostic": "reviewed_not_restored"}

    write_price_reference_quarantine([first], path=path)
    write_price_reference_quarantine([corrected], path=path)

    loaded = load_price_reference_quarantine(path)
    assert len(loaded) == 1
    assert loaded[0]["reference_diagnostic"] == "reviewed_not_restored"


def test_workbook_exposes_quarantine_sheet_and_keeps_its_records_visible(tmp_path, monkeypatch):
    from openpyxl import load_workbook
    import enrich_existing_promo_catalog_multisource as enhancer

    monkeypatch.setattr(enhancer, "PRICE_REFERENCE_CSV", tmp_path / "state" / "price_reference.csv")
    monkeypatch.setattr(enhancer, "MARKET_REFERENCE_CSV", tmp_path / "state" / "market_reference.csv")
    monkeypatch.setattr(enhancer, "CATEGORY_REVIEW_LIST_CSV", tmp_path / "config" / "not-present.csv")

    record = {
        "reference_key": "sku-1|aeon|hemat",
        "merchant_name": "AEON",
        "product_text": "Sania Minyak Goreng 2 L",
        "normal_price": "43900",
        "observed_at": "2026-11-03T10:00:00+07:00",
        "source_name": "Hemat.id",
        "source_url": "https://www.hemat.id/katalog-alfamart,courts/",
        "reference_diagnostic": "merchant_not_in_hemat_catalogue_scope",
    }
    workbook_path = tmp_path / "output" / "catalog.xlsx"
    workbook_path.parent.mkdir(parents=True, exist_ok=True)
    assert enhancer.write_excel_catalog(
        workbook_path, [], [], [], [], [], [], {"status": "passed", "issue_counts": {}}, [record]
    )

    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        assert "Referensi Dikarantina" in workbook.sheetnames
        sheet = workbook["Referensi Dikarantina"]
        assert sheet.sheet_state == "visible"
        rows = list(sheet.iter_rows(values_only=True))
        assert len(rows) == 2
        assert rows[1][0] == "AEON"
        assert rows[1][-1] == "merchant_not_in_hemat_catalogue_scope"
        for title in ("Promo", "Promo Aktif - Review", "Perlu Diperiksa"):
            assert title in workbook.sheetnames
    finally:
        workbook.close()
