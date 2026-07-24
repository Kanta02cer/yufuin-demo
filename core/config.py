"""集中設定モジュール。

閾値・施設定義・監視期間・データ品質基準・通知/ログ設定をここに集約する。
環境変数で上書き可能な項目は os.environ 経由で読み込む。
"""
import logging
import os
from pathlib import Path

# ── パス ─────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
DOCS_DIR = ROOT_DIR / "docs"
DEBUG_DIR = DATA_DIR / "debug"

# ── 施設定義（表示名） ───────────────────────────────────────────────
HOTEL_NAMES: dict[str, str] = {
    "kai_yufuin": "界 由布院",
    "kamenoi_bessho": "亀の井別荘",
    "enowa_yufuin": "ENOWA YUFUIN",
}

# レポート列順（表示順を固定する）
HOTEL_ORDER: list[str] = ["kai_yufuin", "kamenoi_bessho", "enowa_yufuin"]

# ── アラート/監視設定 ────────────────────────────────────────────────
def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (ValueError, TypeError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (ValueError, TypeError):
        return default


# 前日比アラート閾値（±5%）
ALERT_THRESHOLD: float = _env_float("ALERT_THRESHOLD", 0.05)

# 監視期間（今日から N 日先まで）
HORIZON_DAYS: int = _env_int("HORIZON_DAYS", 180)

# ── データ品質基準 ───────────────────────────────────────────────────
# 1施設あたり、この件数を下回る取得は「劣化(degraded)」とみなす。
# 180日監視なので、半分未満しか取れなければ何かが壊れていると判断する。
MIN_ROWS_PER_HOTEL: int = _env_int("MIN_ROWS_PER_HOTEL", 30)

# 全施設合計がこの件数以下なら「実行失敗(failed)」とみなし、
# 良データを空データで上書きしない（過去CSVを保護する）。
MIN_TOTAL_ROWS: int = _env_int("MIN_TOTAL_ROWS", 10)

# ── 楽天トラベル公式API（VacantHotelSearch / 2026年新仕様） ──────────
# https://webservice.rakuten.co.jp/ でアプリID + アクセスキーを発行。
# 2026年更新でセキュリティ強化: accessKey を「ヘッダ」で送り、Origin/Referer が
# 登録ドメイン（Developer Console の Allowed websites）と一致する必要がある。
RAKUTEN_APP_ID: str | None = os.environ.get("RAKUTEN_APP_ID") or None
RAKUTEN_ACCESS_KEY: str | None = os.environ.get("RAKUTEN_ACCESS_KEY") or None

# Developer Console の Allowed websites に登録したドメインと一致させること。
# 未一致だと REQUEST_CONTEXT_BODY_HTTP_REFERRER_MISSING で 403 になる。
RAKUTEN_REFERER: str = os.environ.get("RAKUTEN_REFERER", "https://kanta02cer.github.io/")
RAKUTEN_ORIGIN: str = os.environ.get("RAKUTEN_ORIGIN", "https://kanta02cer.github.io")

# 楽天トラベルAPIの hotelNo（KeywordHotelSearch で実在庫を確認済み）。
# 注意: 施設ページURLの HOTEL/NNNNN 番号はAPIのhotelNoとは別物。
#   - ENOWA YUFUIN = 187963（楽天トラベルに在庫あり・確認済み）
#   - 界 由布院 / 亀の井別荘 は楽天トラベルに在庫が無い（掲載なし）ため対象外。
#     → 界=じゃらん、亀の井=一休/手動CSV/SerpAPI で取得する。
RAKUTEN_HOTEL_NOS: dict[str, int] = {
    "enowa_yufuin": 187963,
}

# ── SerpAPI (Google Hotels) ─────────────────────────────────────────
# Booking.com / Agoda / Expedia 等はHTMLを直接取得できない（ボット検知 403/202）。
# Google Hotels を集約する SerpAPI 経由でこれらの価格を合法的に取得する。
# https://serpapi.com/ でAPIキーを取得して設定する（無料枠 月100検索）。
SERPAPI_KEY: str | None = os.environ.get("SERPAPI_KEY") or None

# SerpAPI は1検索=1課金。エリア検索1回で全施設×1日付が取れるため、
# 監視日数=検索数。コスト管理のため既定を短めにする（本日から N 日先まで）。
SERPAPI_HORIZON_DAYS: int = _env_int("SERPAPI_HORIZON_DAYS", 30)

# Google Hotels のエリア検索クエリ（湯布院の競合を一括取得）
SERPAPI_QUERY: str = os.environ.get("SERPAPI_QUERY", "由布院温泉 旅館")

# 施設名 → hotel_key マッチング用キーワード（API結果の施設名に含まれる文字列で判定）
# SerpAPI / Booking(RapidAPI) など、施設名ベースで照合する全ソースで共有する。
HOTEL_NAME_MATCH: dict[str, list[str]] = {
    "kai_yufuin": ["界 由布院", "界由布院", "KAI Yufuin", "Kai Yufuin"],
    "kamenoi_bessho": ["亀の井別荘", "Kamenoi", "Kamenoi Besso"],
    "enowa_yufuin": ["ENOWA", "エノワ"],
}
# 後方互換エイリアス
SERPAPI_HOTEL_MATCH = HOTEL_NAME_MATCH

# ── Booking.com (RapidAPI: booking-com15) ───────────────────────────
# Booking.com はHTML直接取得不可（202チャレンジ）。RapidAPI の booking-com15
# 経由で公式に近いホテル価格をJSONで取得する。https://rapidapi.com/ でキー発行。
# 注意: /cars/ 系はレンタカー用。ホテルは searchDestination→searchHotels を使う。
RAPIDAPI_KEY: str | None = os.environ.get("RAPIDAPI_KEY") or None
BOOKING_RAPIDAPI_HOST: str = os.environ.get(
    "BOOKING_RAPIDAPI_HOST", "booking-com15.p.rapidapi.com"
)
# 1施設×1日付で1検索。監視日数=施設ごとの検索数（コスト管理）
BOOKING_HORIZON_DAYS: int = _env_int("BOOKING_HORIZON_DAYS", 30)

# Booking.com の施設別 dest_id（searchDestination で確認済み）。
# 注意: 由布院エリア検索(dest_id=7023)の上位には競合が出ないため、施設ごとに
# 直接 dest_id を指定して取得する。実キー検証で判明した在庫実態:
#   - ENOWA YUFUIN = 9609444（Booking.comに掲載・実価格取得を確認）
#   - 界由布院・亀の井別荘は Booking.com に掲載が見つからない（Rakuten と同様）
BOOKING_HOTEL_DEST: dict[str, int] = {
    "enowa_yufuin": 9609444,
}

# ── ソース優先度と表示ラベル（複数ソース併用時のマージ順） ───────────
# 前のソースで価格が取れなければ次のソースで補完する。
SOURCE_PRIORITY: list[str] = [
    "booking", "serpapi_google", "rakuten", "jalan", "ikyu", "manual",
]

SOURCE_LABELS: dict[str, str] = {
    "booking": "Booking.com",
    "serpapi_google": "Google/Booking系",
    "rakuten": "楽天",
    "jalan": "じゃらん",
    "ikyu": "一休",
    "manual": "手動",
    "legacy": "旧データ",
}

# ── 通知設定 ─────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL: str | None = os.environ.get("SLACK_WEBHOOK_URL") or None

# ── ログ設定 ─────────────────────────────────────────────────────────
def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """アプリ共通ロガーを初期化して返す。"""
    logger = logging.getLogger("yufuin")
    if logger.handlers:
        return logger
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
    )
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger
