"""Grouped regression tests. Cases are organized by functional area."""



from __future__ import annotations

import sys

from pathlib import Path

import requests

import promo_multisource_collector as collector

from bs4 import BeautifulSoup

from enrich_existing_promo_catalog_multisource import (
    make_clean_row, make_simple_excel_row, preferred_source_url,
)



# --- from test_access_limits.py ---
ENGINE_DIR = Path(__file__).resolve().parents[1] / "src"

# --- from test_access_limits.py ---
sys.path.insert(0, str(ENGINE_DIR))

# --- from test_access_limits.py ---
class FakeResponse:
    def __init__(self, url: str, status_code: int, final_url: str | None = None):
        self.url = final_url or url
        self.status_code = status_code
        self.headers = {"Content-Type": "text/html"}
        self.text = "<html><body>test</body></html>"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

# --- from test_access_limits.py ---
class FakeSession:
    def __init__(self, status_code: int = 200, final_url: str | None = None):
        self.status_code = status_code
        self.final_url = final_url
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        return FakeResponse(url, self.status_code, self.final_url)

# --- from test_access_limits.py ---
class TimeoutSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        raise requests.Timeout("simulated timeout")

# --- from test_access_limits.py ---
def test_collector_stops_source_after_http_429(monkeypatch):
    monkeypatch.setattr(collector.time, "sleep", lambda _seconds: None)
    session = FakeSession(429)
    products, articles, images, request_log = collector.run_source(session, "Hemat.id")
    assert len(session.calls) == 1
    assert products == []
    assert images == []
    assert request_log[0]["status"] == "blocked_or_limited"

# --- from test_access_limits.py ---
def test_collector_stops_after_request_timeout(monkeypatch):
    monkeypatch.setattr(collector.time, "sleep", lambda _seconds: None)
    session = TimeoutSession()
    products, articles, images, request_log = collector.run_source(session, "Hemat.id")
    assert len(session.calls) == 1
    assert products == []
    assert images == []
    assert request_log[0]["status"] == "request_error"

# --- from test_access_limits.py ---
def test_collector_rejects_cross_site_redirect(monkeypatch):
    monkeypatch.setattr(collector.time, "sleep", lambda _seconds: None)
    session = FakeSession(200, "https://unrelated.example.net/redirect")
    products, articles, images, request_log = collector.run_source(session, "Hemat.id")
    assert len(session.calls) == 1
    assert products == []
    assert request_log[0]["status"] == "redirected_offsite"

# --- from test_access_limits.py ---
def test_article_404_is_url_level_failure_and_other_articles_continue(monkeypatch):
    from bs4 import BeautifulSoup

    listing_url = "https://katalogpromosi.com/"
    dead_url = "https://katalogpromosi.com/promo-deleted/"
    good_url = "https://katalogpromosi.com/promo-live/"

    class RouteResponse:
        def __init__(self, url, status_code, body=""):
            self.url = url
            self.status_code = status_code
            self.headers = {"Content-Type": "text/html; charset=utf-8"}
            self.text = body

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"HTTP {self.status_code}")

    class RouterSession:
        def __init__(self):
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append(url)
            if url == listing_url:
                body = (
                    '<html><body><a href="/promo-deleted/">Promo yang sudah dihapus</a>'
                    '<a href="/promo-live/">Promo aktif 23-25 Oktober 2026</a></body></html>'
                )
                return RouteResponse(url, 200, body)
            if url == dead_url:
                return RouteResponse(url, 404, "")
            if url == good_url:
                return RouteResponse(url, 200, "<html><body><h1>Promo Produk 23-25 Oktober 2026</h1><p>Penawaran</p></body></html>")
            raise AssertionError(f"Unexpected request: {url}")

    monkeypatch.setattr(collector.time, "sleep", lambda _seconds: None)
    monkeypatch.setitem(collector.SOURCE_SEEDS, "Katalogpromosi.com", [listing_url])
    monkeypatch.setattr(
        collector,
        "is_article_candidate",
        lambda _source, target, _title: target in {dead_url, good_url},
    )
    monkeypatch.setattr(collector, "title_from_page", lambda _soup, fallback="": fallback or "Promo Produk 23-25 Oktober 2026")
    monkeypatch.setattr(collector, "find_article_container", lambda soup: soup)
    monkeypatch.setattr(collector, "published_from_page", lambda _soup: None)
    monkeypatch.setattr(collector, "infer_merchant_dynamic", lambda *_args, **_kwargs: "Indomaret")
    monkeypatch.setattr(
        collector,
        "extract_article_rows",
        lambda _container, source_name, _title, final_url, _period, published_at=None: (
            [{"source_name": source_name, "product_text": "Contoh Produk 100 g", "source_url": final_url}]
            if final_url == good_url else []
        ),
    )
    monkeypatch.setattr(collector, "image_rows_from_article", lambda *_args, **_kwargs: [])

    products, articles, images, request_log = collector.run_source(RouterSession(), "Katalogpromosi.com")

    assert [row["source_url"] for row in products] == [good_url]
    assert images == []
    assert len(articles) == 2
    assert any(item.get("url") == dead_url and item.get("status") == "not_found" for item in request_log)
    assert any(item.get("url") == good_url and item.get("status") == "ok" for item in request_log)

