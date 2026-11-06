from __future__ import annotations
import argparse
from pathlib import Path
from promo_sku_review import export_review_workbook
ROOT = Path(__file__).resolve().parent.parent

def main(argv=None):
    parser = argparse.ArgumentParser(description="Ekspor kandidat pencocokan SKU untuk review manual.")
    parser.add_argument("--input", default=str(ROOT / "runtime" / "price_reference_match_candidates.csv"))
    parser.add_argument("--output", default=str(ROOT / "output" / "Review_Kandidat_SKU.xlsx"))
    args = parser.parse_args(argv)
    result = export_review_workbook(args.input, args.output)
    print("Kandidat SKU untuk review:", result["rows"])
    print("Klasifikasi:", result["classification_counts"])
    print("Workbook:", result["output"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
