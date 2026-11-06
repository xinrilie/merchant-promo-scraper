"""Grouped regression tests. Cases are organized by functional area."""



from __future__ import annotations

import csv

import sys

from datetime import date

from pathlib import Path

from openpyxl import load_workbook

from promo_sku_review import (  # noqa: E402
    classify_candidate,
    export_review_workbook,
    import_review_approvals,
)

from promo_names import load_product_name_aliases, product_name_matching_key



# --- from test_sku_review_workflow.py ---
SRC = Path(__file__).resolve().parents[1] / "src"

# --- from test_sku_review_workflow.py ---
sys.path.insert(0, str(SRC))

# --- from test_sku_review_workflow.py ---
def candidate(query: str, reference: str, **overrides):
    row = {
        "query_product": query,
        "query_merchant": "Alfamart",
        "candidate_product": reference,
        "candidate_merchant": "Indomaret",
        "candidate_normal_price": "24000",
        "candidate_observed_at": "2026-11-03T10:00:00+07:00",
        "candidate_source_name": "Hemat.id",
        "candidate_source_url": "https://www.hemat.id/harga/contoh-produk/",
        "similarity_score": "0.91",
        "automatic_match_allowed": "no",
    }
    row.update(overrides)
    return row

# --- from test_sku_review_workflow.py ---
def test_known_brand_conflicts_are_rejected_before_similarity():
    samples = [
        ("Bimoli Minyak Goreng Spesial 2 L", "Sania Minyak Goreng 2 L"),
        ("Le Minerale Air Mineral 600 ml", "Nestle Pure Life Air Mineral 600 ml"),
        ("AQUA Air Mineral 600 ml", "Nestle Pure Life Air Mineral 600 ml"),
        ("Barelab Facial Wash 100 ml", "Lang Facial Wash 100 ml"),
    ]
    for query, reference in samples:
        result = classify_candidate(candidate(query, reference), today=date(2026, 11, 4))
        assert result["Klasifikasi Kandidat"] == "reject_brand_mismatch"
        assert result["Keputusan"] == "TOLAK"
        assert result["Kecocokan Merek"] == "false"

# --- from test_sku_review_workflow.py ---
def test_alternative_size_does_not_match_a_single_fixed_pack():
    result = classify_candidate(
        candidate("Bango Kecap Manis 920 / 950 g", "Bango Kecap Manis 950 g"),
        today=date(2026, 11, 4),
    )
    assert result["Klasifikasi Kandidat"] == "reject_package_mismatch"
    assert result["Kecocokan Ukuran"] == "false"

# --- from test_sku_review_workflow.py ---
def test_different_formula_or_flavour_is_rejected():
    result = classify_candidate(
        candidate("Ciptadent Pasta Gigi Cool Mint 190 g", "Ciptadent Pasta Gigi Fresh Mint 190 g"),
        today=date(2026, 11, 4),
    )
    assert result["Klasifikasi Kandidat"] == "reject_variant_mismatch"

# --- from test_sku_review_workflow.py ---
def test_different_explicit_packaging_is_rejected():
    result = classify_candidate(
        candidate("Tropical Minyak Goreng PET 2 L", "Tropical Minyak Goreng Pouch 2 L"),
        today=date(2026, 11, 4),
    )
    assert result["Klasifikasi Kandidat"] == "reject_packaging_mismatch"

# --- from test_sku_review_workflow.py ---
def test_same_sku_across_merchants_is_market_reference_only_not_automatic_alias():
    result = classify_candidate(
        candidate("Bango Kecap Manis Pouch 700 g", "Bango Kecap Manis 700 g"),
        today=date(2026, 11, 4),
    )
    assert result["Kecocokan Merek"] == "true"
    assert result["Kecocokan Ukuran"] == "true"
    assert result["Merchant Sama"] == "false"
    assert result["Cakupan Merchant"] == "cross_merchant_market_reference_only"
    assert result["Klasifikasi Kandidat"] == "manual_review_same_brand_package_variant"
    assert result["Keputusan"] == "BELUM DIREVIEW"

# --- from test_sku_review_workflow.py ---
def test_stale_candidate_is_explicitly_archival_only():
    result = classify_candidate(
        candidate("Bango Kecap Manis 700 g", "Bango Kecap Manis 700 g", candidate_observed_at="2026-09-01"),
        today=date(2026, 11, 4),
    )
    assert "hanya untuk arsip" in result["Rekomendasi"]
    assert result["Keputusan"] == "BELUM DIREVIEW"

