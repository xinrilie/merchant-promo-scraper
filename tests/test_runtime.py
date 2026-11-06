"""Grouped regression tests. Cases are organized by functional area."""



from __future__ import annotations

from pathlib import Path

import sys

from datetime import datetime

from zoneinfo import ZoneInfo

import check_runtime

import enrich_existing_promo_catalog_multisource as enhancer

from source_health_check import build_summary

import csv

import json

from openpyxl import Workbook

from verify_outputs import verify_outputs



# --- from test_launcher_workflows.py ---
def test_launcher_has_sku_review_commands_and_unique_labels():
    run_bat = Path(__file__).resolve().parents[1] / "run.bat"
    text = run_bat.read_text(encoding="utf-8")
    assert '"--export-sku-review" set "MODE=sku_export"' in text
    assert '"--import-sku-review" set "MODE=sku_import"' in text
    assert 'goto :export_sku_review' in text
    assert 'goto :import_sku_review' in text
    labels = [line.strip().casefold() for line in text.splitlines() if line.startswith(":")]
    assert len(labels) == len(set(labels)), f"Duplicate batch labels: {labels}"
    rebuild_start = text.index("\n:rebuild_last_snapshot\n")
    rebuild_end = text.index("\n:export_sku_review\n", rebuild_start)
    rebuild = text[rebuild_start:rebuild_end].casefold()
    assert "enrich_existing_promo_catalog_multisource.py" in rebuild
    assert "export_sku_candidate_review.py" in rebuild
    assert "tanpa mengambil data live" in rebuild
    assert "promo_multisource_collector.py" not in rebuild

# --- from test_launcher_workflows.py ---
def test_launcher_exports_sku_review_after_every_catalog_rebuild():
    run_bat = Path(__file__).resolve().parents[1] / "run.bat"
    text = run_bat.read_text(encoding="utf-8")
    assert text.count("export_sku_candidate_review.py") >= 4
    assert "src\\import_sku_candidate_review.py" in text

# --- from test_runtime_health_upgrade.py ---
JAKARTA = ZoneInfo("Asia/Jakarta")

# --- from test_runtime_health_upgrade.py ---
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

# --- from test_runtime_health_upgrade.py ---
def test_dev_check_also_requires_pytest(monkeypatch):
    imports = []

    def fake_import(name):
        imports.append(name)
        return object()

    monkeypatch.setattr(check_runtime.importlib, "import_module", fake_import)
    issues = check_runtime.check_runtime(dev=True)
    assert issues == []
    assert set(imports) == {"requests", "bs4", "openpyxl", "pytest"}

# --- from test_runtime_health_upgrade.py ---
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

# --- from test_runtime_health_upgrade.py ---
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

# --- from test_runtime_health_upgrade.py ---
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

# --- from test_runtime_health_upgrade.py ---
def test_health_summary_exposes_promo_history_metrics_and_partial_status():
    now = datetime(2026, 11, 3, 9, 0, tzinfo=JAKARTA)
    log = {
        "built_at": "2026-11-03T08:59:00+07:00",
        "reference_date": "2026-11-03",
        "promo_history": {"records_total": 120, "carried_forward_current_or_unverified": 12, "expired_records_retained_in_history": 45},
        "source_health": {
            "Hemat.id": {"status": "fresh_with_preserved", "product_rows_in_output": 20, "fresh_product_rows": 15, "preserved_previous_rows": 5},
            "Katalogpromosi.com": {"status": "preserved_previous", "product_rows_in_output": 4, "preserved_previous_rows": 4},
            "Scanharga.com": {"status": "fresh", "product_rows_in_output": 9, "fresh_product_rows": 9},
        },
    }
    result = build_summary(log, now=now)
    assert result["overall_status"] == "partial"
    assert result["promo_history"]["records_total"] == 120
    assert result["promo_history"]["expired_records_retained_in_history"] == 45
    assert result["sources"]["Hemat.id"]["health"] == "healthy_with_warnings"
    assert result["_exit_code"] == 0

# --- from test_runtime_health_upgrade.py ---
def test_launcher_import_price_mode_reuses_runtime_interpreter_without_pytest():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    batch = (root / "run.bat").read_text(encoding="utf-8")
    assert '"--import-price-research" set "MODE=import"' in batch
    assert 'if /I "%MODE%"=="import" set "CHECK_ARGS="' in batch
    assert 'if /I "%MODE%"=="import" goto :import_price_research' in batch
    assert 'src\\import_manual_price_references.py' in batch
    assert 'src\\enrich_existing_promo_catalog_multisource.py' in batch
    assert 'src\\verify_outputs.py' in batch
    assert 'if /I not "%MODE%"=="import" echo Mode ini juga memerlukan pytest' in batch

