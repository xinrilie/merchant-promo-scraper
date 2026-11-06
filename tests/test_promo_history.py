from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import promo_history as history
import promo_multisource_collector as collector

JAKARTA = ZoneInfo("Asia/Jakarta")


def offer(*, promo_price="12900", valid_until="2026-11-10", valid_from="2026-11-01", offer_text="Harga Promo Rp12.900"):
    return {
        "product_text": "Fresh Basket Potato Chips 200 g",
        "merchant_name": "Fresh Basket",
        "campaign_title": "Promo Fresh Basket November 2026",
        "promo_price": promo_price,
        "normal_price": "15900",
        "offer_text": offer_text,
        "deal_type": "single_item",
        "purchase_condition": "",
        "valid_from": valid_from,
        "valid_until": valid_until,
        "period_precision": "range" if valid_from and valid_until else "unknown",
        "promo_status": "active",
        "source_name": "Hemat.id",
        "source_names": "Hemat.id",
        "source_url": "https://hemat.id/promo/fresh-basket",
        "source_urls": "https://hemat.id/promo/fresh-basket",
        "scraped_at": "2026-11-03T09:00:00+07:00",
        "retained_from_previous_run": False,
    }


def test_history_upserts_without_duplicate_and_carries_unseen_valid_offer():
    now1 = datetime(2026, 11, 3, 9, 0, tzinfo=JAKARTA)
    first = history.update_history([], [offer()], run_id="run-1", now=now1, today=date(2026, 11, 3))
    assert len(first) == 1
    history_id = first[0]["history_id"]
    assert first[0]["seen_count"] == 1
    assert first[0]["presence_status"] == "seen_this_run"

    now2 = datetime(2026, 11, 4, 9, 0, tzinfo=JAKARTA)
    second = history.update_history(first, [offer()], run_id="run-2", now=now2, today=date(2026, 11, 4))
    assert len(second) == 1
    assert second[0]["history_id"] == history_id
    assert second[0]["first_seen_at"] == now1.isoformat(timespec="seconds")
    assert second[0]["last_seen_at"] == now2.isoformat(timespec="seconds")
    assert second[0]["seen_count"] == 2

    now3 = datetime(2026, 11, 5, 9, 0, tzinfo=JAKARTA)
    third = history.update_history(second, [], run_id="run-3", now=now3, today=date(2026, 11, 5))
    carry = history.carry_forward_rows(third, [], today=date(2026, 11, 5))
    assert len(third) == 1  # history never discards old offers
    assert len(carry) == 1  # still-valid offer remains available to current snapshot
    assert carry[0]["retained_from_previous_run"] == "true"
    assert carry[0]["presence_status"] == "not_seen_this_run"
    assert carry[0]["promo_status"] == "active"


def test_expired_offer_remains_in_history_but_is_not_carried_to_current_snapshot():
    seeded = history.seed_history_from_snapshot(
        [offer(valid_from="2026-10-01", valid_until="2026-10-31")],
        now=datetime(2026, 11, 3, 9, 0, tzinfo=JAKARTA),
        today=date(2026, 11, 3),
    )
    assert len(seeded) == 1
    assert seeded[0]["history_promo_status"] == "expired"
    updated = history.update_history(seeded, [], run_id="run-expired", now=datetime(2026, 11, 3, 10, tzinfo=JAKARTA), today=date(2026, 11, 3))
    assert len(updated) == 1
    assert updated[0]["history_record_status"] == "expired"
    assert history.carry_forward_rows(updated, [], today=date(2026, 11, 3)) == []


def test_unknown_period_offer_has_limited_review_grace():
    unknown_offer = offer(valid_from="", valid_until="", offer_text="Diskon untuk produk pilihan")
    unknown_offer["scraped_at"] = "2026-11-01T09:00:00+07:00"
    seeded = history.seed_history_from_snapshot(
        [unknown_offer],
        now=datetime(2026, 11, 1, 9, 0, tzinfo=JAKARTA),
        today=date(2026, 11, 1),
    )
    recent = history.carry_forward_rows(seeded, [], today=date(2026, 11, 10), unknown_period_grace_days=14)
    stale = history.carry_forward_rows(seeded, [], today=date(2026, 11, 16), unknown_period_grace_days=14)
    assert len(recent) == 1
    assert "periode belum jelas" in recent[0]["retention_reason"].casefold()
    assert stale == []