# --- from test_access_limits.py ---
def test_fetch_404_is_not_misclassified_as_source_outage():
    session = FakeSession(404)
    soup, info = collector.fetch_page(session, "https://www.hemat.id/article-deleted/", "Hemat.id")
    assert soup is None
    assert info["status"] == "not_found"
    assert "URL tidak ditemukan" in info["error"]

# --- from test_hemat_source_routing.py ---
def test_hemat_seed_pages_are_single_retailer_catalogues():
    urls = collector.SOURCE_SEEDS["Hemat.id"]
    assert len(urls) == 7
    assert all("," not in url for url in urls)
    assert {url.rstrip("/").rsplit("-", 1)[-1] for url in urls} == {
        "alfamart", "indomaret", "alfamidi", "superindo", "hypermart", "yogya", "top"
    }

# --- from test_hemat_source_routing.py ---
def test_hemat_listing_discovery_rejects_multi_retailer_comparison_urls():
    assert collector.is_listing_link(
        "Hemat.id", "https://www.hemat.id/katalog-yogya/", "Yogya"
    )
    assert collector.is_listing_link(
        "Hemat.id", "https://www.hemat.id/katalog-alfamart/promo-promo/", "Promo JSM Alfamart"
    )
    for retailer_pair in ("alfamart,yogya", "alfamart,superindo", "alfamart,indomaret"):
        assert not collector.is_listing_link(
            "Hemat.id", f"https://www.hemat.id/katalog-{retailer_pair}/", "Bandingkan katalog"
        )

# --- from test_hemat_source_routing.py ---
def test_hemat_discovery_only_follows_supported_single_retailer_slugs():
    assert collector.is_listing_link(
        "Hemat.id", "https://www.hemat.id/katalog-alfamidi/", "Alfamidi"
    )
    assert not collector.is_listing_link(
        "Hemat.id", "https://www.hemat.id/katalog-transmart/", "Transmart"
    )

# --- from test_scraper_images.py ---
def test_scraper_records_poster_image_url_and_metadata_without_reading_image():
    html = '''
    <article>
      <img data-src="/promos/poster.jpg" alt="Katalog promo mingguan" width="640">
      <img src="data:image/png;base64,ignored" alt="inline image">
      <img src="/icons/icon.png" alt="small icon" width="40">
    </article>
    '''
    article = BeautifulSoup(html, "html.parser").article

    rows = collector.image_rows_from_article(
        article,
        source_name="Katalogpromosi.com",
        title="Promo Mingguan",
        article_url="https://example.test/artikel/promo",
        period_status="active",
    )

    assert len(rows) == 1
    assert rows[0]["image_url"] == "https://example.test/promos/poster.jpg"
    assert rows[0]["image_alt"] == "Katalog promo mingguan"
    assert rows[0]["source_name"] == "Katalogpromosi.com"
    assert rows[0]["article_url"] == "https://example.test/artikel/promo"
    assert "ocr" not in rows[0]

