from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

import enrich_existing_promo_catalog_multisource as enhancer


def test_hemat_catalog_prefers_specific_product_detail_url():
    row = {
        "source_name": "Hemat.id",
        "merchant_name": "Alfamart",
        "source_url": "https://www.hemat.id/katalog-alfamart,yogya/",
        "source_page_url": "https://www.hemat.id/katalog-alfamart,yogya/",
        "source_item_url": "https://www.hemat.id/harga/sania-beras-premium-5-kg/",
    }
    assert enhancer.preferred_source_url(row) == row["source_item_url"]


def test_legacy_hemat_comparison_page_falls_back_to_single_retailer_catalog():
    row = {
        "source_name": "Hemat.id",
        "merchant_name": "Yogya",
        "source_url": "https://www.hemat.id/katalog-alfamart,yogya/",
        "source_page_url": "https://www.hemat.id/katalog-alfamart,yogya/",
        "source_item_url": "https://www.hemat.id/katalog//",
    }
    assert enhancer.preferred_source_url(row) == "https://www.hemat.id/katalog-yogya/"


def test_unknown_merchant_keeps_exact_original_source_url():
    row = {
        "source_name": "Hemat.id",
        "merchant_name": "Unknown Retailer",
        "source_url": "https://www.hemat.id/katalog-alfamart,unknown-retailer/",
        "source_item_url": "https://www.hemat.id/katalog//",
    }
    assert enhancer.preferred_source_url(row) == row["source_url"]


def test_non_hemat_source_keeps_article_url_when_no_item_url():
    row = {
        "source_name": "Katalogpromosi.com",
        "source_url": "https://katalogpromosi.com/promo-mingguan/",
        "source_page_url": "https://katalogpromosi.com/promo-mingguan/",
        "source_item_url": "",
    }
    assert enhancer.preferred_source_url(row) == row["source_url"]


def test_clean_catalog_and_simple_workbook_use_preferred_source_url():
    row = {
        "source_name": "Hemat.id",
        "merchant_name": "Alfamart",
        "source_url": "https://www.hemat.id/katalog-alfamart,indomaret/",
        "source_page_url": "https://www.hemat.id/katalog-alfamart,indomaret/",
        "source_item_url": "https://www.hemat.id/harga/produk-contoh/",
        "product_text": "Produk Contoh 100 g",
        "promo_status": "active",
    }
    clean = enhancer.make_clean_row(row)
    simple = enhancer.make_simple_excel_row(row)
    assert clean["Sumber URL"] == row["source_item_url"]
    assert simple["Sumber URL"] == row["source_item_url"]


def test_hemat_category_item_url_is_more_specific_than_comparison_page():
    row = {
        "source_name": "Hemat.id",
        "merchant_name": "AEON",
        "source_url": "https://www.hemat.id/katalog-alfamart,courts/",
        "source_item_url": "https://www.hemat.id/katalog/biore.pembersih-penyegar-wajah/",
    }
    assert enhancer.preferred_source_url(row) == row["source_item_url"]
