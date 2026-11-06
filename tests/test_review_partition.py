from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from enrich_existing_promo_catalog_multisource import partition_current_review_rows  # noqa: E402


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
