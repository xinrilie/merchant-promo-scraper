from __future__ import annotations

"""Persistent promo-history storage and safe carry-forward rules.

The collector's current snapshot is intentionally small/current-facing. This
module stores every distinct observed offer in state/promo_history.csv, updates
last-seen metadata without duplicating repeated runs, and exposes only
non-expired/recently-unverified offers for carry-forward into the next snapshot.
No network access or image/OCR processing is performed here.
"""

import csv
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from promo_campaign_utils import promo_status

JAKARTA = ZoneInfo("Asia/Jakarta")
HISTORY_FIELDS = (
    "history_id",
    "first_seen_at",
    "last_seen_at",
    "last_seen_run_id",
    "seen_count",
    "presence_status",
    "history_promo_status",
    "history_status_as_of",
    "history_record_status",
    "days_since_last_seen",
    "history_source_names",
    "history_source_urls",
    "superseded_by_history_id",
    "retention_reason",
)
DEFAULT_UNKNOWN_PERIOD_GRACE_DAYS = 14


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: object) -> str:
    text = _text(value).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _parse_iso_date(value: object) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parse_timestamp(value: object) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JAKARTA)
    return parsed.astimezone(JAKARTA)


def _iso_now(now: datetime | None = None) -> str:
    value = now or datetime.now(JAKARTA)
    if value.tzinfo is None:
        value = value.replace(tzinfo=JAKARTA)
    return value.astimezone(JAKARTA).isoformat(timespec="seconds")


def _truthy(value: object) -> bool:
    return _text(value).casefold() in {"1", "true", "yes", "y", "ya"}


def _split_pipe(value: object) -> list[str]:
    return list(dict.fromkeys(part.strip() for part in str(value or "").split(" | ") if part.strip()))


def source_names_for(row: dict) -> list[str]:
    return list(dict.fromkeys(_split_pipe(row.get("source_names")) + _split_pipe(row.get("source_name"))))


def source_urls_for(row: dict) -> list[str]:
    return list(dict.fromkeys(_split_pipe(row.get("source_urls")) + _split_pipe(row.get("source_url"))))


def promo_event_key(row: dict) -> str:
    """Stable ID for a product offer version; price/date changes form a new event."""
    valid_from = _text(row.get("valid_from"))
    valid_until = _text(row.get("valid_until"))
    identity = {
        "merchant": _norm(row.get("merchant_name")),
        "product": _norm(row.get("product_text") or row.get("original_product_text")),
        "valid_from": valid_from,
        "valid_until": valid_until,
        "promo_price": _text(row.get("promo_price")),
        "normal_price": _text(row.get("normal_price")),
        "condition": _norm(row.get("purchase_condition")),
        "deal_type": _norm(row.get("deal_type")),
    }
    # Campaign titles and line wording are editorial and often vary by
    # aggregator. With a complete date range, product+merchant+period+price
    # is a more stable observation key. For undated offers retain context.
    if not (valid_from and valid_until):
        identity["campaign"] = _norm(row.get("campaign_title"))
        identity["offer"] = _norm(row.get("offer_text"))
    if not identity["product"]:
        identity["source"] = "|".join(_norm(v) for v in source_names_for(row))
        identity["source_url"] = _norm(row.get("source_url"))
        identity["raw_line"] = _norm(row.get("raw_line"))
    payload = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def promo_family_key(row: dict) -> str:
    """Identity ignoring price/offer text, used to detect a refreshed version."""
    valid_from = _text(row.get("valid_from"))
    valid_until = _text(row.get("valid_until"))
    identity = {
        "merchant": _norm(row.get("merchant_name")),
        "product": _norm(row.get("product_text") or row.get("original_product_text")),
        "valid_from": valid_from,
        "valid_until": valid_until,
        "condition": _norm(row.get("purchase_condition")),
        "deal_type": _norm(row.get("deal_type")),
    }
    # With an explicit period, product+merchant+period is a better family key
    # than the editorial campaign title, which aggregators often rewrite.
    # Without a period, retain campaign context to avoid over-merging.
    if not (valid_from and valid_until):
        identity["campaign"] = _norm(row.get("campaign_title"))
    if not identity["product"]:
        identity["source_url"] = _norm(row.get("source_url"))
        identity["raw_line"] = _norm(row.get("raw_line"))
    payload = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def current_promo_status(row: dict, today: date) -> str:
    """Recalculate temporal status; a known past end date always means expired."""
    start = _parse_iso_date(row.get("valid_from"))
    end = _parse_iso_date(row.get("valid_until"))
    if end and end < today:
        return "expired"
    return promo_status(
        start.isoformat() if start else None,
        end.isoformat() if end else None,
        _text(row.get("period_precision")) or "unknown",
        today=today,
    )


