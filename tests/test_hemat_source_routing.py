from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

import promo_multisource_collector as collector


def test_hemat_seed_pages_are_single_retailer_catalogues():
    urls = collector.SOURCE_SEEDS["Hemat.id"]
    assert len(urls) == 7
    assert all("," not in url.split("/katalog-", 1)[1].split("/", 1)[0] for url in urls)
    assert {url.rstrip("/").rsplit("-", 1)[-1] for url in urls} >= {
        "alfamart", "indomaret", "alfamidi", "superindo", "hypermart", "yogya", "top"
    }


def test_hemat_listing_discovery_rejects_multi_retailer_comparison_urls():
    assert collector.is_listing_link(
        "Hemat.id", "https://www.hemat.id/katalog-yogya/", "Yogya"
    )
    assert collector.is_listing_link(
        "Hemat.id", "https://www.hemat.id/katalog-alfamart/promo-promo/", "Promo JSM Alfamart"
    )
    for retailer_pair in ("alfamart,yogya", "alfamart,superindo", "alfamart,indomaret"):
        assert not collector.is_listing_link(
            "Hemat.id", f"https://www.hemat.id/katalog-{retailer_pair}/", "Bandingkan katalog"
        )
        assert not collector.is_listing_link(
            "Hemat.id", f"https://www.hemat.id/katalog-{retailer_pair}/promo-promo/", "Promo"
        )


def test_hemat_discovery_only_follows_supported_single_retailer_slugs():
    assert collector.is_listing_link(
        "Hemat.id", "https://www.hemat.id/katalog-alfamidi/", "Alfamidi"
    )
    assert not collector.is_listing_link(
        "Hemat.id", "https://www.hemat.id/katalog-transmart/", "Transmart"
    )
    assert not collector.is_listing_link(
        "Hemat.id", "https://www.hemat.id/katalog-promo-terbaru/", "Katalog Promo"
    )
    assert not collector.is_listing_link(
        "Hemat.id", "https://www.hemat.id/katalog-transmart/", "Transmart"
    )