# --- from test_source_url_display.py ---
def test_hemat_catalog_prefers_specific_product_detail_url():
    row = {
        "source_name": "Hemat.id",
        "merchant_name": "Alfamart",
        "source_url": "https://www.hemat.id/katalog-alfamart,yogya/",
        "source_page_url": "https://www.hemat.id/katalog-alfamart,yogya/",
        "source_item_url": "https://www.hemat.id/harga/sania-beras-premium-5-kg/",
    }
    assert preferred_source_url(row) == row["source_item_url"]

# --- from test_source_url_display.py ---
def test_legacy_hemat_comparison_page_falls_back_to_single_retailer_catalog():
    row = {
        "source_name": "Hemat.id",
        "merchant_name": "Yogya",
        "source_url": "https://www.hemat.id/katalog-alfamart,yogya/",
        "source_page_url": "https://www.hemat.id/katalog-alfamart,yogya/",
        "source_item_url": "https://www.hemat.id/katalog//",
    }
    assert preferred_source_url(row) == "https://www.hemat.id/katalog-yogya/"

# --- from test_source_url_display.py ---
def test_unknown_merchant_keeps_exact_original_source_url():
    row = {
        "source_name": "Hemat.id",
        "merchant_name": "Unknown Retailer",
        "source_url": "https://www.hemat.id/katalog-alfamart,unknown-retailer/",
        "source_item_url": "https://www.hemat.id/katalog//",
    }
    assert preferred_source_url(row) == row["source_url"]

# --- from test_source_url_display.py ---
def test_non_hemat_source_keeps_article_url_when_no_item_url():
    row = {
        "source_name": "Katalogpromosi.com",
        "source_url": "https://katalogpromosi.com/promo-mingguan/",
        "source_page_url": "https://katalogpromosi.com/promo-mingguan/",
        "source_item_url": "",
    }
    assert preferred_source_url(row) == row["source_url"]

# --- from test_source_url_display.py ---
def test_clean_catalog_and_simple_workbook_use_preferred_source_url():
    row = {
        "source_name": "Hemat.id",
        "merchant_name": "Alfamart",
        "source_url": "https://www.hemat.id/katalog-alfamart,indomaret/",
        "source_page_url": "https://www.hemat.id/katalog-alfamart,indomaret/",
        "source_item_url": "https://www.hemat.id/harga/produk-contoh/",
        "product_text": "Produk Contoh 100 g",
        "promo_status": "active",
    }
    clean = make_clean_row(row)
    simple = make_simple_excel_row(row)
    assert clean["Sumber URL"] == row["source_item_url"]
    assert simple["Sumber URL"] == row["source_item_url"]

# --- from test_source_url_display.py ---
def test_hemat_category_item_url_is_more_specific_than_comparison_page():
    row = {
        "source_name": "Hemat.id",
        "merchant_name": "AEON",
        "source_url": "https://www.hemat.id/katalog-alfamart,courts/",
        "source_item_url": "https://www.hemat.id/katalog/biore.pembersih-penyegar-wajah/",
    }
    assert preferred_source_url(row) == row["source_item_url"]

# --- from test_source_url_display.py ---
def test_hemat_legacy_hyphenated_price_detail_url_is_preferred():
    row = {
        "source_name": "Hemat.id",
        "merchant_name": "Lotte Mart",
        "source_url": "https://www.hemat.id/katalog-alfamart,lottemart/",
        "source_item_url": "https://www.hemat.id/harga-choice-l-tisu-wajah-2ply-200-pcs-2ply-lottemart-1129598/",
    }
    assert preferred_source_url(row) == row["source_item_url"]
