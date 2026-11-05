# Changelog

## v11 — Smart SKU matching & review-only candidates
- Add canonical physical-unit matching for exact SKU references (e.g. 1.8 L and 1800 ml; 1 kg and 1000 g) while preserving multipack structure so 2 x 500 ml never collapses to 1 L.
- Apply the same exact unit-normalized product identity to manual market references and normal-price estimates.
- Add an optional curated alias file at `config/product_name_aliases.csv`; only approved aliases with identical package and variant signatures are loaded. The file is empty by default.
- Add review-only near-match suggestions at `runtime/price_reference_match_candidates.csv`, including similarity, size/variant/merchant flags, source URL and reason. These suggestions never attach a price or calculate a discount.
- Report separate counts for reordered-token, unit-normalized and approved-alias exact matches.
- Add regression tests for unit conversions, multipack boundaries, variant protection, approved aliases, market-reference matching and non-automatic fuzzy suggestions.

## v10 — Reference integrity & workbook reconciliation
- Quarantine legacy Hemat price-reference records when the merchant is outside the retailer scope explicitly named by a comparison/catalogue URL; invalid records are excluded from matching rather than silently trusted.
- Keep the quarantine ledger persistent in `runtime/price_reference_quarantine.csv` and show all prior/current quarantined records in the visible `Referensi Dikarantina` workbook sheet on subsequent runs.
- Make the everyday workbook buckets mutually exclusive: clean active offers, active offers requiring review, and review-only non-active offers. Add reconciled bucket totals to console and JSON reports.
- Preserve per-source freshness provenance through cross-source deduplication and expose fresh unique offer rows, per-source fresh attributions, preserved attributions, and cross-source overlap in collector/health reports.
- Keep product-reference matching strict on normalized SKU, size, variant, retailer/merchant, region/channel, and age; no fuzzy SKU merge is introduced.
- Add regression tests for persistent quarantine, merchant-scope rejection, cross-source freshness attribution, and non-overlapping review partitions.

## v9 — Promo status & source identity integrity
- Explicit source-side `Expired`/`Kedaluwarsa` labels are preserved as evidence and take precedence over estimated future end dates. These offers remain in history but are excluded from the current active snapshot.
- Hemat card-context extraction now stops before neighboring price-bearing product cards, preventing status/merchant labels from leaking between cards.
- Hemat retailer attribution prefers an explicit retailer prefix in the item-detail URL over a comparison-page wrapper label; generic category URLs do not trigger merchant guesses.
- Leading `None`, `null`, `undefined`, `nan`, and `n/a` brand placeholders are removed from normalized product names while raw source text remains available for audit.
- Conflicting estimated date windows for the same merchant/product/offer are quarantined as `unknown` for manual review instead of silently extending promo validity.
- Explicit expired and active offers are not cross-source merged; equivalent expired observations can still be consolidated historically.
- Added `run.bat --rebuild-from-last-snapshot` to reprocess an existing collector snapshot after a code/validation update without repeating live scraping.
- Added regression coverage for the Alfamart diaper merchant mismatch, explicit expired cards, adjacent-card status isolation, placeholder brands, conflicting estimated dates, and history carry-forward.

## v8 — Source freshness, retention & price-reference matching audit
- Added source-specific carry-forward windows: Hemat.id 21 days, Katalogpromosi.com 14 days, Scanharga.com 7 days; offers with independent evidence from multiple sources use the longest applicable window.
- Unknown-period offers are kept only within the shorter of the 14-day review grace and the source retention window. Stale/unverified offers remain in permanent history with explicit presence and retention reasons, but leave the current snapshot.
- Scanharga is dynamically labelled `discovery_support` when a run finds at least 10 article pages, no more than 5 fresh textual product rows, and image references. Its articles/images remain discoverable without treating posters as product-price evidence.
- Source health now reports article count, text-bearing article count, product rows extracted from articles, image references, and fresh product yield per article; console output includes each source's role and explanation.
- Clarified run metrics so raw extraction rows, fresh deduplicated offers, carried-forward rows, pre-quality-gate active candidates, and post-quality-gate catalogue counts are not conflated.
- Price-reference matching now accepts exact token sets regardless of word order, but continues to require exact size/variant and region/channel signatures. Added diagnostics for SKU, size, variant, scope, and stale-reference mismatches.
- Added regression coverage for source-specific retention, multi-source retention, discovery-role reporting, and safe price identity matching.

## v7.1 — Hemat source routing & source URL display fix
- Replaced the two Hemat seed URLs with seven verified single-retailer catalogue URLs: Alfamart, Indomaret, Alfamidi, Super Indo, Hypermart, Yogya, and Tip Top.
- Hemat listing discovery now accepts only configured single-retailer slugs (including the retailer-specific `/promo-promo/` route), rejecting multi-retailer comparison pages and unsupported retailer slugs.
- Added `preferred_source_url()` for clean catalogue display: prefer valid Hemat product/category detail URLs; otherwise use the identified retailer's single-retailer catalogue; preserve original URL for unknown merchants and non-Hemat sources.
- Applied the preferred URL to both the full clean catalogue and concise Excel/CSV output while preserving original source URLs in raw snapshot/audit provenance.
- Added nine regression tests for seed coverage, listing discovery filters, item URL preference, merchant fallback, and both catalogue exports.
- Fixed Hemat legacy product detail links using `/harga-<slug>/` (in addition to `/harga/<slug>/` and `/katalog/<slug>/`); rebuilt the local catalogue so no displayed Hemat `Sumber URL` remains a comma-separated comparison route.
- Added an additional regression test for the legacy hyphenated detail URL pattern.

## v7 — Manual price verification & normal-price estimate
- Tokku is supported as a small-volume, manual verification source only; no automated Tokku collection is added.
- Manual workbook now captures retailer, source-side last-checked date, price classification, and exact SKU-match status.
- Stale Tokku observations older than 30 days are retained for audit but excluded from current normal-price estimates and market comparisons.
- Added a separate estimated-normal-market-price output, range, provenance, age, and confidence. This never overwrites the source's original/normal price or official discount calculation.
- Three-month Hemat historical averages are a low-confidence fallback and are not labelled as original price. Promo/unknown/historical-minimum records are not used as normal-price estimates.
- Moved mutable market-reference observations to `state/product_market_price_reference.csv`, with one-time migration from the tracked `data/` seed.
- Added `run.bat --prepare-price-research` for offline workbook regeneration.
- Added `run.bat --import-price-research` to import checked references, rebuild the catalog from the last snapshot without live scraping, refresh the workbook, and verify outputs with the launcher-selected interpreter.
