"""Grouped regression tests. Cases are organized by functional area."""



from __future__ import annotations

from promo_names import clean_product_name, product_name_similarity, product_names_can_auto_merge

from enrich_existing_promo_catalog_multisource import merge_equivalent_cross_source_offers

import sys

from pathlib import Path

import enrich_existing_promo_catalog_multisource as enhancer



# --- from test_duplicate_fixes.py ---
"""Regression tests for product-name cleanup and cross-source offer dedupe."""

# --- from test_duplicate_fixes.py ---
def row(**overrides):
    base = {
        "product_text": "My Baby Body Cologne Sweet Floral 100 ml",
        "original_product_text": "MY BABY Body Cologne Sweet Floral 100 ml btl",
        "product_name_variants": "MY BABY Body Cologne Sweet Floral 100 ml btl",
        "merchant_name": "Indomaret",
        "campaign_title": "Promo Berhadiah Indomaret 15-28 Oktober 2026",
        "campaign_type": "Promo Umum",
        "promo_status": "active",
        "valid_from": "2026-10-15",
        "valid_until": "2026-10-28",
        "period_precision": "range",
        "period_flags": None,
        "matched_period_text": "15-28 Oktober 2026",
        "published_at": "2026-10-15",
        "promo_price": None,
        "normal_price": None,
        "discount_percent": 50,
        "discount_percent_basis": "bundle_estimate_same_item_value",
        "discount_percent_confidence": "low",
        "discount_percent_calculated": None,
        "discount_savings_rp": None,
        "estimated_bundle_discount_percent": 50,
        "campaign_discount_percent": None,
        "campaign_discount_basis": None,
        "price_parse_method": "no_single_price_bundle_offer",
        "price_basis": "non_numeric_bundle_offer",
        "purchase_condition": "Beli 1 Gratis 1",
        "deal_type": "Beli Gratis",
        "offer_text": "Promo Beli 1 Gratis 1",
        "section": None,
        "source_url": "https://hemat.example/item",
        "source_urls": None,
        "source_campaign_titles": None,
        "source_dataset": "hemat_input.csv",
        "source_name": "Hemat.id",
        "source_names": None,
        "source_type": "aggregator_product_listing",
        "verification_status": "aggregator_only",
        "source_page_url": "https://hemat.example/catalog",
        "source_item_url": "https://hemat.example/item",
        "region_or_channel": None,
        "scraped_at": "2026-10-22T10:00:00+07:00",
        "duplicate_count": 1,
        "duplicate_group_id": None,
        "cross_dataset_duplicate": False,
        "overlapping_offer_count": 1,
        "overlap_period_flag": None,
        "price_quality_flag": None,
        "data_quality_flags": None,
        "retained_from_previous_run": False,
        "raw_line": "Beli 1 Gratis 1",
    }
    base.update(overrides)
    return base

