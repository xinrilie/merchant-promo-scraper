from __future__ import annotations

import csv
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import enrich_existing_promo_catalog_multisource as enhancer  # noqa: E402
from test_simple_excel import base_row  # noqa: E402


def test_carried_forward_classifier_recognizes_only_nonfresh_rows():
    assert enhancer.row_is_carried_forward({"retained_from_previous_run": "true"})
    assert enhancer.row_is_carried_forward({"freshness_status": "preserved_previous"})
    assert enhancer.row_is_carried_forward({"freshness_status": "mixed:preserved_previous"})
    assert not enhancer.row_is_carried_forward({"freshness_status": "mixed:fresh|preserved_previous"})
    assert not enhancer.row_is_carried_forward({"freshness_status": "fresh"})


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
