"""Summarize the latest collector run's source health without network access."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "runtime" / "promo_multisource_runlog.json"
DEFAULT_OUTPUT = ROOT / "runtime" / "source_health_summary.json"
JAKARTA = ZoneInfo("Asia/Jakarta")
KNOWN_SOURCES = ("Hemat.id", "Katalogpromosi.com", "Scanharga.com")
USABLE_STATUSES = {"fresh", "preserved_previous", "reachable_no_products"}
WARNING_STATUSES = {"request_failed", "blocked_or_limited", "no_request", "unknown"}


def _parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=JAKARTA)
    return result.astimezone(JAKARTA)


def _as_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def build_summary(log: dict, *, now: datetime | None = None) -> dict:
    """Create a stable, machine-readable summary from a collector run log."""
    current = (now or datetime.now(JAKARTA)).astimezone(JAKARTA)
    built_at = _parse_datetime(log.get("built_at"))
    is_current_date = bool(built_at and built_at.date() == current.date())
    raw_health = log.get("source_health")
    if not isinstance(raw_health, dict) or not raw_health:
        raise ValueError("Run log tidak memuat objek source_health yang valid.")

    sources: dict[str, dict] = {}
    warnings: list[str] = []
    usable_rows_total = 0
    fresh_sources = 0
    healthy_sources = 0
    partial_sources = 0
    for name in KNOWN_SOURCES:
        raw = raw_health.get(name)
        if not isinstance(raw, dict):
            raw = {"status": "no_request", "product_rows_in_output": 0}
        status = str(raw.get("status") or "unknown").casefold()
        rows = _as_int(raw.get("product_rows_in_output"))
        fresh_rows = _as_int(raw.get("fresh_product_rows"))
        preserved_rows = _as_int(raw.get("preserved_previous_rows"))
        failed_requests = _as_int(raw.get("failed_requests"))
        blocked_requests = _as_int(raw.get("blocked_or_limited_requests"))

        if status == "fresh":
            if failed_requests or blocked_requests:
                health = "healthy_with_warnings"
                partial_sources += 1
                warnings.append(
                    f"{name}: ada request gagal/dibatasi ({failed_requests} gagal, {blocked_requests} dibatasi), "
                    "meskipun sebagian data baru berhasil diambil."
                )
            else:
                health = "healthy"
                healthy_sources += 1
            fresh_sources += 1
        elif status == "preserved_previous":
            health = "using_previous_data"
            partial_sources += 1
            warnings.append(f"{name}: menggunakan {preserved_rows or rows} baris dari run sebelumnya.")
        elif status == "reachable_no_products":
            health = "reachable_no_products"
            partial_sources += 1
            warnings.append(f"{name}: halaman dapat diakses tetapi tidak menghasilkan baris produk baru.")
        elif status in WARNING_STATUSES:
            health = "warning"
            partial_sources += 1
            warnings.append(f"{name}: status sumber {status}.")
        else:
            health = "warning"
            partial_sources += 1
            warnings.append(f"{name}: status tidak dikenali ({status}).")

        usable_rows_total += rows
        sources[name] = {
            "status": status,
            "health": health,
            "request_count": _as_int(raw.get("request_count")),
            "successful_requests": _as_int(raw.get("successful_requests")),
            "failed_requests": failed_requests,
            "not_found_requests": _as_int(raw.get("not_found_requests")),
            "gone_requests": _as_int(raw.get("gone_requests")),
            "other_client_error_requests": _as_int(raw.get("other_client_error_requests")),
            "blocked_or_limited_requests": blocked_requests,
            "product_rows_in_output": rows,
            "fresh_product_rows": fresh_rows,
            "preserved_previous_rows": preserved_rows,
            "rows_with_promo_price": int(raw.get("rows_with_promo_price") or 0),
            "rows_with_normal_price": _as_int(raw.get("rows_with_normal_price")),
            "rows_with_discount": _as_int(raw.get("rows_with_discount")),
            "promo_price_evidence_coverage": raw.get("promo_price_evidence_coverage"),
            "discount_evidence_coverage": raw.get("discount_evidence_coverage"),
            "period_evidence_coverage": raw.get("period_evidence_coverage"),
        }

    if not is_current_date:
        warnings.append("Run log bukan dari tanggal lokal hari ini; pastikan collector baru saja dijalankan.")

    if usable_rows_total <= 0:
        overall = "no_data"
        status_code = 2
        warnings.append("Tidak ada baris produk segar maupun data sebelumnya pada sumber mana pun.")
    elif partial_sources:
        overall = "partial"
        status_code = 0
    else:
        overall = "healthy"
        status_code = 0

    summary = {
        "built_at": current.isoformat(timespec="seconds"),
        "collector_built_at": built_at.isoformat(timespec="seconds") if built_at else None,
        "collector_reference_date": str(log.get("reference_date") or "") or None,
        "collector_log_is_current_date": is_current_date,
        "overall_status": overall,
        "source_count": len(sources),
        "healthy_sources": healthy_sources,
        "fresh_sources": fresh_sources,
        "partial_or_warning_sources": partial_sources,
        "product_rows_in_source_outputs": usable_rows_total,
        "image_references_found": int(log.get("image_references_found") or 0),
        "ocr_used": False,
        "images_downloaded_for_text_extraction": False,
        "sources": sources,
        "warnings": warnings,
    }
    summary["_exit_code"] = status_code
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path run log collector")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path report JSON")
    args = parser.parse_args()

    try:
        log = json.loads(args.input.read_text(encoding="utf-8-sig"))
        if not isinstance(log, dict):
            raise ValueError("Run log harus berupa objek JSON.")
        summary = build_summary(log)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR health-check: {exc}", file=sys.stderr)
        return 1

    exit_code = summary.pop("_exit_code")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(args.output.suffix + ".tmp")
    temp.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(args.output)

    print(f"Source health: {summary['overall_status']} | produk di output sumber: {summary['product_rows_in_source_outputs']}")
    for name, source in summary["sources"].items():
        print(
            f" - {name}: {source['status']} | rows={source['product_rows_in_output']} "
            f"fresh={source['fresh_product_rows']} preserved={source['preserved_previous_rows']}"
        )
    for warning in summary["warnings"]:
        print(f"PERINGATAN: {warning}")
    print(f"Laporan: {args.output}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
