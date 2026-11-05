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
USABLE_STATUSES = {"fresh", "fresh_with_preserved", "preserved_previous", "reachable_no_products"}
WARNING_STATUSES = {"fresh_with_preserved", "request_failed", "blocked_or_limited", "no_request", "unknown"}


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

        if status == "fresh_with_preserved":
            health = "healthy_with_warnings"
            partial_sources += 1
            warnings.append(
                f"{name}: ada data baru dan {preserved_rows} baris lama yang dipertahankan; "
                "periksa kolom kesegaran sebelum menganggap seluruh data terbaru."
            )
            fresh_sources += 1
        elif status == "fresh":
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

        if name == "Scanharga.com":
            source_role = str(raw.get("source_role") or "discovery_support")
            article_pages = _as_int(raw.get("discovered_article_pages"))
            fresh_product_yield = raw.get("fresh_product_rows_per_article")
            image_refs = _as_int(raw.get("image_references_found"))
            if article_pages >= 10 and fresh_rows <= 5 and image_refs > 0:
                warnings.append(
                    f"{name}: lebih efektif sebagai sumber discovery/gambar ({article_pages} artikel, "
                    f"{image_refs} URL gambar, hanya {fresh_rows} produk segar); jangan menganggapnya sumber utama harga produk."
                )
        else:
            source_role = str(raw.get("source_role") or "product_and_promo_source")
            article_pages = _as_int(raw.get("discovered_article_pages"))
            fresh_product_yield = raw.get("fresh_product_rows_per_article")
            image_refs = _as_int(raw.get("image_references_found"))

        usable_rows_total += rows
        sources[name] = {
            "status": status,
            "health": health,
            "source_role": source_role,
            "source_role_note": str(raw.get("source_role_note") or ""),
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
            "discovered_article_pages": article_pages,
            "articles_with_textual_product_rows": _as_int(raw.get("articles_with_textual_product_rows")),
            "textual_product_rows_from_articles": _as_int(raw.get("textual_product_rows_from_articles")),
            "image_references_found": image_refs,
            "fresh_product_rows_per_article": fresh_product_yield,
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
        "promo_history": log.get("promo_history") if isinstance(log.get("promo_history"), dict) else {},
        "freshness_metrics": {
            "raw_product_rows_scraped_before_dedupe": _as_int(log.get("raw_product_rows_scraped_before_dedupe")),
            "fresh_deduplicated_offer_records": _as_int(log.get("fresh_deduplicated_offer_records")),
            "fresh_distinct_offer_rows_in_snapshot": _as_int(log.get("fresh_distinct_offer_rows_in_snapshot")),
            "fresh_source_attributions_by_source": log.get("fresh_source_attributions_by_source") if isinstance(log.get("fresh_source_attributions_by_source"), dict) else {},
            "fresh_source_attribution_total": _as_int(log.get("fresh_source_attribution_total")),
            "fresh_cross_source_overlap_extra_attributions": _as_int(log.get("fresh_cross_source_overlap_extra_attributions")),
            "preserved_source_attributions_by_source": log.get("preserved_source_attributions_by_source") if isinstance(log.get("preserved_source_attributions_by_source"), dict) else {},
            "distinct_rows_preserved_only": _as_int(log.get("distinct_rows_preserved_only")),
            "carried_forward_rows": _as_int(log.get("carried_forward_rows")),
            "rows_before_final_snapshot_dedupe": _as_int(log.get("rows_before_final_snapshot_dedupe")),
            "product_rows_after_exact_dedup": _as_int(log.get("product_rows_after_exact_dedup")),
            "carry_forward_decisions": log.get("carry_forward_decisions") if isinstance(log.get("carry_forward_decisions"), dict) else {},
        },
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
            f" - {name}: {source['status']} | role={source['source_role']} "
            f"rows={source['product_rows_in_output']} fresh={source['fresh_product_rows']} "
            f"preserved={source['preserved_previous_rows']} "
            f"articles={source['discovered_article_pages']} "
            f"text_articles={source['articles_with_textual_product_rows']} "
            f"article_products={source['textual_product_rows_from_articles']} "
            f"images={source['image_references_found']} "
            f"fresh_per_article={source['fresh_product_rows_per_article']}"
        )
        if source.get("source_role_note"):
            print(f"   Peran sumber: {source['source_role_note']}")
    for warning in summary["warnings"]:
        print(f"PERINGATAN: {warning}")
    print(f"Laporan: {args.output}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