def load_history(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def seed_history_from_snapshot(
    snapshot_rows: Iterable[dict], *, now: datetime | None = None, today: date | None = None
) -> list[dict]:
    """One-time migration from the previous runtime snapshot to persistent history."""
    current_date = today or (now or datetime.now(JAKARTA)).astimezone(JAKARTA).date()
    rows_by_id: dict[str, dict] = {}
    for raw in snapshot_rows:
        row = dict(raw)
        history_id = _text(row.get("history_id")) or promo_event_key(row)
        scraped_at = _text(row.get("scraped_at")) or _iso_now(now)
        first_seen_at = _text(row.get("first_seen_at")) or scraped_at
        last_seen_at = _text(row.get("last_seen_at")) or scraped_at
        prior = rows_by_id.get(history_id)
        if prior:
            prior["history_source_names"] = " | ".join(dict.fromkeys(
                _split_pipe(prior.get("history_source_names")) + source_names_for(row)
            ))
            prior["history_source_urls"] = " | ".join(dict.fromkeys(
                _split_pipe(prior.get("history_source_urls")) + source_urls_for(row)
            ))
            continue
        item = dict(row)
        item.update({
            "history_id": history_id,
            "first_seen_at": first_seen_at,
            "last_seen_at": last_seen_at,
            "last_seen_run_id": _text(row.get("last_seen_run_id")) or "imported_from_previous_snapshot",
            "seen_count": max(1, int(row.get("seen_count") or 1)) if str(row.get("seen_count") or "").isdigit() else 1,
            "presence_status": _text(row.get("presence_status")) or "imported_from_previous_snapshot",
            "history_promo_status": current_promo_status(row, current_date),
            "history_status_as_of": current_date.isoformat(),
            "history_record_status": "expired" if current_promo_status(row, current_date) == "expired" else "current_or_unverified",
            "days_since_last_seen": 0,
            "history_source_names": " | ".join(source_names_for(row)),
            "history_source_urls": " | ".join(source_urls_for(row)),
            "superseded_by_history_id": "",
            "retention_reason": "",
        })
        rows_by_id[history_id] = item
    return list(rows_by_id.values())



def merge_snapshot_into_history(
    history_rows: Iterable[dict],
    snapshot_rows: Iterable[dict],
    *,
    now: datetime | None = None,
    today: date | None = None,
) -> list[dict]:
    """Backfill legacy/current snapshots into an existing history without counting a new sighting."""
    existing = {(_text(row.get("history_id")) or promo_event_key(row)): dict(row) for row in history_rows}
    imported = seed_history_from_snapshot(snapshot_rows, now=now, today=today)
    for candidate in imported:
        history_id = candidate["history_id"]
        if history_id not in existing:
            existing[history_id] = candidate
            continue
        current = existing[history_id]
        current["history_source_names"] = " | ".join(dict.fromkeys(
            _split_pipe(current.get("history_source_names")) + _split_pipe(candidate.get("history_source_names"))
        ))
        current["history_source_urls"] = " | ".join(dict.fromkeys(
            _split_pipe(current.get("history_source_urls")) + _split_pipe(candidate.get("history_source_urls"))
        ))
    return list(existing.values())


def update_history(
    history_rows: Iterable[dict],
    observed_rows: Iterable[dict],
    *,
    run_id: str,
    now: datetime | None = None,
    today: date | None = None,
) -> list[dict]:
    """Upsert fresh observations and retain all earlier observations indefinitely."""
    current_now = now or datetime.now(JAKARTA)
    now_text = _iso_now(current_now)
    current_date = today or current_now.astimezone(JAKARTA).date()
    indexed: dict[str, dict] = {}
    for raw in history_rows:
        row = dict(raw)
        history_id = _text(row.get("history_id")) or promo_event_key(row)
        row["history_id"] = history_id
        row["presence_status"] = "not_seen_this_run"
        indexed[history_id] = row

    observed = [dict(row) for row in observed_rows if not _truthy(row.get("retained_from_previous_run"))]
    observed_ids: set[str] = set()
    observed_families: dict[str, str] = {}
    for row in observed:
        history_id = promo_event_key(row)
        family_id = promo_family_key(row)
        observed_ids.add(history_id)
        observed_families[family_id] = history_id
        old = indexed.get(history_id, {})
        source_names = list(dict.fromkeys(_split_pipe(old.get("history_source_names")) + source_names_for(row)))
        source_urls = list(dict.fromkeys(_split_pipe(old.get("history_source_urls")) + source_urls_for(row)))
        try:
            seen_count = int(old.get("seen_count") or 0) + 1
        except (TypeError, ValueError):
            seen_count = 1
        merged = dict(old)
        merged.update(row)
        merged.update({
            "history_id": history_id,
            "first_seen_at": _text(old.get("first_seen_at")) or _text(row.get("scraped_at")) or now_text,
            "last_seen_at": now_text,
            "last_seen_run_id": run_id,
            "seen_count": seen_count,
            "presence_status": "seen_this_run",
            "history_promo_status": current_promo_status(row, current_date),
            "history_status_as_of": current_date.isoformat(),
            "history_record_status": "expired" if current_promo_status(row, current_date) == "expired" else "current_or_unverified",
            "days_since_last_seen": 0,
            "history_source_names": " | ".join(source_names),
            "history_source_urls": " | ".join(source_urls),
            "superseded_by_history_id": "",
            "retention_reason": "",
        })
        indexed[history_id] = merged

    # When the same campaign/product/period appears with a changed price or offer,
    # keep the old version in history but do not carry it into the current catalog.
    for history_id, row in indexed.items():
        family_id = promo_family_key(row)
        replacement_id = observed_families.get(family_id)
        if replacement_id and replacement_id != history_id:
            row["history_record_status"] = "superseded"
            row["superseded_by_history_id"] = replacement_id
            row["presence_status"] = "superseded_by_new_observation"

    for history_id, row in indexed.items():
        status = current_promo_status(row, current_date)
        row["history_promo_status"] = status
        row["history_status_as_of"] = current_date.isoformat()
        if status == "expired" and row.get("history_record_status") != "superseded":
            row["history_record_status"] = "expired"
        elif row.get("history_record_status") != "superseded":
            row["history_record_status"] = "current_or_unverified"
        last_seen = _parse_timestamp(row.get("last_seen_at"))
        days = max(0, (current_date - last_seen.date()).days) if last_seen else None
        row["days_since_last_seen"] = days if days is not None else ""
    return sorted(indexed.values(), key=lambda row: (_text(row.get("last_seen_at")), _text(row.get("history_id"))), reverse=True)


def carry_forward_rows(
    history_rows: Iterable[dict],
    observed_rows: Iterable[dict],
    *,
    today: date,
    unknown_period_grace_days: int = DEFAULT_UNKNOWN_PERIOD_GRACE_DAYS,
) -> list[dict]:
    """Carry unseen offers only while dated-valid or briefly unverified."""
    observed_ids = {promo_event_key(row) for row in observed_rows if not _truthy(row.get("retained_from_previous_run"))}
    observed_families = {promo_family_key(row) for row in observed_rows if not _truthy(row.get("retained_from_previous_run"))}
    carry: list[dict] = []
    for raw in history_rows:
        row = dict(raw)
        history_id = _text(row.get("history_id")) or promo_event_key(row)
        if history_id in observed_ids:
            continue
        if _text(row.get("history_record_status")) == "superseded":
            continue
        if promo_family_key(row) in observed_families:
            continue
        status = current_promo_status(row, today)
        if status == "expired":
            continue
        last_seen = _parse_timestamp(row.get("last_seen_at") or row.get("scraped_at"))
        days_since = max(0, (today - last_seen.date()).days) if last_seen else None
        if status == "unknown":
            if days_since is None or days_since > unknown_period_grace_days:
                continue
            reason = f"Periode belum jelas; dipertahankan maksimal {unknown_period_grace_days} hari sejak observasi terakhir untuk review."
        else:
            reason = "Tidak terlihat pada run terbaru; dipertahankan karena periode promo belum berakhir."
        row.update({
            "retained_from_previous_run": "true",
            "presence_status": "not_seen_this_run",
            "promo_status": status,
            "history_promo_status": status,
            "history_status_as_of": today.isoformat(),
            "history_record_status": "current_or_unverified",
            "days_since_last_seen": days_since if days_since is not None else "",
            "retention_reason": reason,
        })
        carry.append(row)
    return carry


def save_history(path: Path, rows: Iterable[dict]) -> None:
    """Atomically save history, preserving all fields encountered in the dataset."""
    path = Path(path)
    materialized = [dict(row) for row in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for name in ("history_id", "first_seen_at", "last_seen_at", "last_seen_run_id", "seen_count", "presence_status", "history_promo_status", "history_status_as_of", "history_record_status", "days_since_last_seen", "history_source_names", "history_source_urls", "superseded_by_history_id", "retention_reason"):
        fields.append(name)
    for row in materialized:
        for key in row:
            if key not in fields:
                fields.append(key)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(materialized)
    temp.replace(path)


def export_history_csv(path: Path, rows: Iterable[dict]) -> None:
    """Export a readable, stable history view without altering the state database."""
    preferred = [
        "history_id", "history_record_status", "history_promo_status", "history_status_as_of", "presence_status",
        "product_text", "merchant_name", "promo_price", "normal_price", "discount_percent",
        "valid_from", "valid_until", "period_precision", "campaign_title", "offer_text",
        "first_seen_at", "last_seen_at", "days_since_last_seen", "seen_count",
        "history_source_names", "history_source_urls", "verification_status", "source_url",
        "retention_reason",
    ]
    materialized = [dict(row) for row in rows]
    # Export all remaining fields after the human-facing columns for auditability.
    fields = list(preferred)
    for row in materialized:
        for key in row:
            if key not in fields:
                fields.append(key)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(materialized)
    temp.replace(path)