# --- from test_duplicate_fixes.py ---
def test_duplicate_fixes_regressions():
    # Price/promotion labels must not become part of the product name.
    assert clean_product_name("Aice Mochi Vanilla/ Chocolate - Harga Normal 270 g") == "Aice Mochi Vanilla / Chocolate 270 g"
    assert clean_product_name("Aice Mochi Vanilla/ Chocolate 270 g") == "Aice Mochi Vanilla / Chocolate 270 g"
    assert clean_product_name("My Baby Body Cologne Sweet Floral 100 ml Harga Promo Rp 12.900") == "My Baby Body Cologne Sweet Floral 100 ml"

    # My Baby B1G1 should be one offer even when the two sources use slightly different wording.
    m1 = row(source_name="Hemat.id", source_dataset="hemat.csv", valid_from="2026-10-01",
             valid_until="2026-10-31", period_precision="month", source_url="https://hemat.example/mybaby")
    m2 = row(source_name="Katalogpromosi.com", source_dataset="katalogpromosi.csv",
             offer_text="Beli 1 Gratis 1", deal_type="Beli 1 Gratis 1",
             campaign_title="Promo Berhadiah Indomaret 15-28 Oktober 2026 - Beli 1 Gratis 1 My Baby",
             source_url="https://katalogpromosi.example/mybaby")
    merged, groups, absorbed = merge_equivalent_cross_source_offers([m1, m2])
    assert len(merged) == 1 and groups == 1 and absorbed == 1, "B1G1 duplicate was not consolidated"
    assert merged[0]["valid_from"] == "2026-10-15", "Prefer the explicit date range"
    assert "Hemat.id" in (merged[0].get("source_names") or "") and "Katalogpromosi.com" in (merged[0].get("source_names") or "")

    # Aice with a percentage claim vs explicit prices should merge when price and period agree.
    a1 = row(product_text="Aice Mochi Vanilla / Chocolate 270 g", merchant_name="Hypermart",
             original_product_text="Aice Mochi Vanilla/ Chocolate - Harga Normal 270 g",
             product_name_variants="Aice Mochi Vanilla/ Chocolate - Harga Normal 270 g",
             source_name="Hemat.id", source_dataset="hemat.csv", source_url="https://hemat.example/aice",
             campaign_title="Promo Hypermart Oktober 2026", valid_from="2026-10-01",
             valid_until="2026-10-31", period_precision="month", promo_price=9900,
             normal_price=None, discount_percent=67, discount_percent_basis="explicit_offer",
             discount_percent_confidence="medium", discount_percent_calculated=None,
             offer_text="Diskon 67%", purchase_condition=None, deal_type="Diskon Persentase", price_basis="offer_price")
    a2 = row(product_text="Aice Mochi Vanilla / Chocolate 270 g", original_product_text="Aice Mochi Vanilla/ Chocolate 270 g",
             product_name_variants="Aice Mochi Vanilla/ Chocolate 270 g", merchant_name="Hypermart",
             source_name="Katalogpromosi.com", source_dataset="katalogpromosi.csv", source_url="https://katalogpromosi.example/aice",
             campaign_title="Promo Hypermart Daily Fresh 16-22 Oktober 2026", valid_from="2026-10-16",
             valid_until="2026-10-22", period_precision="range", promo_price=9900,
             normal_price=29990, discount_percent=67, discount_percent_basis="calculated_from_unit_prices",
             discount_percent_confidence="high", discount_percent_calculated=67.0,
             offer_text="Harga Normal Rp 29.990 | Harga Promo Rp 9.900", purchase_condition=None,
             deal_type="Diskon Persentase", price_basis="offer_price", discount_savings_rp=20090)
    merged, groups, absorbed = merge_equivalent_cross_source_offers([a1, a2])
    assert len(merged) == 1 and groups == 1 and absorbed == 1, "Aice cross-source duplicate was not consolidated"
    assert merged[0]["normal_price"] == 29990 and merged[0]["promo_price"] == 9900
    assert merged[0]["valid_from"] == "2026-10-16" and merged[0]["valid_until"] == "2026-10-22"

    # A near-identical name can merge dynamically when merchant, size, variant,
    # period, price and offer evidence are compatible.
    fuzzy_name_a = "Wall's Ice Cream Avocado Brownie Matcha Strawberry Cookies Cream Strawberry Cheese Tub 350 ml"
    fuzzy_name_b = "Wall's Cream Avocado Brownie Matcha Strawberry Cookies Cream Strawberry Cheese Tub 350 ml"
    assert product_name_similarity(fuzzy_name_a, fuzzy_name_b) >= 0.93
    assert product_names_can_auto_merge(fuzzy_name_a, fuzzy_name_b)
    f1 = row(product_text=fuzzy_name_a, original_product_text=fuzzy_name_a,
             product_name_variants=fuzzy_name_a, source_name="Hemat.id",
             source_dataset="hemat.csv", source_url="https://hemat.example/walls-a",
             source_item_url="https://hemat.example/item/walls-a")
    f2 = dict(f1, product_text=fuzzy_name_b, original_product_text=fuzzy_name_b,
              product_name_variants=fuzzy_name_b, source_name="Katalogpromosi.com",
              source_dataset="katalogpromosi.csv", source_url="https://katalogpromosi.example/walls-b",
              source_item_url="https://katalogpromosi.example/item/walls-b")
    fuzzy_merged, fuzzy_groups, fuzzy_absorbed = merge_equivalent_cross_source_offers([f1, f2])
    assert len(fuzzy_merged) == 1 and fuzzy_groups == 1 and fuzzy_absorbed == 1, "High-confidence fuzzy name match was not consolidated"


    # Dynamic fuzzy matching should identify spelling/punctuation variation but
    # protect explicit SKU size and flavour differences.
    assert product_name_similarity("Aice Mochi Vanilla Chocolate 270 g", "Aice Mochi Vanilla / Chocolate 270 g") >= 0.99
    assert product_names_can_auto_merge("Aice Mochi Vanilla Chocolate 270 g", "Aice Mochi Vanilla / Chocolate 270 g")
    assert not product_names_can_auto_merge("Sunlight Jeruk 755 ml", "Sunlight Jeruk 450 ml")
    assert not product_names_can_auto_merge("Aice Mochi Vanilla 270 g", "Aice Mochi Chocolate 270 g")

    # A combined Hemat listing can resolve to one specific retailer only when
    # the independent source names that retailer and offer/price/period evidence agrees.
    unknown_merchant = row(merchant_name=None, source_name="Hemat.id", source_dataset="hemat.csv",
        source_url="https://www.hemat.id/katalog-alfamart,hypermart/", source_page_url="https://www.hemat.id/katalog-alfamart,hypermart/",
        source_item_url="https://www.hemat.id/item/aice",
        product_text="Aice Mochi Vanilla Chocolate 270 g", original_product_text="Aice Mochi Vanilla Chocolate 270 g",
        product_name_variants="Aice Mochi Vanilla Chocolate 270 g", promo_price=9900, normal_price=29990,
        discount_percent=67, discount_percent_basis="calculated_from_unit_prices",
        offer_text="Harga Normal Rp 29.990 Harga Promo Rp 9.900", deal_type="Diskon Persentase", price_basis="offer_price",
        period_precision="month", valid_from="2026-10-01", valid_until="2026-10-31", period_flags=None)
    known_merchant = row(merchant_name="Hypermart", source_name="Katalogpromosi.com", source_dataset="katalogpromosi.csv",
        source_url="https://katalogpromosi.example/aice", source_page_url="https://katalogpromosi.example/aice",
        source_item_url="https://katalogpromosi.example/item/aice", product_text="Aice Mochi Vanilla / Chocolate 270 g",
        original_product_text="Aice Mochi Vanilla / Chocolate 270 g", product_name_variants="Aice Mochi Vanilla / Chocolate 270 g",
        promo_price=9900, normal_price=29990, discount_percent=67,
        discount_percent_basis="calculated_from_unit_prices", discount_percent_confidence="high",
        offer_text="Harga Normal Rp 29.990 Harga Promo Rp 9.900", deal_type="Diskon Persentase", price_basis="offer_price",
        campaign_title="Promo Hypermart Daily Fresh 16-22 Oktober 2026", valid_from="2026-10-16", valid_until="2026-10-22", period_precision="range", period_flags=None)
    fuzzy_merged, inferred_groups, inferred_absorbed = merge_equivalent_cross_source_offers([unknown_merchant, known_merchant])
    assert len(fuzzy_merged) == 1 and inferred_groups == 1 and inferred_absorbed == 1, "Combined Hemat retailer was not corroborated/merged"
    assert fuzzy_merged[0]["merchant_name"] == "Hypermart"
    assert fuzzy_merged[0]["merchant_resolution_method"] == "cross_source_corroboration_unverified"

    # My Baby B1G1: unknown retailer from a combined Hemat listing can match a named
    # Indomaret article when product, bundle ratio, period, and URL retailer evidence agree.
    mybaby_hemat = row(merchant_name=None, source_name="Hemat.id", source_dataset="hemat.csv",
        source_url="https://www.hemat.id/katalog-alfamart,indomaret/", source_page_url="https://www.hemat.id/katalog-alfamart,indomaret/",
        source_item_url="https://www.hemat.id/item/mybaby", product_text="My Baby Body Cologne Sweet Floral 100 ml",
        original_product_text="MY BABY Body Cologne Sweet Floral 100ml btl", product_name_variants="MY BABY Body Cologne Sweet Floral 100ml btl",
        promo_price=None, normal_price=None, discount_percent=50, discount_percent_basis="explicit_offer",
        offer_text="Diskon 50%", purchase_condition=None, deal_type="Diskon Persentase", price_basis="non_numeric_bundle_offer",
        valid_from="2026-10-01", valid_until="2026-10-31", period_precision="month", period_flags=None)
    mybaby_known = row(merchant_name="Indomaret", source_name="Katalogpromosi.com", source_dataset="katalogpromosi.csv",
        source_url="https://katalogpromosi.example/promo-indomaret", source_page_url="https://katalogpromosi.example/promo-indomaret",
        source_item_url="https://katalogpromosi.example/item/mybaby", product_text="MY BABY Body Cologne Sweet Floral 100ml btl",
        original_product_text="MY BABY Body Cologne Sweet Floral 100ml btl", product_name_variants="MY BABY Body Cologne Sweet Floral 100ml btl",
        promo_price=None, normal_price=None, discount_percent=50, discount_percent_basis="bundle_estimate_same_item_value",
        discount_percent_confidence="low", estimated_bundle_discount_percent=50,
        offer_text="Promo Beli 1 Gratis 1", purchase_condition="Beli 1 Gratis 1", deal_type="Beli 1 Gratis 1",
        price_basis="non_numeric_bundle_offer", valid_from="2026-10-15", valid_until="2026-10-28", period_precision="range", period_flags=None,
        campaign_title="Promo Berhadiah Indomaret 15-28 Oktober 2026, Beli 1 Gratis 1 My Baby-Tropicana Slim")
    mybaby_merged, _, _ = merge_equivalent_cross_source_offers([mybaby_hemat, mybaby_known])
    assert len(mybaby_merged) == 1 and mybaby_merged[0]["merchant_name"] == "Indomaret", "My Baby cross-source duplicate was not consolidated"

    # If the exact same offer could correspond to two retailers named in the
    # combined Hemat URL, do not guess which retailer owns the card.
    known_alfamart = dict(known_merchant, merchant_name="Alfamart",
        source_url="https://katalogpromosi.example/aice-alfamart",
        source_page_url="https://katalogpromosi.example/aice-alfamart",
        campaign_title="Promo Alfamart 16-22 Oktober 2026")
    ambiguous_result, _, _ = merge_equivalent_cross_source_offers([
        dict(unknown_merchant), dict(known_merchant), known_alfamart
    ])
    assert len(ambiguous_result) == 3, "Ambiguous retailer match was incorrectly merged"
    assert any(not r.get("merchant_name") for r in ambiguous_result), "Ambiguous Hemat row should remain unassigned"

    # Distinct purchase tiers remain separate even when their row prices are absent.
    tier5 = row(
        product_text="Yummy Choice Fried Chicken", merchant_name="Indomaret",
        source_name="Katalogpromosi.com", source_dataset="katalog.csv",
        source_url="https://katalogpromosi.example/yummy-choice",
        campaign_title="Promo Indomaret Fresh 16-31 Oktober 2026",
        valid_from="2026-10-16", valid_until="2026-10-31", period_precision="range",
        promo_price=None, normal_price=None, discount_percent=None,
        offer_text="Beli 5 pcs Diskon Rp10.000", purchase_condition="Beli 5 pcs",
        deal_type="Diskon nominal", price_basis="bundle_offer_amount",
    )
    tier10 = dict(tier5, source_name="Scanharga.com", source_dataset="scan.csv",
        source_url="https://scan.example/yummy-choice",
        offer_text="Beli 10 pcs Diskon Rp24.000", purchase_condition="Beli 10 pcs")
    tier_result, tier_groups, tier_absorbed = merge_equivalent_cross_source_offers([tier5, tier10])
    assert len(tier_result) == 2 and tier_groups == 0 and tier_absorbed == 0, "different buy-quantity tiers were merged"

    # Conflicting explicit prices must never be silently merged.
    c1 = dict(a2, promo_price=10900, discount_percent=63.7, discount_percent_calculated=63.7,
              source_url="https://hemat.example/aice-price-a", source_name="Hemat.id", source_dataset="hemat.csv")
    c2 = dict(a2, promo_price=9900, discount_percent=67.0, discount_percent_calculated=67.0,
              source_url="https://katalogpromosi.example/aice-price-b", source_name="Katalogpromosi.com", source_dataset="katalogpromosi.csv")
    merged, groups, absorbed = merge_equivalent_cross_source_offers([c1, c2])
    assert len(merged) == 2 and groups == 0, "Conflicting prices were silently merged"
    print("SELF-TEST PASSED: name cleaning, conservative fuzzy matching, duplicate-candidate review, and price-conflict protection.")

