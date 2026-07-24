"""楽天トラベル公式API による価格取得（亀の井別荘の代替ソース）。

一休(ikyu)はボット検知(403)で自動取得できず、楽天トラベルの施設ページHTMLも403で
ブロックされる。一方、楽天トラベルの公式API(VacantHotelSearch)はボット検知がなく、
無料のアプリID(applicationId)だけで日付別の空室・価格JSONを返す。

  検証結果（本モジュール実装時）:
    - openapi.rakuten.co.jp/.../VacantHotelSearch は到達可能
    - hotelNo=180627(亀の井別荘) 実クエリで正規のJSONエラー
      "applicationId must be present" を返す = キーを入れれば取得可能

環境変数 RAKUTEN_APP_ID が未設定の場合は何もせず {} を返す（安全に無効化）。
既存の品質ガード・手動CSV補完と組み合わせて使う。
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from core import config

API_URL = "https://app.rakuten.co.jp/services/api/Travel/VacantHotelSearch/20170426"

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
    if config.RAKUTEN_ACCESS_KEY:
        params["accessKey"] = config.RAKUTEN_ACCESS_KEY

    url = API_URL + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SEC) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 404 = 該当日の空室なし（正常系）。それ以外は劣化として記録。
        if e.code != 404:
            log.debug("  [rakuten] %s HTTP %s", checkin, e.code)
        return None
    except Exception as e:
        log.debug("  [rakuten] %s 取得失敗: %s", checkin, e)
        return None

    return _extract_min_charge(body)


def _extract_min_charge(body: dict) -> int | None:
    """VacantHotelSearch レスポンスから最安料金を抽出する。"""
    hotels = body.get("hotels")
    if not hotels:
        return None
    charges: list[int] = []
    for hotel in hotels:
        # hotels[].hotel[].roomInfo[].dailyCharge.total などにネスト
        for entry in hotel.get("hotel", []):
            room_info = entry.get("roomInfo")
            if not room_info:
                continue
            for room in room_info:
                daily = room.get("dailyCharge") or {}
                for key in ("total", "rakutenCharge"):
                    val = daily.get(key)
                    if isinstance(val, int) and val > 0:
                        charges.append(val)
        # hotelMinCharge（施設単位の最安）もフォールバックに使う
        for entry in hotel.get("hotel", []):
            basic = entry.get("hotelBasicInfo") or {}
            mc = basic.get("hotelMinCharge")
            if isinstance(mc, int) and mc > 0:
                charges.append(mc)
    return min(charges) if charges else None


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


def scrape_rakuten_kamenoi(adult_num: int = 2) -> dict[str, int]:
    """亀の井別荘（楽天トラベル hotelNo=180627）の日別最安料金を返す。"""
    return scrape_rakuten_hotel("kamenoi_bessho", adult_num=adult_num)
