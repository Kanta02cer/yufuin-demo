"""データ品質評価モジュール。

スクレイピング結果の健全性を判定し、以下を可能にする:
  - 空/劣化データで過去の良データを上書きしない（データ破壊の防止）
  - 障害・劣化を検知して通知に回す（サイレント障害の防止）
  - レポートに施設別のデータ健全性を表示する
"""
from dataclasses import dataclass, field

from core import config


@dataclass
class HotelStatus:
    hotel_key: str
    hotel_name: str
    row_count: int
    status: str  # "ok" | "degraded" | "empty"


@dataclass
class RunHealth:
    total_rows: int
    hotels: list[HotelStatus] = field(default_factory=list)
    # 実行全体の判定: "ok" | "degraded" | "failed"
    verdict: str = "ok"

    @property
    def is_failed(self) -> bool:
        return self.verdict == "failed"

    @property
    def is_healthy(self) -> bool:
        return self.verdict == "ok"

    def problems(self) -> list[HotelStatus]:
        """ok 以外の施設を返す（通知用）。"""
        return [h for h in self.hotels if h.status != "ok"]


def _hotel_status(row_count: int) -> str:
    if row_count == 0:
        return "empty"
    if row_count < config.MIN_ROWS_PER_HOTEL:
        return "degraded"
    return "ok"


def assess(prices_by_hotel: dict[str, dict]) -> RunHealth:
    """取得結果全体の健全性を評価する。

    prices_by_hotel: {hotel_key: {check_date: price|None}}
    None 価格は「取得できなかった」扱いで件数に含めない。
    """
    hotels: list[HotelStatus] = []
    total = 0
    for hotel_key in config.HOTEL_ORDER:
        dates = prices_by_hotel.get(hotel_key, {})
        count = sum(1 for v in dates.values() if v is not None)
        total += count
        hotels.append(
            HotelStatus(
                hotel_key=hotel_key,
                hotel_name=config.HOTEL_NAMES.get(hotel_key, hotel_key),
                row_count=count,
                status=_hotel_status(count),
            )
        )

    # 監視対象なのに結果 dict に存在すらしない施設も empty として計上
    for hotel_key, dates in prices_by_hotel.items():
        if hotel_key not in config.HOTEL_ORDER:
            count = sum(1 for v in dates.values() if v is not None)
            total += count
            hotels.append(
                HotelStatus(
                    hotel_key=hotel_key,
                    hotel_name=config.HOTEL_NAMES.get(hotel_key, hotel_key),
                    row_count=count,
                    status=_hotel_status(count),
                )
            )

    if total <= config.MIN_TOTAL_ROWS:
        verdict = "failed"
    elif any(h.status != "ok" for h in hotels):
        verdict = "degraded"
    else:
        verdict = "ok"

    return RunHealth(total_rows=total, hotels=hotels, verdict=verdict)