def test_changed_price_supersedes_old_offer_but_keeps_both_versions_in_history():
    day1 = datetime(2026, 11, 3, 9, 0, tzinfo=JAKARTA)
    original = offer(promo_price="12900", offer_text="Harga Promo Rp12.900")
    first = history.update_history([], [original], run_id="run-1", now=day1, today=date(2026, 11, 3))
    refreshed = offer(promo_price="11900", offer_text="Harga Promo Rp11.900")
    day2 = datetime(2026, 11, 4, 9, 0, tzinfo=JAKARTA)
    second = history.update_history(first, [refreshed], run_id="run-2", now=day2, today=date(2026, 11, 4))
    assert len(second) == 2
    old = next(row for row in second if row["promo_price"] == "12900")
    new = next(row for row in second if row["promo_price"] == "11900")
    assert old["history_record_status"] == "superseded"
    assert old["superseded_by_history_id"] == new["history_id"]
    assert old["history_id"] not in {row["history_id"] for row in history.carry_forward_rows(second, [refreshed], today=date(2026, 11, 4))}


def test_history_csv_save_load_and_export_are_atomic_and_readable(tmp_path):
    rows = history.update_history(
        [], [offer()], run_id="run-csv",
        now=datetime(2026, 11, 3, 9, 0, tzinfo=JAKARTA), today=date(2026, 11, 3),
    )
    state_path = tmp_path / "state" / "promo_history.csv"
    export_path = tmp_path / "output" / "Riwayat_Promo.csv"
    history.save_history(state_path, rows)
    history.export_history_csv(export_path, rows)
    assert not state_path.with_suffix(".csv.tmp").exists()
    assert not export_path.with_suffix(".csv.tmp").exists()
    loaded = history.load_history(state_path)
    assert len(loaded) == 1
    assert loaded[0]["history_id"] == rows[0]["history_id"]
    with export_path.open("r", encoding="utf-8-sig", newline="") as handle:
        exported = list(csv.DictReader(handle))
    assert len(exported) == 1
    assert exported[0]["product_text"] == "Fresh Basket Potato Chips 200 g"


def test_seed_migration_preserves_all_snapshot_rows_and_source_provenance():
    rows = [
        offer(),
        {**offer(), "source_name": "Scanharga.com", "source_names": "Scanharga.com", "source_url": "https://scanharga.com/promo/fresh-basket", "source_urls": "https://scanharga.com/promo/fresh-basket"},
    ]
    seeded = history.seed_history_from_snapshot(rows, now=datetime(2026, 11, 3, 9, tzinfo=JAKARTA), today=date(2026, 11, 3))
    assert len(seeded) == 1
    assert set(seeded[0]["history_source_names"].split(" | ")) == {"Hemat.id", "Scanharga.com"}
    assert set(seeded[0]["history_source_urls"].split(" | ")) == {rows[0]["source_url"], rows[1]["source_url"]}


