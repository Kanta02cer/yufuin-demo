"""SerpAPI (Google Hotels) による競合価格取得。

Booking.com / Agoda / Expedia などのOTAは、サーバーからのHTML直接取得が
ボット検知で不可（Booking.com=202チャレンジ, Expedia=429）。Google Hotels は
これらOTAの価格を集約しており、SerpAPI 経由で合法的にJSONで取得できる。

エリア検索1回（1課金）で湯布院の全施設×指定1日付が返るため、
「監視日数 = 検索数」で効率的。コスト管理のため SERPAPI_HORIZON_DAYS で
取得する日数を絞る（既定30日）。

環境変数 SERPAPI_KEY 未設定時は {} を返す（安全に無効化）。
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from core import config

API_URL = "https://serpapi.com/search.json"
_REQUEST_INTERVAL_SEC = 1.0
_TIMEOUT_SEC = 30


def _match_hotel_key(property_name: str) -> str | None:
    """Google Hotels の施設名を監視対象の hotel_key にマッチさせる。"""
    if not property_name:
        return None
    for hotel_key, keywords in config.SERPAPI_HOTEL_MATCH.items():
        for kw in keywords:
            if kw.lower() in property_name.lower():
                return hotel_key
    return None


def _extract_rate(prop: dict) -> int | None:
    """property から1泊あたりの数値価格を取り出す。"""
    for field in ("rate_per_night", "total_rate"):
        rate = prop.get(field) or {}
        val = rate.get("extracted_lowest")
        if isinstance(val, (int, float)) and val > 0:
            return int(val)
    return None


def _fetch_day(checkin: date, log) -> dict[str, int]:
    """指定チェックイン日の、湯布院エリア全施設の最安価格を返す。

    戻り値: {hotel_key: price}
    """
    checkout = checkin + timedelta(days=1)
    params = {
        "engine": "google_hotels",
        "q": config.SERPAPI_QUERY,
        "check_in_date": checkin.isoformat(),
        "check_out_date": checkout.isoformat(),
        "adults": 2,
        "currency": "JPY",
        "gl": "jp",
        "hl": "ja",
        "api_key": config.SERPAPI_KEY,
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SEC) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        log.debug("  [serpapi] %s HTTP %s", checkin, e.code)
        return {}
    except Exception as e:
        log.debug("  [serpapi] %s 取得失敗: %s", checkin, e)
        return {}

    if body.get("error"):
        log.warning("  [serpapi] %s APIエラー: %s", checkin, body["error"])
        return {}

    result: dict[str, int] = {}
    for prop in body.get("properties", []):
        hotel_key = _match_hotel_key(prop.get("name", ""))
        if hotel_key is None:
            continue
        rate = _extract_rate(prop)
        if rate is None:
            continue
        # 同施設が複数出た場合は最安を採用
        if hotel_key not in result or rate < result[hotel_key]:
            result[hotel_key] = rate
    return result


def scrape_google_hotels() -> dict[str, dict[str, int]]:
    """Google Hotels(SerpAPI) で監視対象施設の日別価格を取得する。

    戻り値: {hotel_key: {check_date: price}}
    SERPAPI_KEY 未設定時は {} を返す。
    """
    log = config.setup_logging()
    if not config.SERPAPI_KEY:
        log.info("  [serpapi] SERPAPI_KEY 未設定のためスキップ")
        return {}

    today = date.today()
    horizon = config.SERPAPI_HORIZON_DAYS
    log.info("  [serpapi] Google Hotels 取得開始（%d 日分・1日=1検索）", horizon + 1)

    by_hotel: dict[str, dict[str, int]] = {}
    for offset in range(horizon + 1):
        checkin = today + timedelta(days=offset)
        day_prices = _fetch_day(checkin, log)
        for hotel_key, price in day_prices.items():
            by_hotel.setdefault(hotel_key, {})[checkin.isoformat()] = price
        time.sleep(_REQUEST_INTERVAL_SEC)

    total = sum(len(v) for v in by_hotel.values())
    log.info(
        "  [serpapi] 取得完了: %d 施設・合計 %d 日分", len(by_hotel), total
    )
    return by_hotel
