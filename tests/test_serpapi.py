from scrapers import serpapi_hotels


def test_match_hotel_key():
    assert serpapi_hotels._match_hotel_key("界 由布院") == "kai_yufuin"
    assert serpapi_hotels._match_hotel_key("亀の井別荘 別館") == "kamenoi_bessho"
    assert serpapi_hotels._match_hotel_key("ENOWA YUFUIN") == "enowa_yufuin"
    assert serpapi_hotels._match_hotel_key("無関係なホテル") is None
    assert serpapi_hotels._match_hotel_key("") is None


def test_extract_rate_prefers_rate_per_night():
    prop = {
        "rate_per_night": {"lowest": "¥25,000", "extracted_lowest": 25000},
        "total_rate": {"extracted_lowest": 27000},
    }
    assert serpapi_hotels._extract_rate(prop) == 25000


def test_extract_rate_none_when_missing():
    assert serpapi_hotels._extract_rate({}) is None
    assert serpapi_hotels._extract_rate({"rate_per_night": {}}) is None


def test_scrape_disabled_without_key(monkeypatch):
    monkeypatch.setattr(serpapi_hotels.config, "SERPAPI_KEY", None)
    assert serpapi_hotels.scrape_google_hotels() == {}
