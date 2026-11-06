"""Human-reviewed SKU candidate workflow; fuzzy suggestions never attach prices by themselves."""
from __future__ import annotations

import csv
import hashlib
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from promo_names import (
    product_name_brand_match,
    product_name_brand_signature,
    product_name_package_match_signature,
    product_name_variant_signature,
    product_name_packaging_signature,
    product_name_packaging_match,
)

REVIEW_HEADERS = [
    "ID Kandidat", "Produk Promo", "Merchant Promo", "Produk Referensi",
    "Merchant Referensi", "Harga Referensi (Rp)", "Tanggal Observasi Referensi",
    "Umur Data (hari)", "Sumber Referensi", "URL Bukti Harga", "Kemiripan (%)",
    "Merek Promo", "Merek Referensi", "Kecocokan Merek", "Kecocokan Ukuran",
    "Kecocokan Varian", "Kecocokan Kemasan", "Merchant Sama", "Cakupan Merchant", "Klasifikasi Kandidat",
    "Prioritas Review", "Rekomendasi", "Keputusan", "Bukti Identitas SKU (URL)",
    "Catatan Reviewer",
]


def _date_value(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _candidate_id(row: dict) -> str:
    payload = "|".join(str(row.get(k) or "").strip().casefold() for k in (
        "query_product", "query_merchant", "candidate_product", "candidate_merchant",
        "candidate_normal_price", "candidate_observed_at", "candidate_source_url",
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16].upper()


def classify_candidate(row: dict, today: date | None = None) -> dict:
    today = today or date.today()
    query = str(row.get("query_product") or "").strip()
    candidate = str(row.get("candidate_product") or "").strip()
    q_brand = product_name_brand_signature(query)
    c_brand = product_name_brand_signature(candidate)
    brand_value = product_name_brand_match(query, candidate)
    brand_match = "unknown" if brand_value is None else str(brand_value).lower()
    q_package = product_name_package_match_signature(query)
    c_package = product_name_package_match_signature(candidate)
    package_match = bool(q_package) and q_package == c_package
    q_variant = product_name_variant_signature(query)
    c_variant = product_name_variant_signature(candidate)
    variant_match = q_variant == c_variant
    q_packaging = product_name_packaging_signature(query)
    c_packaging = product_name_packaging_signature(candidate)
    packaging_value = product_name_packaging_match(query, candidate)
    packaging_match = "unknown" if packaging_value is None else str(packaging_value).lower()
    q_merchant = str(row.get("query_merchant") or "").strip().casefold()
    c_merchant = str(row.get("candidate_merchant") or "").strip().casefold()
    merchant_match = bool(q_merchant and c_merchant and q_merchant == c_merchant)
    try:
        similarity = float(str(row.get("similarity_score") or 0).replace(",", "."))
    except (TypeError, ValueError):
        similarity = 0.0
    observed = _date_value(row.get("candidate_observed_at"))
    age = (today - observed).days if observed else None
    if brand_match == "false":
        classification, priority = "reject_brand_mismatch", "reject"
        recommendation = "TOLAK — merek berbeda"
    elif not package_match:
        classification, priority = "reject_package_mismatch", "reject"
        recommendation = "TOLAK — ukuran/kemasan berbeda atau tidak lengkap"
    elif not variant_match:
        classification, priority = "reject_variant_mismatch", "reject"
        recommendation = "TOLAK — varian berbeda"
    elif packaging_match == "false":
        classification, priority = "reject_packaging_mismatch", "reject"
        recommendation = "TOLAK — jenis kemasan berbeda"
    elif brand_match == "true":
        classification = "manual_review_same_brand_package_variant"
        priority = "high" if similarity >= 0.82 else "medium"
        recommendation = "TINJAU — merek, ukuran, dan varian cocok; pastikan nama hanya berbeda penulisan"
    else:
        classification, priority = "manual_review_brand_unknown", "low"
        recommendation = "TINJAU MANUAL — merek tidak dapat dipastikan dari nama"
    if age is None:
        age_note = "Tanggal observasi tidak tersedia; harga tidak boleh dianggap terkini"
    elif age < 0:
        age_note = "Tanggal observasi berada di masa depan; periksa timestamp"
    elif age > 30:
        age_note = f"Data harga berumur {age} hari; hanya untuk arsip, bukan estimasi terkini"
    else:
        age_note = f"Data berumur {age} hari"
    merchant_scope = "same_merchant" if merchant_match else "cross_merchant_market_reference_only"
    source_url = str(row.get("candidate_source_url") or "").strip()
    normalized = {
        "ID Kandidat": _candidate_id(row),
        "Produk Promo": query,
        "Merchant Promo": str(row.get("query_merchant") or ""),
        "Produk Referensi": candidate,
        "Merchant Referensi": str(row.get("candidate_merchant") or ""),
        "Harga Referensi (Rp)": row.get("candidate_normal_price", ""),
        "Tanggal Observasi Referensi": row.get("candidate_observed_at", ""),
        "Umur Data (hari)": age if age is not None else "",
        "Sumber Referensi": row.get("candidate_source_name", ""),
        "URL Bukti Harga": source_url,
        "Kemiripan (%)": round(similarity * 100, 1),
        "Merek Promo": q_brand or "Tidak teridentifikasi",
        "Merek Referensi": c_brand or "Tidak teridentifikasi",
        "Kecocokan Merek": brand_match,
        "Kecocokan Ukuran": str(package_match).lower(),
        "Kecocokan Varian": str(variant_match).lower(),
        "Kecocokan Kemasan": packaging_match,
        "Merchant Sama": str(merchant_match).lower(),
        "Cakupan Merchant": merchant_scope,
        "Klasifikasi Kandidat": classification,
        "Prioritas Review": priority,
        "Rekomendasi": recommendation + "; " + age_note,
        "Keputusan": "TOLAK" if priority == "reject" else "BELUM DIREVIEW",
        "Bukti Identitas SKU (URL)": "",
        "Catatan Reviewer": "",
    }
    return normalized


def read_candidate_csv(path: str | Path, today: date | None = None) -> list[dict]:
    path = Path(path)
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [classify_candidate(row, today=today) for row in rows]


def export_review_workbook(candidate_csv: str | Path, output_xlsx: str | Path, today: date | None = None) -> dict:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.utils import get_column_letter

    rows = read_candidate_csv(candidate_csv, today=today)
    output = Path(output_xlsx)
    output.parent.mkdir(parents=True, exist_ok=True)
    previous_decisions = {}
    if output.is_file():
        try:
            old = load_workbook(output, read_only=True, data_only=True)
            if "Review SKU" in old.sheetnames:
                old_ws = old["Review SKU"]
                headers = [str(v or "") for v in next(old_ws.iter_rows(min_row=1, max_row=1, values_only=True))]
                for values in old_ws.iter_rows(min_row=2, values_only=True):
                    record = dict(zip(headers, values))
                    key = str(record.get("ID Kandidat") or "")
                    if key:
                        previous_decisions[key] = (record.get("Keputusan"), record.get("Bukti Identitas SKU (URL)"), record.get("Catatan Reviewer"))
            old.close()
        except Exception:
            previous_decisions = {}
    for row in rows:
        previous = previous_decisions.get(row["ID Kandidat"])
        if previous:
            decision, evidence, note = previous
            if decision:
                row["Keputusan"] = str(decision)
            row["Bukti Identitas SKU (URL)"] = evidence or ""
            row["Catatan Reviewer"] = note or ""

    wb = Workbook()
    ws = wb.active
    ws.title = "Review SKU"
    ws.append(REVIEW_HEADERS)
    for row in rows:
        ws.append([row.get(header, "") for header in REVIEW_HEADERS])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    ws.sheet_view.showGridLines = False
    ws.row_dimensions[1].height = 42
    widths = [18, 42, 20, 42, 20, 18, 24, 15, 20, 62, 15, 20, 20, 16, 16, 16, 16, 16, 34, 38, 16, 62, 22, 58, 50]
    for index, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(index)].width = width
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="244062")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row_idx in range(2, ws.max_row + 1):
        for col_idx in range(1, ws.max_column + 1):
            ws.cell(row_idx, col_idx).alignment = Alignment(vertical="top", wrap_text=col_idx in {2, 4, 10, 18, 19, 21, 23, 24})
        decision_cell = ws.cell(row_idx, REVIEW_HEADERS.index("Keputusan") + 1)
        decision_cell.fill = PatternFill("solid", fgColor="FCE4D6" if decision_cell.value == "TOLAK" else "FFF2CC")
    validation = DataValidation(type="list", formula1='"BELUM DIREVIEW,APPROVE_ALIAS,TOLAK,PERLU_BUKTI"', allow_blank=False)
    validation.error = "Pilih keputusan dari daftar yang tersedia."
    validation.errorTitle = "Keputusan tidak dikenal"
    ws.add_data_validation(validation)
    validation.add(f"W2:W{max(2, ws.max_row)}")

    guide = wb.create_sheet("Petunjuk")
    guide_rows = [
        ["REVIEW KANDIDAT SKU — JANGAN LANGSUNG PAKAI HARGA"],
        ["1. Kandidat di sini hanya saran pencocokan; tidak ada harga yang otomatis ditempel ke katalog."],
        ["2. TOLAK otomatis disarankan jika merek, ukuran, varian, atau jenis kemasan yang sama-sama tercantum ternyata berbeda."],
        ["3. Merchant berbeda tidak otomatis berarti SKU berbeda; itu hanya berarti harga berasal dari retailer lain."],
        ["4. APPROVE_ALIAS hanya untuk produk yang benar-benar SKU sama; isi Bukti Identitas SKU (URL) dan Catatan Reviewer."],
        ["5. Merek yang tidak teridentifikasi perlu bukti manual; sistem tidak menebak merek dari kata pertama."],
        ["6. Harga lebih dari 30 hari dapat disimpan sebagai arsip, tetapi tidak dipakai sebagai estimasi harga terkini."],
        [r"7. Setelah keputusan disimpan, jalankan run.bat --import-sku-review lalu run.bat --rebuild-from-last-snapshot."],
        ["8. Jangan menyetujui kandidat yang hanya mirip kategori/ukuran tetapi berbeda merek atau varian."],
    ]
    for row in guide_rows:
        guide.append(row)
    guide.column_dimensions["A"].width = 150
    for row in guide.iter_rows():
        row[0].alignment = Alignment(wrap_text=True, vertical="top")
    guide.sheet_view.showGridLines = False
    wb.save(output)
    counts = {}
    for row in rows:
        counts[row["Klasifikasi Kandidat"]] = counts.get(row["Klasifikasi Kandidat"], 0) + 1
    return {"rows": len(rows), "classification_counts": counts, "output": str(output)}


