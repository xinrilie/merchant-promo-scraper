from bs4 import BeautifulSoup

import promo_multisource_collector as collector


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