# --- from test_duplicate_fixes.py ---
def test_canonical_package_signature_normalizes_metric_units_without_collapsing_pack_structure():
    from promo_names import product_name_package_match_signature, product_name_matching_key

    assert product_name_package_match_signature("Susu UHT Full Cream 1.8 L") == product_name_package_match_signature("Susu UHT Full Cream 1800 ml")
    assert product_name_matching_key("Minyak Goreng 1 kg") == product_name_matching_key("Minyak Goreng 1000 g")
    assert product_name_matching_key("Susu 2 x 500 ml") == product_name_matching_key("Susu 2x0.5 L")
    assert product_name_matching_key("Susu 2 x 500 ml") != product_name_matching_key("Susu 1 L")
    assert product_name_matching_key("Mie Instan 10 x 27 g") != product_name_matching_key("Mie Instan 270 g")

# --- from test_duplicate_fixes.py ---
def test_canonical_package_signature_keeps_variant_tokens_exact():
    from promo_names import product_name_matching_key

    assert product_name_matching_key("Susu UHT Cokelat 1 L") != product_name_matching_key("Susu UHT Full Cream 1000 ml")

# --- from test_duplicate_fixes.py ---
def test_indonesian_thousands_notation_in_product_size_is_normalized_safely():
    from promo_names import product_name_package_match_signature, clean_product_name

    assert clean_product_name("Minyak Goreng 1.000 ml") == "Minyak Goreng 1000 ml"
    assert product_name_package_match_signature("Minyak Goreng 1.000 ml") == product_name_package_match_signature("Minyak Goreng 1 L")
    assert product_name_package_match_signature("Minyak Goreng 1,5 L") == product_name_package_match_signature("Minyak Goreng 1500 ml")