def import_review_approvals(review_xlsx: str | Path, aliases_csv: str | Path) -> dict:
    from openpyxl import load_workbook

    review_path = Path(review_xlsx)
    alias_path = Path(aliases_csv)
    if not review_path.is_file():
        raise FileNotFoundError(f"Workbook review tidak ditemukan: {review_path}")
    wb = load_workbook(review_path, read_only=True, data_only=True)
    try:
        if "Review SKU" not in wb.sheetnames:
            raise ValueError("Sheet 'Review SKU' tidak ditemukan.")
        ws = wb["Review SKU"]
        headers = [str(v or "").strip() for v in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))]
        records = [dict(zip(headers, values)) for values in ws.iter_rows(min_row=2, values_only=True)]
    finally:
        wb.close()

    alias_path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if alias_path.is_file():
        with alias_path.open("r", encoding="utf-8-sig", newline="") as handle:
            existing = list(csv.DictReader(handle))
    approved = {}
    for row in existing:
        alias = str(row.get("alias") or "").strip()
        canonical = str(row.get("canonical_name") or "").strip()
        if alias and canonical:
            approved[alias.casefold()] = {
                "alias": alias, "canonical_name": canonical, "approved": "yes",
                "verification_note": row.get("verification_note") or row.get("note", ""),
                "evidence_url": row.get("evidence_url", ""),
            }

    pending = []
    errors = []
    approved_count = 0
    for idx, row in enumerate(records, start=2):
        if str(row.get("Keputusan") or "").strip().upper() != "APPROVE_ALIAS":
            continue
        alias = str(row.get("Produk Promo") or "").strip()
        canonical = str(row.get("Produk Referensi") or "").strip()
        brand_match = str(row.get("Kecocokan Merek") or "unknown").strip().casefold()
        package_match = str(row.get("Kecocokan Ukuran") or "false").strip().casefold() == "true"
        variant_match = str(row.get("Kecocokan Varian") or "false").strip().casefold() == "true"
        packaging_match = str(row.get("Kecocokan Kemasan") or "unknown").strip().casefold()
        proof_url = str(row.get("Bukti Identitas SKU (URL)") or "").strip()
        note = str(row.get("Catatan Reviewer") or "").strip()
        parsed = urlparse(proof_url) if proof_url else None
        if not alias or not canonical or alias.casefold() == canonical.casefold():
            errors.append(f"Baris {idx}: nama alias/kandidat kosong atau sama.")
            continue
        if brand_match == "false":
            errors.append(f"Baris {idx}: merek berbeda; alias ditolak.")
            continue
        if not package_match or not variant_match:
            errors.append(f"Baris {idx}: ukuran/varian tidak cocok; alias ditolak.")
            continue
        if packaging_match == "false":
            errors.append(f"Baris {idx}: jenis kemasan berbeda; alias ditolak.")
            continue
        if brand_match != "true" and not (parsed and parsed.scheme in {"http", "https"} and parsed.hostname and note):
            errors.append(f"Baris {idx}: merek tidak teridentifikasi; isi URL bukti SKU dan catatan verifikasi.")
            continue
        if brand_match == "true" and not (note or (parsed and parsed.scheme in {"http", "https"} and parsed.hostname)):
            errors.append(f"Baris {idx}: approval memerlukan catatan reviewer atau URL bukti SKU.")
            continue
        alias_key = alias.casefold()
        prior = approved.get(alias_key)
        if prior and prior["canonical_name"].casefold() != canonical.casefold():
            errors.append(f"Baris {idx}: alias {alias!r} sudah dipetakan ke kandidat berbeda; konflik tidak diimpor.")
            continue
        pending.append({
            "alias": alias, "canonical_name": canonical, "approved": "yes",
            "verification_note": note, "evidence_url": proof_url,
        })

    # Resolve multiple new decisions for the same alias before writing anything.
    new_by_alias = {}
    conflict_aliases = set()
    for row in pending:
        key = row["alias"].casefold()
        old = new_by_alias.get(key)
        if old and old["canonical_name"].casefold() != row["canonical_name"].casefold():
            conflict_aliases.add(key)
        else:
            new_by_alias[key] = row
    for key in conflict_aliases:
        new_by_alias.pop(key, None)
        errors.append(f"Alias {key!r}: beberapa kandidat berbeda disetujui; tidak ada yang diimpor.")
    for key, row in new_by_alias.items():
        approved[key] = row
        approved_count += 1

    temp = alias_path.with_suffix(alias_path.suffix + ".tmp")
    fields = ["alias", "canonical_name", "approved", "verification_note", "evidence_url"]
    with temp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(approved.values(), key=lambda value: value["alias"].casefold()))
    temp.replace(alias_path)
    return {"approved_aliases_added_or_updated": approved_count, "total_approved_aliases": len(approved), "rejected_decisions": len(errors), "errors": errors, "database_path": str(alias_path)}
