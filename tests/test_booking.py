from scrapers import booking_scraper


def test_match_hotel_key():
    assert booking_scraper._match_hotel_key("ENOWA YUFUIN Hotel") == "enowa_yufuin"
    assert booking_scraper._match_hotel_key("界 由布院") == "kai_yufuin"
    assert booking_scraper._match_hotel_key("Kamenoi Besso") == "kamenoi_bessho"
    assert booking_scraper._match_hotel_key("Some Other Ryokan") is None
    assert booking_scraper._match_hotel_key("") is None


def test_extract_price_from_gross_price():
    prop = {"property": {"priceBreakdown": {"grossPrice": {"value": 81890, "currency": "JPY"}}}}
    assert booking_scraper._extract_price(prop) == 81890


def test_extract_price_fallback_fields():
    assert booking_scraper._extract_price({"property": {"minTotalPrice": 55000}}) == 55000
    assert booking_scraper._extract_price({"minTotalPrice": 42000}) == 42000


def test_extract_price_none_when_missing():
    assert booking_scraper._extract_price({"property": {}}) is None
    assert booking_scraper._extract_price({}) is None


def test_scrape_disabled_without_key(monkeypatch):
    monkeypatch.setattr(booking_scraper.config, "RAPIDAPI_KEY", None)
    assert booking_scraper.scrape_booking() == {}