# --- from test_merchant_gift_dedupe.py ---
ENGINE_DIR = Path(__file__).resolve().parents[1] / "src"

# --- from test_merchant_gift_dedupe.py ---
sys.path.insert(0, str(ENGINE_DIR))

# --- from test_merchant_gift_dedupe.py ---
def _base_row(**updates):
    row = {
        "product_text": "Sunlight Jeruk 755 ml",
        "original_product_text": "Sunlight Jeruk 755 ml",
        "merchant_name": "Indomaret",
        "campaign_title": "Promo Indomaret 23-25 Oktober 2026",
        "promo_status": "active",
        "period_precision": "range",
        "valid_from": "2026-10-23",
        "valid_until": "2026-10-25",
        "promo_price": 16900,
        "normal_price": 22900,
        "discount_percent": 26.2,
        "discount_percent_basis": "calculated_from_unit_prices",
        "discount_percent_confidence": "high",
        "price_basis": "offer_price",
        "offer_text": "Harga Normal Rp22.900, Harga Promo Rp16.900",
        "purchase_condition": None,
        "deal_type": "Diskon Persentase",
        "source_url": "https://example.test/promo-a",
        "source_item_url": "https://example.test/item-a",
        "source_name": "Katalogpromosi.com",
        "source_dataset": "katalog.csv",
        "product_validation_status": "eligible",
        "price_quality_flag": None,
    }
    row.update(updates)
    return row

