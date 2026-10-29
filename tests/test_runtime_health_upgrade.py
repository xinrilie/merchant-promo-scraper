from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import check_runtime
import enrich_existing_promo_catalog_multisource as enhancer
from source_health_check import build_summary

JAKARTA = ZoneInfo("Asia/Jakarta")


def test_runtime_only_check_does_not_require_pytest(monkeypatch):
    imports = []

    def fake_import(name):
        imports.append(name)
        return object()

    monkeypatch.setattr(check_runtime.importlib, "import_module", fake_import)
    monkeypatch.setattr(check_runtime.sys, "prefix", sys.prefix)
    issues = check_runtime.check_runtime(dev=False)
    assert issues == []
    assert set(imports) == {"requests", "bs4", "openpyxl"}
    assert "pytest" not in imports


def test_dev_check_also_requires_pytest(monkeypatch):
    imports = []

    def fake_import(name):
        imports.append(name)
        return object()

    monkeypatch.setattr(check_runtime.importlib, "import_module", fake_import)
    issues = check_runtime.check_runtime(dev=True)
    assert issues == []
    assert set(imports) == {"requests", "bs4", "openpyxl", "pytest"}


def test_price_reference_seed_copied_once_to_mutable_state(tmp_path):
    seed = tmp_path / "seed.csv"
    state = tmp_path / "state" / "price.csv"
    seed.write_text("merchant_name,product_text\nAlfamart,Susu 1 l\n", encoding="utf-8")

    assert enhancer.initialize_price_reference_database(state, seed) == "seeded"
    assert state.read_text(encoding="utf-8") == seed.read_text(encoding="utf-8")

    seed.write_text("merchant_name,product_text\nUpdated,Changed\n", encoding="utf-8")
    assert enhancer.initialize_price_reference_database(state, seed) == "existing"
    assert "Alfamart" in state.read_text(encoding="utf-8")
    assert "Updated" not in state.read_text(encoding="utf-8")


def test_health_summary_marks_partial_source_and_preserved_rows():
    now = datetime(2026, 10, 29, 9, 0, tzinfo=JAKARTA)
    log = {
        "built_at": "2026-10-29T08:59:00+07:00",
        "reference_date": "2026-10-29",
        "image_references_found": 12,
        "source_health": {
            "Hemat.id": {"status": "fresh", "product_rows_in_output": 20, "fresh_product_rows": 20},
            "Katalogpromosi.com": {"status": "preserved_previous", "product_rows_in_output": 4, "preserved_previous_rows": 4},
            "Scanharga.com": {"status": "request_failed", "product_rows_in_output": 0},
        },
    }
    result = build_summary(log, now=now)
    assert result["overall_status"] == "partial"
    assert result["product_rows_in_source_outputs"] == 24
    assert result["image_references_found"] == 12
    assert result["ocr_used"] is False
    assert result["sources"]["Katalogpromosi.com"]["health"] == "using_previous_data"
    assert any("Scanharga.com" in warning for warning in result["warnings"])
    assert result["_exit_code"] == 0


def test_health_summary_fails_when_all_sources_have_no_data():
    log = {
        "built_at": "2026-10-29T08:59:00+07:00",
        "source_health": {
            name: {"status": "request_failed", "product_rows_in_output": 0}
            for name in ("Hemat.id", "Katalogpromosi.com", "Scanharga.com")
        },
    }
    now = datetime(2026, 10, 29, 9, 0, tzinfo=JAKARTA)
    result = build_summary(log, now=now)
    assert result["overall_status"] == "no_data"
    assert result["_exit_code"] == 2
    assert result["product_rows_in_source_outputs"] == 0
