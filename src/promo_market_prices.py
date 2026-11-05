"""Evidence-validated market price references and comparison helpers.

This module contains only deterministic market-reference functionality. It does
not call any AI API and never creates estimated prices without a source.
"""
from __future__ import annotations

import csv
import hashlib
import re
import statistics
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from promo_names import (
    clean_product_name, product_name_size_signature, product_name_variant_signature,
    product_name_matching_key, product_name_package_match_signature,
)
from promo_price_reference import identity_key

ROOT_DIR = Path(__file__).resolve().parent.parent
# Manually checked and dynamic market-price observations belong in ignored local state.
# The tracked data/ CSV remains a seed that can be migrated on first use.
MARKET_REFERENCE_CSV = ROOT_DIR / "state" / "product_market_price_reference.csv"
MARKET_REFERENCE_SEED_CSV = ROOT_DIR / "data" / "product_market_price_reference.csv"
DEFAULT_MAX_AGE_DAYS = 14
DEFAULT_NORMAL_ESTIMATE_MAX_AGE_DAYS = 30
MARKET_REFERENCE_FIELDS = [
    "product_text", "product_key", "size_signature", "variant_signature",
    "market_price", "observed_at", "source_name", "source_domain", "source_url",
    "evidence_text", "page_title", "price_kind", "source_kind", "verification_method",
    "confidence", "reference_key", "retailer_name", "source_checked_at",
    "price_classification", "product_match_status",
]


def parse_idr_price(value: object) -> int | None:
    """Parse Indonesian Rupiah strings such as ``Rp 22.900``."""
    if value in (None, "") or isinstance(value, bool):
        return None
    text = str(value).strip()
    text = re.sub(r"(?i)\b(?:rp|idr)\b", "", text)
    text = text.replace(" ", "")
    text = re.sub(r"[^0-9.,+\-]", "", text)
    if not text or not re.search(r"\d", text):
        return None
    if "." in text and "," in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "." in text or "," in text:
        separator = "." if "." in text else ","
        parts = text.split(separator)
        if len(parts) > 1 and len(parts[-1]) in (1, 2):
            text = "".join(parts[:-1]) + "." + parts[-1]
        else:
            text = "".join(parts)
    try:
        result = int(round(float(text)))
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result > 0 else None


def _parse_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except (TypeError, ValueError, OverflowError):
        try:
            return date.fromisoformat(text[:10])
        except (TypeError, ValueError):
            return None


def _normalize_record(record: dict) -> dict:
    row = {field: str(record.get(field) or "").strip() for field in MARKET_REFERENCE_FIELDS}
    row["product_key"] = row["product_key"] or identity_key(row["product_text"])
    row["size_signature"] = row["size_signature"] or "|".join(product_name_size_signature(row["product_text"]))
    row["variant_signature"] = row["variant_signature"] or "|".join(sorted(product_name_variant_signature(row["product_text"])))
    row["source_domain"] = row["source_domain"] or (urlparse(row["source_url"]).hostname or "").lower()
    if not row["reference_key"]:
        material = "|".join((row["product_key"], row["source_url"], row["observed_at"], row["market_price"]))
        row["reference_key"] = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    return row


