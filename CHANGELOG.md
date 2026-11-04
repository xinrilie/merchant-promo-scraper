# Changelog

## v7 — Manual price verification & normal-price estimate
- Tokku is supported as a small-volume, manual verification source only; no automated Tokku collection is added.
- Manual workbook now captures retailer, source-side last-checked date, price classification, and exact SKU-match status.
- Stale Tokku observations older than 30 days are retained for audit but excluded from current normal-price estimates and market comparisons.
- Added a separate estimated-normal-market-price output, range, provenance, age, and confidence. This never overwrites the source's original/normal price or official discount calculation.
- Three-month Hemat historical averages are a low-confidence fallback and are not labelled as original price. Promo/unknown/historical-minimum records are not used as normal-price estimates.
- Moved mutable market-reference observations to `state/product_market_price_reference.csv`, with one-time migration from the tracked `data/` seed.
- Added `run.bat --prepare-price-research` for offline workbook regeneration.
- Added `run.bat --import-price-research` to import checked references, rebuild the catalog from the last snapshot without live scraping, refresh the workbook, and verify outputs with the launcher-selected interpreter.
