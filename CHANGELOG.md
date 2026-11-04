# Changelog

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