def _ensure_csv(path: Path, fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            csv.DictWriter(handle, fieldnames=fields).writeheader()


def initialize_market_reference_database(
    path: str | Path = MARKET_REFERENCE_CSV,
    seed_path: str | Path = MARKET_REFERENCE_SEED_CSV,
) -> str:
    """Create local market-reference state, migrating the tracked seed once."""
    path = Path(path)
    seed = Path(seed_path)
    if path.exists():
        return "existing"
    if seed.exists():
        try:
            with seed.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            if rows:
                upsert_market_reference_database(path, rows)
                return "migrated_seed"
        except (OSError, csv.Error):
            pass
    _ensure_csv(path, MARKET_REFERENCE_FIELDS)
    return "created_empty"


def load_market_reference_database(path: str | Path = MARKET_REFERENCE_CSV) -> list[dict]:
    """Load only market prices with a URL, evidence, timestamp and verified-page marker."""
    path = Path(path)
    _ensure_csv(path, MARKET_REFERENCE_FIELDS)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            raw_rows = list(csv.DictReader(handle))
    except (OSError, csv.Error):
        return []
    rows = []
    for raw in raw_rows:
        row = _normalize_record(dict(raw))
        price = parse_idr_price(row.get("market_price"))
        observed = _parse_date(row.get("observed_at"))
        parsed = urlparse(row.get("source_url", ""))
        is_tokku = (parsed.hostname or "").lower().removeprefix("www.") == "tokku.app"
        if (
            not row.get("product_key") or not row.get("product_text")
            or price is None or price < 100 or price > 100_000_000
            or not observed or not row.get("evidence_text")
            or parsed.scheme not in {"http", "https"} or not parsed.hostname
            or not row.get("source_domain")
            or row.get("verification_method") != "page_price_verified"
            or (is_tokku and (
                not row.get("retailer_name")
                or row.get("product_match_status", "").casefold() != "exact"
                or not _parse_date(row.get("source_checked_at"))
            ))
        ):
            continue
        row["market_price"] = str(price)
        row["source_domain"] = parsed.hostname.lower().removeprefix("www.")
        rows.append(row)
    return rows


def upsert_market_reference_database(path: str | Path, rows: list[dict]) -> dict:
    """Insert independently verified records, deduplicating by product page URL."""
    path = Path(path)
    existing = load_market_reference_database(path)
    # A collection/category page can list many different SKUs, so URL alone is
    # not a unique key. Keep a separate reference for each product on that page.
    by_url = {
        (
            row.get("product_key", ""), row.get("source_url", ""),
            row.get("price_kind", "market"), row.get("retailer_name", "").casefold(),
        ): row
        for row in existing if row.get("source_url")
    }
    added = updated = 0
    for raw in rows:
        row = _normalize_record(raw)
        price = parse_idr_price(row.get("market_price"))
        parsed = urlparse(row.get("source_url", ""))
        if (
            not row.get("product_key") or price is None or not parsed.hostname
            or parsed.scheme not in {"http", "https"} or not row.get("evidence_text")
            or row.get("verification_method") != "page_price_verified"
        ):
            continue
        row["market_price"] = str(price)
        row["source_domain"] = parsed.hostname.lower().removeprefix("www.")
        key = (
            row.get("product_key", ""), row["source_url"],
            row.get("price_kind", "market"), row.get("retailer_name", "").casefold(),
        )
        old = by_url.get(key)
        if old is None:
            added += 1
        elif any(old.get(k) != row.get(k) for k in (
            "market_price", "observed_at", "source_checked_at", "evidence_text",
            "product_key", "retailer_name", "price_classification",
        )):
            updated += 1
        by_url[key] = row
    ordered = sorted(by_url.values(), key=lambda r: (r.get("product_key", ""), r.get("source_domain", ""), r.get("observed_at", "")))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MARKET_REFERENCE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(ordered)
    temp.replace(path)
    return {"records_before": len(existing), "records_added": added, "records_updated": updated, "records_after": len(ordered), "database_path": str(path)}


def estimate_normal_prices_from_references(
    rows: list[dict],
    references: list[dict],
    today: date | None = None,
    max_age_days: int = DEFAULT_NORMAL_ESTIMATE_MAX_AGE_DAYS,
    aliases: dict[str, str] | None = None,
) -> dict:
    """Attach a clearly labelled normal-market estimate from exact manual evidence.

    Only exact product/size/variant matches classified as an explicit normal price,
    a regular non-promo price, or a 3-month historical average are considered.
    Promo prices, unknown classifications, and stale source-side observations are
    deliberately excluded. Results never overwrite the source's original price.
    """
    today = today or date.today()
    by_product: dict[str, list[dict]] = {}
    accepted_kinds = {"normal", "regular", "historical_average"}
    for raw in references:
        item = _normalize_record(raw)
        kind = str(item.get("price_kind") or "market").casefold()
        if kind not in accepted_kinds:
            continue
        checked = _parse_date(item.get("source_checked_at")) or _parse_date(item.get("observed_at"))
        manual_seen = _parse_date(item.get("observed_at"))
        price = parse_idr_price(item.get("market_price"))
        if (
            not checked or checked > today or (today - checked).days > max_age_days
            or not manual_seen or manual_seen > today or price is None
        ):
            continue
        if str(item.get("source_domain") or "").casefold().removeprefix("www.") == "tokku.app":
            if str(item.get("product_match_status") or "").casefold() != "exact":
                continue
            if not str(item.get("retailer_name") or "").strip():
                continue
        item["_estimate_checked_date"] = checked
        item["_estimate_age_days"] = (today - checked).days
        match_key = product_name_matching_key(item.get("product_text"), aliases)
        if match_key:
            by_product.setdefault(match_key, []).append(item)

    summary = {
        "rows_checked": 0, "rows_estimated": 0, "tokku_estimates": 0,
        "historical_average_estimates": 0, "stale_or_unmatched": 0,
        "max_age_days": max_age_days,
    }
    for row in rows:
        for field in (
            "estimated_normal_price", "estimated_normal_low", "estimated_normal_high",
            "estimated_normal_basis", "estimated_normal_sources", "estimated_normal_retailers",
            "estimated_normal_source_urls", "estimated_normal_observed_at", "estimated_normal_age_days",
            "estimated_normal_observation_count", "estimated_normal_confidence",
            "estimated_normal_status", "estimated_normal_note",
        ):
            row.setdefault(field, None)

        # Keep exact/source-derived prices authoritative. This field is a separate
        # estimate and is only used where the promotion has no usable normal price.
        if parse_idr_price(row.get("normal_price")) is not None or parse_idr_price(row.get("reference_normal_price")) is not None:
            continue
        if row.get("product_validation_status") != "eligible":
            continue
        product = clean_product_name(row.get("product_text"))
        pkey = product_name_matching_key(product, aliases)
        if not pkey:
            continue
        summary["rows_checked"] += 1
        qpackage = product_name_package_match_signature(product)
        qvariant = "|".join(sorted(product_name_variant_signature(product)))
        candidates = [
            item for item in by_product.get(pkey, [])
            if product_name_package_match_signature(item.get("product_text")) == qpackage
            and item.get("variant_signature", "") == qvariant
        ]
        if not candidates:
            if any(product_name_matching_key(item.get("product_text"), aliases) == pkey for item in references):
                summary["stale_or_unmatched"] += 1
            continue

        # Explicit regular/current observations take precedence over the 3-month
        # historical average. A historical average is a lower-confidence fallback.
        regular = [item for item in candidates if item.get("price_kind") in {"normal", "regular"}]
        selected = regular or [item for item in candidates if item.get("price_kind") == "historical_average"]
        if not selected:
            continue

        # One latest observation per retailer. When a page has no retailer field,
        # use its source domain as a conservative grouping key.
        latest_by_outlet: dict[str, dict] = {}
        for item in sorted(selected, key=lambda value: (
            value.get("_estimate_checked_date"), value.get("observed_at", "")
        )):
            outlet = str(item.get("retailer_name") or item.get("source_domain") or item.get("source_name") or "unknown").casefold()
            latest_by_outlet[outlet] = item
        chosen = list(latest_by_outlet.values())
        prices = [parse_idr_price(item.get("market_price")) for item in chosen]
        prices = [value for value in prices if value is not None]
        if not prices:
            continue

        estimate = int(round(statistics.median(prices)))
        source_domains = sorted({str(item.get("source_domain") or item.get("source_name") or "") for item in chosen if item.get("source_domain") or item.get("source_name")})
        retailers = sorted({str(item.get("retailer_name") or "").strip() for item in chosen if str(item.get("retailer_name") or "").strip()})
        latest_checked = max(item["_estimate_checked_date"] for item in chosen)
        worst_age = max(item["_estimate_age_days"] for item in chosen)
        used_historical_average = not regular
        is_tokku = any(str(item.get("source_domain") or "").casefold().removeprefix("www.") == "tokku.app" for item in chosen)

        row["estimated_normal_price"] = estimate
        row["estimated_normal_low"] = min(prices)
        row["estimated_normal_high"] = max(prices)
        row["estimated_normal_basis"] = "historical_average_3m" if used_historical_average else "median_regular_retailer_prices"
        row["estimated_normal_sources"] = " | ".join(source_domains)
        row["estimated_normal_retailers"] = " | ".join(retailers) or None
        row["estimated_normal_source_urls"] = " | ".join(sorted({item.get("source_url", "") for item in chosen if item.get("source_url")}))
        row["estimated_normal_observed_at"] = latest_checked.isoformat()
        row["estimated_normal_age_days"] = worst_age
        row["estimated_normal_observation_count"] = len(prices)
        # Tokku's own terms warn that automated product matching may be imperfect.
        # Never label an estimate from a single aggregator as high confidence.
        if used_historical_average:
            confidence = "low"
        elif len(prices) >= 3:
            confidence = "medium"
        else:
            confidence = "low"
        row["estimated_normal_confidence"] = confidence
        row["estimated_normal_status"] = "estimated_from_manual_price_evidence"
        if used_historical_average:
            row["estimated_normal_note"] = "Rata-rata historis 3 bulan; dapat mencakup harga promo, bukan harga normal resmi. Tidak dipakai menghitung diskon resmi."
            summary["historical_average_estimates"] += 1
        elif is_tokku:
            row["estimated_normal_note"] = "Median harga retailer yang ditandai normal/reguler dan dicocokkan manual sebagai SKU exact di Tokku. Bukan harga asli resmi merchant promo."
            summary["tokku_estimates"] += 1
        else:
            row["estimated_normal_note"] = "Median observasi harga retailer yang ditandai normal/reguler. Bukan harga asli resmi merchant promo."
        summary["rows_estimated"] += 1
    return summary


def compare_market_prices(
    rows: list[dict], references: list[dict], today: date | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS, aliases: dict[str, str] | None = None,
) -> dict:
    """Attach market median only when same exact product/size/variant evidence matches."""
    today = today or date.today()
    by_product: dict[str, list[dict]] = {}
    for raw in references:
        row = _normalize_record(raw)
        # Tokku and other comparison pages expose a source-side "last checked"
        # date. Prefer that over the user's manual capture date; a page opened
        # today can still contain a price last checked months ago.
        observed = _parse_date(row.get("source_checked_at")) or _parse_date(row.get("observed_at"))
        price = parse_idr_price(row.get("market_price"))
        kind = str(row.get("price_kind") or "market").casefold()
        if kind in {"promo", "unknown", "historical_min", "historical_average"}:
            continue
        if not observed or observed > today or (today - observed).days > max_age_days or price is None:
            continue
        match_key = product_name_matching_key(row.get("product_text"), aliases)
        if match_key:
            by_product.setdefault(match_key, []).append(row)

    summary = {"rows_checked": 0, "rows_with_market_reference": 0, "single_source_only": 0, "below_market_median": 0, "not_below_market_median": 0, "no_market_reference": 0, "stale_or_unmatched": 0, "max_age_days": max_age_days}
    for row in rows:
        for key in (
            "market_reference_price", "market_reference_low", "market_reference_high",
            "market_reference_source_count", "market_reference_sources", "market_reference_source_urls",
            "market_reference_observed_at", "market_reference_status", "market_reference_below_median_percent",
            "market_reference_savings", "market_reference_confidence", "market_reference_note",
        ):
            row.setdefault(key, None)
        promo = parse_idr_price(row.get("promo_price"))
        product = clean_product_name(row.get("product_text"))
        pkey = product_name_matching_key(product, aliases)
        if not pkey or promo is None or row.get("product_validation_status") != "eligible":
            row["market_reference_status"] = "not_comparable"
            continue
        summary["rows_checked"] += 1
        qpackage = product_name_package_match_signature(product)
        qvariant = "|".join(sorted(product_name_variant_signature(product)))
        candidates = [
            item for item in by_product.get(pkey, [])
            if product_name_package_match_signature(item.get("product_text")) == qpackage
            and item.get("variant_signature", "") == qvariant
        ]
        latest_by_domain: dict[str, dict] = {}
        for item in sorted(candidates, key=lambda r: (r.get("observed_at", ""), r.get("source_url", ""))):
            domain = str(item.get("source_domain") or "").lower().removeprefix("www.")
            if domain:
                latest_by_domain[domain] = item
        refs = list(latest_by_domain.values())
        if not refs:
            row["market_reference_status"] = "no_market_reference"
            summary["no_market_reference"] += 1
            if any(product_name_matching_key(item.get("product_text"), aliases) == pkey for item in references):
                summary["stale_or_unmatched"] += 1
            continue
        prices = [parse_idr_price(item.get("market_price")) for item in refs]
        prices = [price for price in prices if price is not None]
        if not prices:
            row["market_reference_status"] = "invalid_market_reference"
            continue
        median_price = int(round(statistics.median(prices)))
        row["market_reference_price"] = median_price
        row["market_reference_low"] = min(prices)
        row["market_reference_high"] = max(prices)
        row["market_reference_source_count"] = len(refs)
        row["market_reference_sources"] = " | ".join(
            f"{item.get('source_domain')} (Rp{parse_idr_price(item.get('market_price')):,}; {item.get('price_kind') or 'unknown'})".replace(",", ".")
            for item in sorted(refs, key=lambda r: r.get("source_domain", ""))
        )
        row["market_reference_source_urls"] = " | ".join(item.get("source_url", "") for item in sorted(refs, key=lambda r: r.get("source_domain", "")))
        row["market_reference_observed_at"] = max(item.get("observed_at", "") for item in refs)
        row["market_reference_note"] = "Pembanding pasar dari halaman publik yang harganya cocok diverifikasi; bukan harga normal resmi merchant promo. Harga promo/regular pada sumber pembanding dapat berbeda."
        summary["rows_with_market_reference"] += 1
        if len(refs) < 2:
            row["market_reference_status"] = "single_source_only"
            row["market_reference_confidence"] = "insufficient"
            summary["single_source_only"] += 1
            continue
        row["market_reference_confidence"] = "medium" if len(refs) >= 3 else "low"
        if median_price > promo:
            row["market_reference_below_median_percent"] = round((median_price - promo) / median_price * 100, 1)
            row["market_reference_savings"] = median_price - promo
            row["market_reference_status"] = "below_market_median"
            summary["below_market_median"] += 1
        else:
            row["market_reference_status"] = "not_below_market_median"
            summary["not_below_market_median"] += 1
    return summary
