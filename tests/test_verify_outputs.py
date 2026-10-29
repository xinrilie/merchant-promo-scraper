from __future__ import annotations

import csv
import json
from pathlib import Path

from openpyxl import Workbook

from verify_outputs import verify_outputs


def _write_valid_outputs(root: Path) -> None:
    (root / "output").mkdir(parents=True)
    (root / "runtime").mkdir(parents=True)

    workbook = Workbook()
    workbook.active.title = "Katalog"
    workbook.save(root / "output" / "Katalog_Promo_Final.xlsx")

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


def test_verify_outputs_succeeds_in_project_path_with_spaces(tmp_path):
    project_root = tmp_path / "Merchant Promo Scraper"
    _write_valid_outputs(project_root)

    report = verify_outputs(project_root)

    assert report["ok"] is True
    assert report["errors"] == []
    assert report["sheets"] == ["Katalog"]
    assert set(report["files"]) == {"workbook", "catalog_csv", "image_index", "source_health"}
    assert all(item["ok"] for item in report["files"].values())


def test_verify_outputs_reports_missing_artifact(tmp_path):
    project_root = tmp_path / "project"
    _write_valid_outputs(project_root)
    (project_root / "output" / "Katalog_Promo_Final.csv").unlink()

    report = verify_outputs(project_root)

    assert report["ok"] is False
    assert any("catalog_csv tidak ditemukan" in error for error in report["errors"])


def test_verify_outputs_reports_corrupt_workbook(tmp_path):
    project_root = tmp_path / "project"
    _write_valid_outputs(project_root)
    (project_root / "output" / "Katalog_Promo_Final.xlsx").write_bytes(b"not an xlsx")

    report = verify_outputs(project_root)

    assert report["ok"] is False
    assert any("Workbook tidak dapat dibuka" in error for error in report["errors"])


def test_run_bat_uses_verifier_script_not_embedded_project_path():
    run_bat = Path(__file__).resolve().parents[1] / "run.bat"
    source = run_bat.read_text(encoding="utf-8")

    assert '"%~dp0src\\verify_outputs.py"' in source
    assert "Path(r'%~dp0')" not in source