# --- from test_merchant_gift_dedupe.py ---
def test_generic_merchant_is_resolved_from_article_title_and_url():
    merchant, method = enhancer.canonical_merchant(
        "Lainnya",
        "Duo Bakso A: promo spesial Es Teler 77",
        "https://katalogpromosi.com/promo/promo-es-teler-77-duo-bakso-a",
    )
    assert merchant == "Es Teler 77"
    assert method in {"title_url_known_alias", "known_alias_from_title_or_url", "source_url_known_alias"}

# --- from test_merchant_gift_dedupe.py ---
def test_generic_merchant_is_not_kept_when_context_is_ambiguous():
    merchant, method = enhancer.canonical_merchant(
        "Lainnya",
        "Promo Es Teler 77 x McDonald's",
        "https://example.test/promo-es-teler-77-mcdonalds",
    )
    assert merchant is None
    assert method == "conflicting_merchant_context"

# --- from test_merchant_gift_dedupe.py ---
def test_dynamic_unknown_merchant_inference_remains_supported():
    merchant, method = enhancer.canonical_merchant(
        "Lainnya",
        "Promo All Fruit 23-25 Oktober 2026",
        "https://example.test/promo-all-fruit",
    )
    assert merchant == "All Fruit"
    assert method == "campaign_title_inference"

