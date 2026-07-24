"""Booking.com 価格取得（RapidAPI: booking-com15 経由）。

Booking.com はHTML直接取得がボット検知(202チャレンジ)で不可。RapidAPI の
booking-com15 API 経由でホテル価格をJSONで取得する。標準ライブラリ urllib のみ使用。

正しいホテル取得フロー（/cars/ 系はレンタカー用なので使わない）:
  1. searchDestination で由布院の dest_id を取得（1回だけ）
  2. searchHotels を日付ごとに呼び、返る施設群から監視対象を名前照合で抽出

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

_TIMEOUT_SEC = 30
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


def _resolve_dest_id(log) -> tuple[str | None, str | None]:
    """由布院の dest_id と search_type を取得する。"""
    body = _get("api/v1/hotels/searchDestination", {"query": config.BOOKING_QUERY}, log)
    if not body:
        return None, None
    items = body.get("data") or []
    for item in items:
        # 市区町村レベルを優先
        dest_id = item.get("dest_id")
        search_type = item.get("search_type") or item.get("dest_type")
        if dest_id:
            return str(dest_id), (search_type or "CITY").upper()
    return None, None


def _extract_price(prop: dict) -> int | None:
    """searchHotels の1施設分から総額を取り出す（複数のレスポンス形に対応）。"""
    # よくある構造: property.priceBreakdown.grossPrice.value
    p = prop.get("property") or prop
    breakdown = (p.get("priceBreakdown") or {}).get("grossPrice") or {}
    for key in ("value", "amountRounded", "amount"):
        v = breakdown.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
    # 別形: composite price / min price
    for key in ("minTotalPrice", "price", "totalPrice"):
        v = p.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
    return None


def _fetch_day(dest_id: str, search_type: str, checkin: date, log) -> dict[str, int]:
    checkout = checkin + timedelta(days=1)
    params = {
        "dest_id": dest_id,
        "search_type": search_type,
        "arrival_date": checkin.isoformat(),
        "departure_date": checkout.isoformat(),
        "adults": 2,
        "room_qty": 1,
        "currency_code": "JPY",
        "languagecode": "ja",
    }
    body = _get("api/v1/hotels/searchHotels", params, log)
    if not body:
        return {}
    hotels = (body.get("data") or {}).get("hotels") or []
    result: dict[str, int] = {}
    for entry in hotels:
        name = (entry.get("property") or {}).get("name") or entry.get("hotel_name") or ""
        hotel_key = _match_hotel_key(name)
        if hotel_key is None:
            continue
        price = _extract_price(entry)
        if price is None:
            continue
        if hotel_key not in result or price < result[hotel_key]:
            result[hotel_key] = price
    return result


def scrape_booking() -> dict[str, dict[str, int]]:
    """Booking.com(RapidAPI) で監視対象施設の日別価格を取得する。

    戻り値: {hotel_key: {check_date: price}}
    RAPIDAPI_KEY 未設定時は {} を返す。
    """
    log = config.setup_logging()
    if not config.RAPIDAPI_KEY:
        log.info("  [booking] RAPIDAPI_KEY 未設定のためスキップ")
        return {}

    dest_id, search_type = _resolve_dest_id(log)
    if not dest_id:
        log.warning("  [booking] 由布院の dest_id を取得できませんでした")
        return {}
    log.info("  [booking] dest_id=%s (%s) で取得開始（%d 日分）", dest_id, search_type, config.BOOKING_HORIZON_DAYS + 1)

    today = date.today()
    by_hotel: dict[str, dict[str, int]] = {}
    for offset in range(config.BOOKING_HORIZON_DAYS + 1):
        checkin = today + timedelta(days=offset)
        for hotel_key, price in _fetch_day(dest_id, search_type, checkin, log).items():
            by_hotel.setdefault(hotel_key, {})[checkin.isoformat()] = price
        time.sleep(_REQUEST_INTERVAL_SEC)

    total = sum(len(v) for v in by_hotel.values())
    log.info("  [booking] 取得完了: %d 施設・合計 %d 日分", len(by_hotel), total)
    return by_hotel
