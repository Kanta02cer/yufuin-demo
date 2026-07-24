"""Booking.com 価格取得（RapidAPI: booking-com15 経由）。

Booking.com はHTML直接取得がボット検知(202チャレンジ)で不可。RapidAPI の
booking-com15 API 経由でホテル価格をJSONで取得する。標準ライブラリ urllib のみ使用。

正しいホテル取得フロー（/cars/ 系はレンタカー用なので使わない）:
  - searchHotels を施設別 dest_id (config.BOOKING_HOTEL_DEST) + search_type=hotel で
    日付ごとに呼び、返る候補から対象施設を名前照合して価格を抽出する。
  （由布院エリア検索(dest_id=7023)の上位20件には競合が出ないため、施設ごとに
    dest_id を直接指定する方式が確実。）

  実データ検証（実キーで確認）:
    - ENOWA YUFUIN(dest_id=9609444) の実価格取得に成功
      （例 2026-08-01 ¥78,167 / 2026-08-15 ¥136,500, 2名1泊）
    - 界由布院・亀の井別荘は Booking.com に掲載が見つからない（config 参照）

環境変数 RAPIDAPI_KEY 未設定時は {} を返す（安全に無効化）。
戻り値: {hotel_key: {check_date: price}}
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from core import config

_TIMEOUT_SEC = 35
_REQUEST_INTERVAL_SEC = 1.0


def _headers() -> dict:
    return {
        "x-rapidapi-host": config.BOOKING_RAPIDAPI_HOST,
        "x-rapidapi-key": config.RAPIDAPI_KEY or "",
    }


def _get(path: str, params: dict, log):
    """booking-com15 API を GET し、JSON(dict)を返す。失敗時 None。"""
    url = f"https://{config.BOOKING_RAPIDAPI_HOST}/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        log.warning("  [booking] HTTP %s (%s)", e.code, path)
    except Exception as e:
        log.debug("  [booking] 取得失敗 (%s): %s", path, e)
    return None


def _match_hotel_key(name: str) -> str | None:
    if not name:
        return None
    for hotel_key, keywords in config.HOTEL_NAME_MATCH.items():
        for kw in keywords:
            if kw.lower() in name.lower():
                return hotel_key
    return None


def _extract_price(prop: dict) -> int | None:
    """searchHotels の1施設分から総額を取り出す（複数のレスポンス形に対応）。"""
    p = prop.get("property") or prop
    breakdown = (p.get("priceBreakdown") or {}).get("grossPrice") or {}
    for key in ("value", "amountRounded", "amount"):
        v = breakdown.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
    for key in ("minTotalPrice", "price", "totalPrice"):
        v = p.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
    return None


def _price_for_hotel_day(dest_id: int, hotel_key: str, checkin: date, log) -> int | None:
    """施設別 dest_id で1泊分を検索し、対象施設の価格を返す。"""
    checkout = checkin + timedelta(days=1)
    params = {
        "dest_id": dest_id,
        "search_type": "hotel",
        "arrival_date": checkin.isoformat(),
        "departure_date": checkout.isoformat(),
        "adults": 2,
        "room_qty": 1,
        "currency_code": "JPY",
        "languagecode": "ja",
    }
    body = _get("api/v1/hotels/searchHotels", params, log)
    if not body:
        return None
    hotels = (body.get("data") or {}).get("hotels") or []
    for entry in hotels:
        name = (entry.get("property") or {}).get("name") or entry.get("hotel_name") or ""
        # dest_id指定検索は近隣施設も返すため、対象施設名に一致するものだけ採用
        if _match_hotel_key(name) == hotel_key:
            return _extract_price(entry)
    return None


def scrape_booking() -> dict[str, dict[str, int]]:
    """Booking.com(RapidAPI) で監視対象施設の日別価格を取得する。

    戻り値: {hotel_key: {check_date: price}}
    RAPIDAPI_KEY 未設定時は {} を返す。
    """
    log = config.setup_logging()
    if not config.RAPIDAPI_KEY:
        log.info("  [booking] RAPIDAPI_KEY 未設定のためスキップ")
        return {}
    if not config.BOOKING_HOTEL_DEST:
        log.info("  [booking] BOOKING_HOTEL_DEST 未設定のためスキップ")
        return {}

    today = date.today()
    by_hotel: dict[str, dict[str, int]] = {}
    for hotel_key, dest_id in config.BOOKING_HOTEL_DEST.items():
        name = config.HOTEL_NAMES.get(hotel_key, hotel_key)
        log.info("  [booking] %s (dest_id=%s) 取得開始（%d 日分）", name, dest_id, config.BOOKING_HORIZON_DAYS + 1)
        for offset in range(config.BOOKING_HORIZON_DAYS + 1):
            checkin = today + timedelta(days=offset)
            price = _price_for_hotel_day(dest_id, hotel_key, checkin, log)
            if price is not None:
                by_hotel.setdefault(hotel_key, {})[checkin.isoformat()] = price
            time.sleep(_REQUEST_INTERVAL_SEC)
        log.info("  [booking] %s → %d 日分取得", name, len(by_hotel.get(hotel_key, {})))
    return by_hotel