def test_collector_main_migrates_snapshot_and_keeps_unseen_valid_rows(tmp_path, monkeypatch):
    import sys
    from datetime import date

    import promo_multisource_collector as collector

    root = tmp_path / "Merchant Promo Scraper"
    runtime = root / "runtime"
    output = root / "output"
    state = root / "state"
    runtime.mkdir(parents=True)
    output.mkdir(parents=True)
    snapshot = offer(valid_until="2026-11-20")
    snapshot["scraped_at"] = "2026-11-02T09:00:00+07:00"
    snapshot["retained_from_previous_run"] = "false"
    collector.write_csv(
        runtime / "promo_multisource_products_all.csv", [snapshot],
        collector.PRODUCT_FIELDS + ["source_urls", "source_names"],
    )

    fresh = {
        **offer(),
        "product_text": "Fresh Basket Corn Chips 150 g",
        "promo_price": "9900",
        "valid_from": "2026-11-01",
        "valid_until": "2026-11-30",
        "scraped_at": "2026-11-03T10:00:00+07:00",
        "retained_from_previous_run": False,
    }

    monkeypatch.setattr(collector, "ROOT_DIR", root)
    monkeypatch.setattr(collector, "RUNTIME_DIR", runtime)
    monkeypatch.setattr(collector, "OUTPUT_DIR", output)
    monkeypatch.setattr(collector, "STATE_DIR", state)
    monkeypatch.setattr(collector, "HISTORY_PATH", state / "promo_history.csv")
    monkeypatch.setattr(collector, "OUT_HISTORY", output / "Riwayat_Promo.csv")
    monkeypatch.setattr(collector, "OUT_ALL", runtime / "promo_multisource_products_all.csv")
    monkeypatch.setattr(collector, "OUT_ARTICLES", runtime / "promo_multisource_articles.csv")
    monkeypatch.setattr(collector, "OUT_IMAGES", runtime / "promo_multisource_catalog_images.csv")
    monkeypatch.setattr(collector, "OUT_LOG", runtime / "promo_multisource_runlog.json")
    monkeypatch.setattr(collector, "OUT_REJECTED_CANDIDATES", runtime / "promo_multisource_rejected_candidates.csv")
    monkeypatch.setattr(collector, "TODAY", date(2026, 11, 3))
    monkeypatch.setattr(collector, "SOURCE_SEEDS", {"Hemat.id": ["https://hemat.id/"]})
    monkeypatch.setattr(collector, "run_source", lambda *_args, **_kwargs: ([fresh], [], [], [{"source_name": "Hemat.id", "status": "ok"}]))
    monkeypatch.setattr(sys, "argv", ["promo_multisource_collector.py"])

    collector.main()

    with (runtime / "promo_multisource_products_all.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        current_rows = list(csv.DictReader(handle))
    assert {row["product_text"] for row in current_rows} == {
        "Fresh Basket Potato Chips 200 g", "Fresh Basket Corn Chips 150 g"
    }
    old_row = next(row for row in current_rows if row["product_text"] == "Fresh Basket Potato Chips 200 g")
    assert old_row["retained_from_previous_run"].casefold() == "true"
    assert old_row["promo_status"] == "active"

    history_rows = history.load_history(state / "promo_history.csv")
    assert len(history_rows) == 2
    assert (output / "Riwayat_Promo.csv").is_file()
    # The complete all-products snapshot is canonical; duplicate active/review
    # CSV exports are no longer generated.
    assert not (runtime / "promo_multisource_products_active.csv").exists()
    assert not (runtime / "promo_multisource_products_review.csv").exists()


def test_collector_main_keeps_expired_rows_in_history_not_current_snapshot(tmp_path, monkeypatch):
    import sys
    from datetime import date

    import promo_multisource_collector as collector

    root = tmp_path / "Project"
    runtime = root / "runtime"
    output = root / "output"
    state = root / "state"
    runtime.mkdir(parents=True)
    output.mkdir(parents=True)
    expired = offer(valid_from="2026-10-01", valid_until="2026-10-31")
    expired["scraped_at"] = "2026-10-29T09:00:00+07:00"
    collector.write_csv(
        runtime / "promo_multisource_products_all.csv", [expired],
        collector.PRODUCT_FIELDS + ["source_urls", "source_names"],
    )

    fresh = {
        **offer(),
        "product_text": "Fresh Basket Corn Chips 150 g",
        "valid_from": "2026-11-01",
        "valid_until": "2026-11-30",
    }
    monkeypatch.setattr(collector, "ROOT_DIR", root)
    monkeypatch.setattr(collector, "RUNTIME_DIR", runtime)
    monkeypatch.setattr(collector, "OUTPUT_DIR", output)
    monkeypatch.setattr(collector, "STATE_DIR", state)
    monkeypatch.setattr(collector, "HISTORY_PATH", state / "promo_history.csv")
    monkeypatch.setattr(collector, "OUT_HISTORY", output / "Riwayat_Promo.csv")
    monkeypatch.setattr(collector, "OUT_ALL", runtime / "promo_multisource_products_all.csv")
    monkeypatch.setattr(collector, "OUT_ARTICLES", runtime / "promo_multisource_articles.csv")
    monkeypatch.setattr(collector, "OUT_IMAGES", runtime / "promo_multisource_catalog_images.csv")
    monkeypatch.setattr(collector, "OUT_LOG", runtime / "promo_multisource_runlog.json")
    monkeypatch.setattr(collector, "OUT_REJECTED_CANDIDATES", runtime / "promo_multisource_rejected_candidates.csv")
    monkeypatch.setattr(collector, "TODAY", date(2026, 11, 3))
    monkeypatch.setattr(collector, "SOURCE_SEEDS", {"Hemat.id": ["https://hemat.id/"]})
    monkeypatch.setattr(collector, "run_source", lambda *_args, **_kwargs: ([fresh], [], [], [{"source_name": "Hemat.id", "status": "ok"}]))
    monkeypatch.setattr(sys, "argv", ["promo_multisource_collector.py"])

    collector.main()

    with (runtime / "promo_multisource_products_all.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        current_rows = list(csv.DictReader(handle))
    assert all(row["product_text"] != "Fresh Basket Potato Chips 200 g" for row in current_rows)
    history_rows = history.load_history(state / "promo_history.csv")
    expired_history = next(row for row in history_rows if row["product_text"] == "Fresh Basket Potato Chips 200 g")
    assert expired_history["history_promo_status"] == "expired"
    assert expired_history["history_record_status"] == "expired"


def test_collector_does_not_overwrite_last_good_snapshot_when_all_sources_empty(tmp_path, monkeypatch):
    import sys
    from datetime import date

    import promo_multisource_collector as collector

    root = tmp_path / "Project"
    runtime = root / "runtime"
    output = root / "output"
    state = root / "state"
    runtime.mkdir(parents=True)
    output.mkdir(parents=True)
    previous_content = "product_text,promo_price\nLast Good Product,10000\n"
    (runtime / "promo_multisource_products_all.csv").write_text(previous_content, encoding="utf-8-sig")
    # Seed one expired record, so nothing is eligible to carry forward on this date.
    expired = offer(valid_from="2026-10-01", valid_until="2026-10-31")
    expired["scraped_at"] = "2026-10-29T09:00:00+07:00"
    collector.write_csv(
        runtime / "promo_multisource_products_all.csv", [expired],
        collector.PRODUCT_FIELDS + ["source_urls", "source_names"],
    )
    previous_content = (runtime / "promo_multisource_products_all.csv").read_text(encoding="utf-8-sig")

    monkeypatch.setattr(collector, "ROOT_DIR", root)
    monkeypatch.setattr(collector, "RUNTIME_DIR", runtime)
    monkeypatch.setattr(collector, "OUTPUT_DIR", output)
    monkeypatch.setattr(collector, "STATE_DIR", state)
    monkeypatch.setattr(collector, "HISTORY_PATH", state / "promo_history.csv")
    monkeypatch.setattr(collector, "OUT_HISTORY", output / "Riwayat_Promo.csv")
    monkeypatch.setattr(collector, "OUT_ALL", runtime / "promo_multisource_products_all.csv")
    monkeypatch.setattr(collector, "OUT_ARTICLES", runtime / "promo_multisource_articles.csv")
    monkeypatch.setattr(collector, "OUT_IMAGES", runtime / "promo_multisource_catalog_images.csv")
    monkeypatch.setattr(collector, "OUT_LOG", runtime / "promo_multisource_runlog.json")
    monkeypatch.setattr(collector, "OUT_REJECTED_CANDIDATES", runtime / "promo_multisource_rejected_candidates.csv")
    monkeypatch.setattr(collector, "TODAY", date(2026, 11, 3))
    monkeypatch.setattr(collector, "SOURCE_SEEDS", {"Hemat.id": ["https://hemat.id/"]})
    monkeypatch.setattr(collector, "run_source", lambda *_args, **_kwargs: ([], [], [], [{"source_name": "Hemat.id", "status": "request_error"}]))
    monkeypatch.setattr(sys, "argv", ["promo_multisource_collector.py"])

    with pytest.raises(RuntimeError, match="Snapshot katalog sebelumnya dipertahankan"):
        collector.main()
    assert (runtime / "promo_multisource_products_all.csv").read_text(encoding="utf-8-sig") == previous_content
    assert (output / "Riwayat_Promo.csv").is_file()


def test_existing_history_is_backfilled_from_legacy_snapshot_without_faking_seen_count():
    now = datetime(2026, 11, 3, 9, 0, tzinfo=JAKARTA)
    existing_offer = offer()
    existing = history.update_history([], [existing_offer], run_id="run-1", now=now, today=date(2026, 11, 3))
    legacy = offer(promo_price="10900", offer_text="Harga Promo Rp10.900")
    legacy["scraped_at"] = "2026-10-30T09:00:00+07:00"
    merged = history.merge_snapshot_into_history(existing, [legacy], now=now, today=date(2026, 11, 3))
    assert len(merged) == 2
    migrated = next(row for row in merged if row["promo_price"] == "10900")
    assert migrated["last_seen_run_id"] == "imported_from_previous_snapshot"
    assert migrated["seen_count"] == 1
    assert migrated["last_seen_at"] == "2026-10-30T09:00:00+07:00"


def test_collector_health_marks_partial_fresh_and_carried_rows():
    products = [
        {"source_name": "Hemat.id", "product_text": "Fresh 100 g", "retained_from_previous_run": False},
        {"source_name": "Hemat.id", "product_text": "Carried 100 g", "retained_from_previous_run": "true"},
    ]
    requests = [{"source_name": "Hemat.id", "status": "ok"}]
    report = collector.build_source_health_report(["Hemat.id"], products, requests)
    assert report["Hemat.id"]["status"] == "fresh_with_preserved"
    assert report["Hemat.id"]["fresh_product_rows"] == 1
    assert report["Hemat.id"]["preserved_previous_rows"] == 1


def test_same_dated_offer_from_different_aggregator_title_updates_one_history_record():
    first = offer()
    second = {
        **first,
        "source_name": "Scanharga.com",
        "source_names": "Scanharga.com",
        "source_url": "https://scanharga.com/promo/fresh-basket",
        "source_urls": "https://scanharga.com/promo/fresh-basket",
        "campaign_title": "Diskon Fresh Basket November — Promo Mingguan",
        "offer_text": "Harga promo Rp12.900 untuk Fresh Basket Potato Chips",
    }
    assert history.promo_event_key(first) == history.promo_event_key(second)
    now = datetime(2026, 11, 3, 9, 0, tzinfo=JAKARTA)
    result = history.update_history([], [first, second], run_id="run-1", now=now, today=date(2026, 11, 3))
    assert len(result) == 1
    assert set(result[0]["history_source_names"].split(" | ")) == {"Hemat.id", "Scanharga.com"}


def test_scanharga_only_history_uses_shorter_carry_forward_window_and_keeps_archive():
    scan = offer()
    scan.update({
        "source_name": "Scanharga.com",
        "source_names": "Scanharga.com",
        "source_url": "https://scanharga.com/promo/fresh-basket",
        "source_urls": "https://scanharga.com/promo/fresh-basket",
        "scraped_at": "2026-10-20T09:00:00+07:00",
    })
    history_rows = history.seed_history_from_snapshot(
        [scan], now=datetime(2026, 10, 20, 9, 0, tzinfo=JAKARTA),
        today=date(2026, 10, 20),
    )
    decisions = {}
    carried = history.carry_forward_rows(
        history_rows, [], today=date(2026, 11, 3), decision_summary=decisions
    )
    assert carried == []  # Scanharga-only product has exceeded its 7-day window.
    assert decisions["not_carried_stale"] == 1
    assert decisions["source_max_age_days"]["Scanharga.com"] == 7
    assert len(history_rows) == 1  # It remains in permanent history.
    assert history_rows[0]["presence_status"] == "not_seen_beyond_carry_window"
    assert "Riwayat tetap disimpan" in history_rows[0]["retention_reason"]


def test_multi_source_offer_uses_longest_source_retention_window():
    mixed = offer()
    mixed.update({
        "source_name": "Hemat.id",
        "source_names": "Hemat.id | Scanharga.com",
        "history_source_names": "Hemat.id | Scanharga.com",
        "scraped_at": "2026-10-20T09:00:00+07:00",
        "last_seen_at": "2026-10-20T09:00:00+07:00",
    })
    history_rows = history.seed_history_from_snapshot(
        [mixed], now=datetime(2026, 10, 20, 9, 0, tzinfo=JAKARTA),
        today=date(2026, 10, 20),
    )
    carried = history.carry_forward_rows(history_rows, [], today=date(2026, 11, 3))
    assert len(carried) == 1
    assert carried[0]["carry_forward_max_age_days"] == 21


def test_collector_source_health_reports_article_and_image_yield():
    products = [
        {"source_name": "Scanharga.com", "product_text": "Only Product 100 g", "retained_from_previous_run": False},
    ]
    requests = [
        {"source_name": "Scanharga.com", "phase": "listing", "status": "ok"},
        {"source_name": "Scanharga.com", "phase": "article", "status": "ok", "product_rows": 1, "image_count": 10},
    ]
    articles = [
        {"source_name": "Scanharga.com", "product_rows_extracted": 1 if i == 0 else 0}
        for i in range(12)
    ]
    images = [{"source_name": "Scanharga.com", "image_url": f"https://example.test/{i}.jpg"} for i in range(10)]
    report = collector.build_source_health_report(
        ["Scanharga.com"], products, requests, articles, images
    )
    source = report["Scanharga.com"]
    assert source["source_role"] == "discovery_support"
    assert source["discovered_article_pages"] == 12
    assert source["articles_with_textual_product_rows"] == 1
    assert source["image_references_found"] == 10


def test_hemat_and_katalogpromosi_have_distinct_carry_forward_windows():
    for source_name, expected_age in (("Hemat.id", 21), ("Katalogpromosi.com", 14)):
        row = offer()
        row.update({
            "source_name": source_name,
            "source_names": source_name,
            "history_source_names": source_name,
            "scraped_at": "2026-10-01T09:00:00+07:00",
        })
        seeded = history.seed_history_from_snapshot(
            [row], now=datetime(2026, 10, 1, 9, 0, tzinfo=JAKARTA),
            today=date(2026, 10, 1),
        )
        assert history.carry_forward_rows(
            seeded, [], today=date(2026, 10, expected_age + 2)
        ) == []