# --- from test_merchant_gift_dedupe.py ---
def test_cross_sku_gift_does_not_become_product_discount():
    # Reproduce the live-row leak: 400 g facial tissue with a different travel-pack SKU.
    offer = "BELI 1 GRATIS 2 pck INDOMARET Travel Pack Tissue 50’s"
    flags = []
    discount = enhancer.safe_discount_fields(
        offer_text=offer,
        promo_price=None,
        normal_price=None,
        price_basis="non_numeric_bundle_offer",
        purchase_condition="BELI 1 GRATIS 2 pck INDOMARET Travel Pack Tissue 50’s",
        deal_type="Beli Gratis",
        quality_flags=flags,
        product_text="Indomaret Facial Tissue Non Perfumed 400 g",
        raw_line=f"Indomaret Facial Tissue Non Perfumed 400 g: {offer}",
    )
    assert discount["discount_percent"] is None
    assert discount["estimated_bundle_discount_percent"] is None
    assert discount["discount_percent_basis"] == "cross_sku_bundle_review"
    assert "cross_sku_gift_not_product_discount" in flags

    row = _base_row(
        product_text="Indomaret Facial Tissue Non Perfumed 400 g",
        offer_text=offer,
        purchase_condition="BELI 1 GRATIS 2 pck INDOMARET Travel Pack Tissue 50’s",
        deal_type="Beli Gratis",
        discount_percent=None,
        discount_percent_basis="cross_sku_bundle_review",
        discount_percent_confidence="unknown",
        promo_price=None,
        normal_price=None,
        price_basis="non_numeric_bundle_offer",
        price_quality_flag="cross_sku_gift_not_product_discount",
    )
    _, gate_report = enhancer.apply_export_quality_gate([row])
    assert gate_report["routed_to_review_rows"] == 1
    assert "cross_sku_gift_bundle_requires_review" in gate_report["routed_rows"][0]["issues"]

# --- from test_merchant_gift_dedupe.py ---
def test_generic_buy_one_get_one_estimate_still_supported_without_named_gift_sku():
    flags = []
    discount = enhancer.safe_discount_fields(
        offer_text="Beli 1 Gratis 1",
        promo_price=None,
        normal_price=None,
        price_basis="non_numeric_bundle_offer",
        purchase_condition="Beli 1 Gratis 1",
        deal_type="Beli Gratis",
        quality_flags=flags,
        product_text="Indomie Goreng",
    )
    assert discount["discount_percent"] == 50.0
    assert discount["discount_percent_basis"] == "bundle_estimate_same_item_value"
    assert "cross_sku_gift_not_product_discount" not in flags

