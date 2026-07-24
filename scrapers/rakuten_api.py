"""楽天トラベル公式API(VacantHotelSearch) による価格取得。

2026年のインフラ刷新でセキュリティが強化された新仕様に対応:
  - エンドポイント: openapi.rakuten.co.jp/engine/api/...
  - applicationId は「クエリ」、accessKey は「HTTPヘッダ」で送る
  - Origin / Referer ヘッダが Developer Console の Allowed websites と一致必須
    （未一致だと 403 REQUEST_CONTEXT_BODY_HTTP_REFERRER_MISSING）

  実データ検証（本実装時, 実キーで確認）:
    - ENOWA YUFUIN(hotelNo=187963) の実価格取得に成功（例 2026-08-01 ¥81,890/2名）
    - 界由布院・亀の井別荘は楽天トラベルに在庫が無く取得不可（config 参照）

環境変数 RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY 未設定時は {} を返す（安全に無効化）。
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from core import config

API_URL = "https://openapi.rakuten.co.jp/engine/api/Travel/VacantHotelSearch/20170426"

# レート制限対策: 同一URLへの短時間連続アクセスは一時的に弾かれ得るため間隔を空ける
_REQUEST_INTERVAL_SEC = 1.0
_TIMEOUT_SEC = 20


def _min_charge_for_date(hotel_no: int, checkin: date, adult_num: int, log) -> int | None:
    """指定チェックイン日(1泊)の最安料金を返す。空室なし/エラー時は None。"""
    checkout = checkin + timedelta(days=1)
    params = {
        "applicationId": config.RAKUTEN_APP_ID,
        "hotelNo": hotel_no,
        "checkinDate": checkin.isoformat(),
        "checkoutDate": checkout.isoformat(),
        "adultNum": adult_num,
        "format": "json",
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)
    # 2026年新仕様: accessKey はヘッダ、Origin/Referer は登録ドメインと一致必須
    headers = {
        "accessKey": config.RAKUTEN_ACCESS_KEY or "",
        "Origin": config.RAKUTEN_ORIGIN,
        "Referer": config.RAKUTEN_REFERER,
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 404 = 該当日の空室なし（正常系）。それ以外は劣化として記録。
        if e.code != 404:
            log.debug("  [rakuten] %s HTTP %s", checkin, e.code)
        return None
    except Exception as e:
        log.debug("  [rakuten] %s 取得失敗: %s", checkin, e)
        return None

    # 認証エラー等（HTTP 200 で errorのことがある）
    if isinstance(body, dict) and (body.get("error") or body.get("errors")):
        # not_found = 空室なし（正常）。それ以外は警告。
        err = body.get("error") or body.get("errors")
        if err != "not_found":
            log.debug("  [rakuten] %s APIエラー: %s", checkin, err)
        return None

    return _extract_min_charge(body)


def _extract_min_charge(body: dict) -> int | None:
    """VacantHotelSearch レスポンスから最安の総額(total)を抽出する。"""
    hotels = body.get("hotels")
    if not hotels:
        return None
    totals: list[int] = []
    fallbacks: list[int] = []
    for hotel in hotels:
        for entry in hotel.get("hotel", []):
            for room in entry.get("roomInfo") or []:
                daily = room.get("dailyCharge") or {}
                total = daily.get("total")
                if isinstance(total, int) and total > 0:
                    totals.append(total)
                elif isinstance(daily.get("rakutenCharge"), int) and daily["rakutenCharge"] > 0:
                    fallbacks.append(daily["rakutenCharge"])
            basic = entry.get("hotelBasicInfo") or {}
            mc = basic.get("hotelMinCharge")
            if isinstance(mc, int) and mc > 0:
                fallbacks.append(mc)
    if totals:
        return min(totals)
    return min(fallbacks) if fallbacks else None


def scrape_rakuten_hotel(hotel_key: str, adult_num: int = 2) -> dict[str, int]:
    """楽天トラベル公式APIで、今日から HORIZON_DAYS 日先までの日別最安料金を返す。

    RAKUTEN_APP_ID 未設定時は {} を返す（機能を安全に無効化）。
    """
    log = config.setup_logging()

    if not config.RAKUTEN_APP_ID:
        log.info("  [rakuten] RAKUTEN_APP_ID 未設定のためスキップ")
        return {}

    hotel_no = config.RAKUTEN_HOTEL_NOS.get(hotel_key)
    if hotel_no is None:
        log.info("  [rakuten] %s の施設番号未登録のためスキップ", hotel_key)
        return {}

    today = date.today()
    prices: dict[str, int] = {}
    log.info("  [rakuten] hotelNo=%s の価格取得を開始（最大 %d 日）", hotel_no, config.HORIZON_DAYS)

    for offset in range(config.HORIZON_DAYS + 1):
        checkin = today + timedelta(days=offset)
        charge = _min_charge_for_date(hotel_no, checkin, adult_num, log)
        if charge is not None:
            prices[checkin.isoformat()] = charge
        time.sleep(_REQUEST_INTERVAL_SEC)

    log.info("  [rakuten] hotelNo=%s → %d 日分取得", hotel_no, len(prices))
    return prices


def scrape_all_rakuten(adult_num: int = 2) -> dict[str, dict[str, int]]:
    """RAKUTEN_HOTEL_NOS に登録された全施設の日別価格を返す。

    戻り値: {hotel_key: {check_date: price}}
    RAKUTEN_APP_ID 未設定時は {} を返す。
    """
    log = config.setup_logging()
    if not config.RAKUTEN_APP_ID:
        log.info("  [rakuten] RAKUTEN_APP_ID 未設定のためスキップ")
        return {}
    result: dict[str, dict[str, int]] = {}
    for hotel_key in config.RAKUTEN_HOTEL_NOS:
        dates = scrape_rakuten_hotel(hotel_key, adult_num=adult_num)
        if dates:
            result[hotel_key] = dates
    return result