# --- from test_sku_review_workflow.py ---
def test_review_workbook_exports_candidates_and_preserves_decisions(tmp_path):
    source = tmp_path / "candidates.csv"
    fields = list(candidate("Bango Kecap Manis 700 g", "Bango Kecap Manis 700 g"))
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(candidate("Bango Kecap Manis Pouch 700 g", "Bango Kecap Manis 700 g"))
    output = tmp_path / "Review_Kandidat_SKU.xlsx"
    summary = export_review_workbook(source, output, today=date(2026, 11, 4))
    assert summary["rows"] == 1
    wb = load_workbook(output)
    ws = wb["Review SKU"]
    headers = [cell.value for cell in ws[1]]
    decision_col = headers.index("Keputusan") + 1
    assert ws.cell(2, decision_col).value == "BELUM DIREVIEW"
    ws.cell(2, decision_col).value = "TOLAK"
    ws.cell(2, headers.index("Catatan Reviewer") + 1).value = "Bukan SKU yang sama"
    wb.save(output)
    wb.close()

    export_review_workbook(source, output, today=date(2026, 11, 4))
    wb = load_workbook(output, read_only=True, data_only=True)
    try:
        ws = wb["Review SKU"]
        header = [cell.value for cell in ws[1]]
        row = dict(zip(header, next(ws.iter_rows(min_row=2, max_row=2, values_only=True))))
        assert row["Keputusan"] == "TOLAK"
        assert row["Catatan Reviewer"] == "Bukan SKU yang sama"
    finally:
        wb.close()

# --- from test_sku_review_workflow.py ---
def test_unknown_brand_alias_requires_evidence_when_importing_review(tmp_path):
    source = tmp_path / "candidates.csv"
    row = candidate("Produk Lokal Teh Celup 25 bags", "Produk Lokal Teh Celup 25 bags")
    # Force a different canonical spelling while preserving package and variant signatures.
    row["candidate_product"] = "Produk Lokal Teh Celup 25 bags Premium"
    row["similarity_score"] = "0.95"
    fields = list(row)
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(row)
    review = tmp_path / "review.xlsx"
    export_review_workbook(source, review, today=date(2026, 11, 4))

    wb = load_workbook(review)
    ws = wb["Review SKU"]
    headers = [cell.value for cell in ws[1]]
    ws.cell(2, headers.index("Keputusan") + 1).value = "APPROVE_ALIAS"
    ws.cell(2, headers.index("Catatan Reviewer") + 1).value = "Nama SKU sudah diperiksa manual"
    # Unknown brand needs a direct evidence URL on new imports.
    wb.save(review)
    wb.close()
    aliases = tmp_path / "aliases.csv"
    result = import_review_approvals(review, aliases)
    assert result["approved_aliases_added_or_updated"] == 0
    assert result["rejected_decisions"] == 1
    assert not aliases.read_text(encoding="utf-8-sig").strip().endswith(",yes,,")

# --- from test_sku_review_workflow.py ---
def test_approved_alias_loader_keeps_legacy_note_compatibility_and_rejects_brand_conflict(tmp_path):
    aliases = tmp_path / "aliases.csv"
    aliases.write_text(
        "alias,canonical_name,approved,note\n"
        "Sari Wangi Teh Celup 25 bags,SariWangi Teh Celup 25 bags,true,Spelling checked manually\n"
        "Bimoli Minyak Goreng 2 L,Sania Minyak Goreng 2 L,true,Wrong brand\n",
        encoding="utf-8-sig",
    )
    mapping = load_product_name_aliases(aliases)
    assert mapping
    assert len(mapping) == 1
    assert product_name_matching_key("Sari Wangi Teh Celup 25 bags", mapping) == product_name_matching_key(
        "SariWangi Teh Celup 25 bags"
    )
    assert product_name_matching_key("Bimoli Minyak Goreng 2 L", mapping) != product_name_matching_key(
        "Sania Minyak Goreng 2 L"
    )

# --- from test_sku_review_workflow.py ---
def test_known_brand_alias_can_be_imported_after_manual_approval(tmp_path):
    source = tmp_path / "candidates.csv"
    row = candidate("Bango Kecap Manis Pch 700 g", "Bango Kecap Manis 700 g")
    fields = list(row)
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(row)
    review = tmp_path / "review.xlsx"
    export_review_workbook(source, review, today=date(2026, 11, 4))

    wb = load_workbook(review)
    ws = wb["Review SKU"]
    headers = [cell.value for cell in ws[1]]
    ws.cell(2, headers.index("Keputusan") + 1).value = "APPROVE_ALIAS"
    ws.cell(2, headers.index("Bukti Identitas SKU (URL)") + 1).value = "https://bango.co.id/products/kecap-manis"
    ws.cell(2, headers.index("Catatan Reviewer") + 1).value = "SKU, ukuran, dan merek sudah diperiksa."
    wb.save(review)
    wb.close()

    aliases = tmp_path / "config" / "product_name_aliases.csv"
    result = import_review_approvals(review, aliases)
    assert result["approved_aliases_added_or_updated"] == 1
    assert result["rejected_decisions"] == 0
    mapping = load_product_name_aliases(aliases)
    assert mapping
    assert product_name_matching_key("Bango Kecap Manis Pch 700 g", mapping) == product_name_matching_key(
        "Bango Kecap Manis 700 g"
    )
