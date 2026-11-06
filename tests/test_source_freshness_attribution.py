from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from promo_multisource_collector import (  # noqa: E402
    build_source_health_report,
    dedupe_rows,
)


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
