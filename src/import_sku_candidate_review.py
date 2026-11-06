from __future__ import annotations
import argparse
from pathlib import Path
from promo_sku_review import import_review_approvals
ROOT = Path(__file__).resolve().parent.parent

def main(argv=None):
    parser = argparse.ArgumentParser(description="Impor alias SKU yang disetujui manual dari workbook review.")
    parser.add_argument("input", nargs="?", default=str(ROOT / "output" / "Review_Kandidat_SKU.xlsx"))
    parser.add_argument("--aliases", default=str(ROOT / "config" / "product_name_aliases.csv"))
    args = parser.parse_args(argv)
    result = import_review_approvals(args.input, args.aliases)
    print("Alias baru/diperbarui:", result["approved_aliases_added_or_updated"])
    print("Total alias disetujui:", result["total_approved_aliases"])
    print("Keputusan ditolak:", result["rejected_decisions"])
    for error in result["errors"][:30]:
        print(" -", error)
    print("Database alias:", result["database_path"])
    return 0 if not result["errors"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
