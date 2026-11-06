from pathlib import Path


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


def test_launcher_exports_sku_review_after_every_catalog_rebuild():
    run_bat = Path(__file__).resolve().parents[1] / "run.bat"
    text = run_bat.read_text(encoding="utf-8")
    assert text.count("export_sku_candidate_review.py") >= 4
    assert "src\\import_sku_candidate_review.py" in text
