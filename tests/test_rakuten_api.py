from scrapers import rakuten_api


# VacantHotelSearch レスポンスの実構造を模したフィクスチャ
_SAMPLE = {
    "hotels": [
        {
            "hotel": [
                {"hotelBasicInfo": {"hotelNo": 180627, "hotelMinCharge": 55000}},
                {
                    "roomInfo": [
                        {"roomBasicInfo": {"planName": "スタンダード"}},
                        {"dailyCharge": {"rakutenCharge": 60000, "total": 62000}},
                    ]
                },
                {
                    "roomInfo": [
                        {"roomBasicInfo": {"planName": "特別室"}},
                        {"dailyCharge": {"rakutenCharge": 88000, "total": 90000}},
                    ]
                },
            ]
        }
    ]
}


def test_extract_min_charge_prefers_lowest_total():
    # total を優先し最安を採用（62000 < 90000）。hotelMinCharge(55000)は
    # total が取れる場合はフォールバック扱いで使わない。
    assert rakuten_api._extract_min_charge(_SAMPLE) == 62000


def test_extract_min_charge_empty_when_no_hotels():
    assert rakuten_api._extract_min_charge({"hotels": []}) is None
    assert rakuten_api._extract_min_charge({}) is None


def test_extract_min_charge_uses_daily_when_no_min_charge():
    body = {
        "hotels": [
            {"hotel": [{"roomInfo": [{"dailyCharge": {"total": 71000}}]}]}
        ]
    }
    assert rakuten_api._extract_min_charge(body) == 71000


def test_extract_min_charge_fallback_to_min_charge_when_no_total():
    body = {"hotels": [{"hotel": [{"hotelBasicInfo": {"hotelMinCharge": 48000}}]}]}
    assert rakuten_api._extract_min_charge(body) == 48000


def test_scrape_disabled_without_app_id(monkeypatch):
    monkeypatch.setattr(rakuten_api.config, "RAKUTEN_APP_ID", None)
    assert rakuten_api.scrape_all_rakuten() == {}


def test_scrape_skips_unknown_hotel(monkeypatch):
    monkeypatch.setattr(rakuten_api.config, "RAKUTEN_APP_ID", "dummy")
    monkeypatch.setattr(rakuten_api.config, "RAKUTEN_HOTEL_NOS", {})
    assert rakuten_api.scrape_rakuten_hotel("enowa_yufuin") == {}