# --- from test_runtime_health_upgrade.py ---
def test_health_summary_preserves_source_role_explanation_and_yield_metrics():
    now = datetime(2026, 11, 4, 9, 0, tzinfo=JAKARTA)
    log = {
        "built_at": "2026-11-04T08:59:00+07:00",
        "source_health": {
            "Hemat.id": {"status": "fresh", "product_rows_in_output": 5, "fresh_product_rows": 5},
            "Katalogpromosi.com": {"status": "fresh", "product_rows_in_output": 4, "fresh_product_rows": 4},
            "Scanharga.com": {
                "status": "fresh_with_preserved", "product_rows_in_output": 20,
                "fresh_product_rows": 2, "preserved_previous_rows": 18,
                "source_role": "discovery_support",
                "source_role_note": "Utamakan artikel dan URL gambar.",
                "discovered_article_pages": 30,
                "articles_with_textual_product_rows": 2,
                "textual_product_rows_from_articles": 2,
                "image_references_found": 179,
                "fresh_product_rows_per_article": 0.067,
            },
        },
    }
    result = build_summary(log, now=now)
    source = result["sources"]["Scanharga.com"]
    assert source["source_role"] == "discovery_support"
    assert source["source_role_note"] == "Utamakan artikel dan URL gambar."
    assert source["discovered_article_pages"] == 30
    assert source["articles_with_textual_product_rows"] == 2
    assert source["image_references_found"] == 179
    assert source["fresh_product_rows_per_article"] == 0.067

# --- from test_verify_outputs.py ---
def _write_valid_outputs(root: Path) -> None:
    (root / "output").mkdir(parents=True)
    (root / "runtime").mkdir(parents=True)

    workbook = Workbook()
    workbook.active.title = "Katalog"
    workbook.save(root / "output" / "Katalog_Promo_Final.xlsx")

    with (root / "output" / "Riwayat_Promo.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["history_id", "product_text"])
        writer.writerow(["history-1", "Contoh Produk"])

    with (root / "output" / "Katalog_Promo_Final.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["Nama Produk", "Harga Promo (Rp)"])
        writer.writerow(["Contoh Produk", 10000])

    with (root / "runtime" / "promo_multisource_catalog_images.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["image_url", "source_url"])
        writer.writerow(["https://example.invalid/poster.jpg", "https://example.invalid/promo"])

    (root / "runtime" / "source_health_summary.json").write_text(
        json.dumps({"overall_status": "healthy", "sources": {}}), encoding="utf-8"
    )

# --- from test_verify_outputs.py ---
def test_verify_outputs_succeeds_in_project_path_with_spaces(tmp_path):
    project_root = tmp_path / "Merchant Promo Scraper"
    _write_valid_outputs(project_root)

    report = verify_outputs(project_root)

    assert report["ok"] is True
    assert report["errors"] == []
    assert report["sheets"] == ["Katalog"]
    assert set(report["files"]) == {"workbook", "catalog_csv", "promo_history", "image_index", "source_health"}
    assert all(item["ok"] for item in report["files"].values())

# --- from test_verify_outputs.py ---
def test_verify_outputs_reports_missing_artifact(tmp_path):
    project_root = tmp_path / "project"
    _write_valid_outputs(project_root)
    (project_root / "output" / "Katalog_Promo_Final.csv").unlink()

    report = verify_outputs(project_root)

    assert report["ok"] is False
    assert any("catalog_csv tidak ditemukan" in error for error in report["errors"])

# --- from test_verify_outputs.py ---
def test_verify_outputs_reports_corrupt_workbook(tmp_path):
    project_root = tmp_path / "project"
    _write_valid_outputs(project_root)
    (project_root / "output" / "Katalog_Promo_Final.xlsx").write_bytes(b"not an xlsx")

    report = verify_outputs(project_root)

    assert report["ok"] is False
    assert any("Workbook tidak dapat dibuka" in error for error in report["errors"])

# --- from test_verify_outputs.py ---
def test_run_bat_uses_verifier_script_not_embedded_project_path():
    run_bat = Path(__file__).resolve().parents[1] / "run.bat"
    source = run_bat.read_text(encoding="utf-8")

    assert '"%~dp0src\\verify_outputs.py"' in source
    assert "Path(r'%~dp0')" not in source