# --- from test_merchant_gift_dedupe.py ---
def test_dedupe_does_not_merge_different_named_gift_items():
    a = _base_row(
        product_text="Facial Tissue 400 g",
        offer_text="Beli 1 Gratis 1, hadiah Facial Tissue Travel Pack",
        purchase_condition="Beli 1 Gratis 1",
        deal_type="Beli Gratis",
    )
    b = dict(a)
    b.update({
        "offer_text": "Beli 1 Gratis 1, hadiah Wet Wipes Travel Pack",
        "source_url": "https://example.test/promo-b",
        "source_item_url": "https://example.test/item-b",
    })
    assert enhancer._gift_item_signature(a) != enhancer._gift_item_signature(b)
    assert not enhancer._compatible_offers(a, b)
    merged, groups, absorbed = enhancer.merge_equivalent_cross_source_offers([a, b])
    assert len(merged) == 2
    assert groups == 0 and absorbed == 0

# --- from test_merchant_gift_dedupe.py ---
def test_duplicate_review_rows_show_priority_and_sort_highest_first():
    # Same product and compatible offer, but date evidence is missing; this is a
    # legitimate high-priority review candidate rather than an offer conflict.
    exact_a = _base_row(
        product_text="Sunlight Jeruk 755 ml",
        offer_text="Harga Promo Rp16.900",
        promo_price=16900,
        valid_from=None,
        valid_until=None,
        source_url="https://example.test/a",
        source_item_url="https://example.test/item-a",
    )
    exact_b = dict(exact_a, source_url="https://example.test/b", source_item_url="https://example.test/item-b")
    similar = dict(
        exact_a,
        product_text="Sunlight Jeruk Lime 755 ml",
        source_url="https://example.test/c",
        source_item_url="https://example.test/item-c",
        promo_price=14900,
        offer_text="Harga Promo Rp14.900",
    )
    candidates = enhancer.build_possible_duplicate_rows([exact_a, exact_b, similar])
    assert candidates
    assert all(row.get("Prioritas Review") in {"Tinggi", "Sedang", "Rendah"} for row in candidates)
    priority_rank = {"Tinggi": 0, "Sedang": 1, "Rendah": 2}
    ranks = [priority_rank[row["Prioritas Review"]] for row in candidates]
    assert ranks == sorted(ranks)
    assert candidates[0]["Prioritas Review"] == "Tinggi"
    assert "Prioritas Review" in enhancer.POSSIBLE_DUPLICATE_FIELDS

# --- from test_merchant_gift_dedupe.py ---
def test_different_purchase_quantity_tiers_are_not_high_priority_duplicate_merges():
    buy_five = _base_row(
        product_text="Yummy Choice Fried Chicken",
        offer_text="Beli 5 diskon Rp10.000",
        purchase_condition="Beli 5 pcs diskon Rp10.000",
        deal_type="Beli Banyak Lebih Hemat",
        promo_price=None,
        normal_price=None,
        valid_from=None,
        valid_until=None,
        source_url="https://example.test/yummy-a",
        source_item_url="https://example.test/yummy-item-a",
    )
    buy_ten = dict(
        buy_five,
        offer_text="Beli 10 diskon Rp24.000",
        purchase_condition="Beli 10 pcs diskon Rp24.000",
        source_url="https://example.test/yummy-b",
        source_item_url="https://example.test/yummy-item-b",
    )
    candidates = enhancer.build_possible_duplicate_rows([buy_five, buy_ten])
    assert len(candidates) == 1
    pair = candidates[0]
    assert pair["Prioritas Review"] != "Tinggi"
    assert "Pertahankan terpisah" in pair["Tindakan"]
    assert "tingkat pembelian berbeda" in pair["Tindakan"]
