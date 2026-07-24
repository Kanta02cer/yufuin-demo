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

# ── 楽天トラベル公式API（亀の井別荘の代替ソース） ───────────────────
# 一休(ikyu)はボット検知(403)で取得不可。楽天トラベルの施設ページHTMLも403だが、
# 公式API(VacantHotelSearch)はボット検知なしでJSONを返す。
# https://webservice.rakuten.co.jp/ で無料のアプリID(applicationId)を発行して設定する。
RAKUTEN_APP_ID: str | None = os.environ.get("RAKUTEN_APP_ID") or None
RAKUTEN_ACCESS_KEY: str | None = os.environ.get("RAKUTEN_ACCESS_KEY") or None

# 楽天トラベルの施設番号（WebSearch/KeywordHotelSearch で確認済み）
RAKUTEN_HOTEL_NOS: dict[str, int] = {
    "kamenoi_bessho": 180627,  # 亀の井別荘
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
