from __future__ import annotations

"""Heuristics for extracting unknown merchant labels without a merchant allow-list.

Known aliases may still be used by source adapters to canonicalize familiar names.
This utility only supplies a conservative fallback from campaign titles/URL slugs;
ambiguous long titles return None rather than pretending to know the merchant.
"""

import re
from urllib.parse import urlparse

SPACE_RE = re.compile(r"\s+")
MONTHS = (
    "januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember|"
    "jan|feb|mar|apr|jun|jul|agu|ags|agst|sep|sept|okt|nov|des"
)
TITLE_PREFIX_RE = re.compile(r"^\s*(?:(?:katalog\s+promo|promo(?:si)?|katalog|penawaran)\s+)", re.I)
TITLE_STOP_RE = re.compile(
    r"\b(?:jsm|psm|minggu\s+ini|minggu\s+depan|akhir\s+pekan|weekend|weekday|"
    r"terbaru|bulan\s+ini|bulan\s+depan|katalog(?:\s+belanja)?|promo(?:si)?|"
    r"diskon|cashback|voucher|kupon|tebus\s+murah|serba\s+gratis|harga(?:\s+spesial)?|"
    r"periode|berlaku|khusus|spesial|hingga|sampai|mulai|ada|hadir(?:kan)?|"
    r"beli\s+\d|buy\s*\d|gratis|potongan|tanggal|untuk|dengan|bersama|pakai|menggunakan|"
    r"sale|deals?|payday|anniversary|b1g1|flash|dari\s+tanggal|x|via|"
    r"januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember|"
    r"jan(?:uari)?|feb(?:ruari)?|mar(?:et)?|apr(?:il)?|jun(?:i)?|jul(?:i)?|agu(?:stus)?|"
    r"sep(?:tember)?|okt(?:ober)?|nov(?:ember)?|des(?:ember)?|20\d{2})\b",
    re.I,
)
LABEL_NOISE_RE = re.compile(
    r"(?:\brp\.?\s*\d|\d{1,2}\s*[-–—]\s*\d{1,2}|%|[!?;]|"
    r"syarat|ketentuan|minimal belanja|tebus murah|cashback|voucher|kupon)",
    re.I,
)
GENERIC_ONLY = {"promo", "promosi", "katalog", "penawaran", "diskon", "belanja", "minggu", "terbaru", "spesial", "sale", "deal", "deals", "payday", "anniversary", "flash", "gratis", "b1g1", "b1g0", "buy", "get", "harga", "cashback", "voucher", "kupon", "jsm", "psm"}


def clean_text(value: object) -> str:
    return SPACE_RE.sub(" ", str(value or "")).strip()



# Retailer prefixes embedded in Hemat product/category detail slugs.
# These item-level URLs are stronger evidence than the comparison-page URL.
_HEMAT_RETAILER_SLUGS = (
    ("Super Indo", ("superindo", "super-indo")),
    ("Alfamart", ("alfamart",)),
    ("Alfamidi", ("alfamidi",)),
    ("Indomaret", ("indomaret",)),
    ("Hypermart", ("hypermart",)),
    ("Yogya", ("yogya", "yomart")),
    ("Tip Top", ("tip-top", "tiptop")),
    ("Lotte Mart", ("lottemart", "lotte-mart")),
    ("Transmart", ("transmart",)),
    ("AEON", ("aeon",)),
    ("Courts", ("courts",)),
    ("Hari Hari Swalayan", ("hari-hari", "harihari", "hari-hari-swalayan")),
)


def _retailer_slug_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean_text(value).casefold())


def canonical_hemat_retailer(value: object) -> str | None:
    """Canonicalize a retailer label only when it matches a known Hemat alias."""
    key = _retailer_slug_key(value)
    if not key:
        return None
    for canonical, aliases in _HEMAT_RETAILER_SLUGS:
        if key == _retailer_slug_key(canonical) or any(key == _retailer_slug_key(alias) for alias in aliases):
            return canonical
    return None


def hemat_retailer_scope_from_url(url: object) -> set[str] | None:
    """Return retailers explicitly represented by a Hemat catalogue URL.

    Examples:
      /katalog-alfamart/ -> {"Alfamart"}
      /katalog-alfamart,courts/promo-promo/ -> {"Alfamart", "Courts"}

    Product detail URLs such as /katalog/biore.../ and unrelated URLs return
    None because they do not define a catalogue retailer scope.
    """
    parsed = urlparse(clean_text(url))
    if parsed.scheme not in {"http", "https"} or (parsed.hostname or "").casefold() not in {"hemat.id", "www.hemat.id"}:
        return None
    for part in (segment for segment in (parsed.path or "").split("/") if segment):
        match = re.fullmatch(r"katalog-([^/]+)", part, flags=re.I)
        if not match:
            continue
        slug = match.group(1)
        retailers = set()
        for token in slug.split(","):
            token = token.strip()
            canonical = canonical_hemat_retailer(token)
            if canonical:
                retailers.add(canonical)
        return retailers or None
    return None


def hemat_merchant_scope_issue(merchant: object, url: object) -> str | None:
    """Flag a merchant outside the retailer(s) named by its Hemat catalogue URL.

    This is a conservative guardrail: it never guesses which retailer supplied
    an offer when the URL lists multiple retailers. It only rejects a clearly
    impossible attribution, e.g. merchant AEON on an Alfamart-vs-Courts page.
    """
    scope = hemat_retailer_scope_from_url(url)
    if scope is None:
        return None
    canonical = canonical_hemat_retailer(merchant)
    if canonical is None:
        return "merchant_not_recognized_in_hemat_catalogue_scope"
    if canonical not in scope:
        return "merchant_not_in_hemat_catalogue_scope"
    return None

def infer_hemat_retailer_from_item_url(url: object) -> str | None:
    """Return a retailer only when a Hemat item-detail slug explicitly starts with it.

    Comparison/listing URLs are intentionally rejected. Example:
    ``/katalog/alfamart.popok-dewasa-celana/`` -> ``Alfamart``.
    Generic category slugs such as ``/katalog/buah-mangga/`` return ``None``.
    """
    parsed = urlparse(clean_text(url))
    if parsed.scheme not in {"http", "https"} or (parsed.hostname or "").casefold() not in {"hemat.id", "www.hemat.id"}:
        return None
    parts = [part for part in (parsed.path or "").split("/") if part]
    for idx, part in enumerate(parts[:-1]):
        if part.casefold() not in {"katalog", "harga"}:
            continue
        slug = parts[idx + 1].casefold()
        for canonical, aliases in _HEMAT_RETAILER_SLUGS:
            for alias in aliases:
                if slug == alias or any(slug.startswith(alias + separator) for separator in (".", "-", "_")):
                    return canonical
    return None

def infer_merchant_candidate_from_title(title: object) -> str | None:
    """Extract a short candidate from a title with an explicit campaign prefix.

    Example: 'Promo All Fruit 23-25 Oktober 2026' -> 'All Fruit'.
    It deliberately avoids retailer-specific allow/deny lists.
    """
    text = clean_text(title)
    if not text or not re.match(r"^(?:promo(?:si)?|katalog|penawaran)\b", text, re.I):
        return None

    text = TITLE_PREFIX_RE.sub("", text, count=1).strip(" :|–—-")
    text = re.sub(r"^(?:jsm|psm)\s+", "", text, flags=re.I).strip()
    text = re.split(r"[:|]", text, maxsplit=1)[0].strip()

    date_match = re.search(rf"\b\d{{1,2}}\s*(?:[-–—]\s*\d{{1,2}})?\s+(?:{MONTHS})\b", text, re.I)
    if date_match:
        text = text[:date_match.start()].strip(" :|–—-")
    year_match = re.search(r"\b20\d{2}\b", text)
    if year_match:
        text = text[:year_match.start()].strip(" :|–—-")
    stop = TITLE_STOP_RE.search(text)
    if stop:
        text = text[:stop.start()].strip(" :|–—-")
    text = re.split(r"\s+[–—]\s+", text, maxsplit=1)[0].strip(" :|–—-")

    tokens = re.findall(r"[\w&'.!]+", text, flags=re.UNICODE)
    if not tokens or len(tokens) > 3 or LABEL_NOISE_RE.search(text):
        return None
    if not any(ch.isalpha() for ch in text) or all(token.casefold() in GENERIC_ONLY for token in tokens):
        return None
    return text


def infer_merchant_candidate_from_url(url: object) -> str | None:
    """Extract an unknown candidate from explicit promo/catalog URL slugs only."""
    parsed = urlparse(clean_text(url))
    if parsed.scheme not in {"http", "https"}:
        return None
    for segment in reversed([part for part in parsed.path.split("/") if part]):
        slug = re.sub(r"[-_]+", " ", segment)
        candidate = infer_merchant_candidate_from_title(slug.title())
        if candidate:
            return candidate
    return None


def is_dynamic_merchant_label(value: object) -> bool:
    label = clean_text(value)
    if not label or len(re.findall(r"[\w&'.!]+", label, flags=re.UNICODE)) > 3:
        return False
    if LABEL_NOISE_RE.search(label) or re.search(r"[,!?;]", label):
        return False
    if re.match(r"^(?:promo|katalog|diskon|syarat|ketentuan|harga)\b", label, re.I):
        return False
    return any(char.isalpha() for char in label)
