import csv
from pathlib import Path

from core import config

DATA_DIR = config.DATA_DIR
ALERT_THRESHOLD = config.ALERT_THRESHOLD
HOTEL_NAMES = config.HOTEL_NAMES


def load_prices(csv_path: Path) -> dict[str, dict[str, int]]:
    """{hotel_key: {check_date: price}} を返す（表示用のプライマリ価格）。

    `source` 列があってもプライマリ価格のみを返す（後方互換）。
    """
    prices, _ = load_prices_with_source(csv_path)
    return prices


def load_prices_with_source(
    csv_path: Path,
) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, str]]]:
    """(price_map, source_map) を返す。

    price_map:  {hotel_key: {check_date: price}}
    source_map: {hotel_key: {check_date: source}}
    `source` 列が無い旧CSVは source="legacy" とする（後方互換）。
    """
    prices: dict[str, dict[str, int]] = {}
    sources: dict[str, dict[str, str]] = {}
    if not csv_path or not csv_path.exists():
        return prices, sources
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            hotel = row["hotel_key"]
            if row.get("price"):
                cd = row["check_date"]
                prices.setdefault(hotel, {})[cd] = int(row["price"])
                sources.setdefault(hotel, {})[cd] = row.get("source") or "legacy"
    return prices, sources


def save_prices(
    prices_by_hotel: dict[str, dict],
    run_date: str,
    source_by_hotel: dict[str, dict] | None = None,
) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    csv_path = DATA_DIR / f"prices_{run_date}.csv"
    source_by_hotel = source_by_hotel or {}
    rows = []
    for hotel_key, dates in prices_by_hotel.items():
        hotel_sources = source_by_hotel.get(hotel_key, {})
        for check_date, price in sorted(dates.items()):
            rows.append(
                {
                    "run_date": run_date,
                    "hotel_key": hotel_key,
                    "check_date": check_date,
                    "price": price if price is not None else "",
                    "source": hotel_sources.get(check_date, ""),
                }
            )
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["run_date", "hotel_key", "check_date", "price", "source"]
        )
        writer.writeheader()
        writer.writerows(rows)
    return csv_path


def merge_sources(
    by_source: dict[str, dict[str, dict[str, int]]],
) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, str]]]:
    """複数ソースの価格を優先度順にマージする。

    by_source: {hotel_key: {source: {check_date: price}}}
    戻り値: (price_map, source_map)
      price_map[hotel][date]  = 採用した価格（優先度の高いソース優先）
      source_map[hotel][date] = 採用したソース名
    """
    price_map: dict[str, dict[str, int]] = {}
    source_map: dict[str, dict[str, str]] = {}
    for hotel_key, sources in by_source.items():
        for source in config.SOURCE_PRIORITY:
            dates = sources.get(source)
            if not dates:
                continue
            for check_date, price in dates.items():
                if price is None:
                    continue
                # 既に高優先ソースで採用済みの日付は上書きしない
                if check_date in price_map.get(hotel_key, {}):
                    continue
                price_map.setdefault(hotel_key, {})[check_date] = price
                source_map.setdefault(hotel_key, {})[check_date] = source
        # SOURCE_PRIORITY に無い未知ソースも拾う（末尾扱い）
        for source, dates in sources.items():
            if source in config.SOURCE_PRIORITY:
                continue
            for check_date, price in (dates or {}).items():
                if price is None or check_date in price_map.get(hotel_key, {}):
                    continue
                price_map.setdefault(hotel_key, {})[check_date] = price
                source_map.setdefault(hotel_key, {})[check_date] = source
    return price_map, source_map


def _has_data(csv_path: Path) -> bool:
    """CSVがヘッダのみ（データ0行）でないかを判定する。"""
    prices = load_prices(csv_path)
    return any(dates for dates in prices.values())


def find_previous_csv(exclude_date: str) -> Path | None:
    """比較対象となる直近の「データが入った」CSVを返す。

    空(ヘッダのみ)のCSVはスキップする。全施設ゼロ件だった障害日を
    「前日」として選んでしまい、変動検出が機能しなくなるのを防ぐ。
    """
    csvs = sorted(
        [p for p in DATA_DIR.glob("prices_*.csv") if exclude_date not in p.name],
        reverse=True,
    )
    for csv_path in csvs:
        if _has_data(csv_path):
            return csv_path
    return None


def select_baseline_csv(run_date: str) -> Path | None:
    """比較の基準となるCSVを返す。

    短間隔ポーリング対応: 同日に既にデータ入りの取得があればそれを基準に
    「前回取得比」を出す。無ければ前日以前の直近データCSVにフォールバックする。
    """
    today_file = DATA_DIR / f"prices_{run_date}.csv"
    if today_file.exists() and _has_data(today_file):
        return today_file
    return find_previous_csv(exclude_date=run_date)


def detect_changes(
    today_prices: dict[str, dict[str, int]],
    prev_prices: dict[str, dict[str, int]],
    today_sources: dict[str, dict[str, str]] | None = None,
    prev_sources: dict[str, dict[str, str]] | None = None,
) -> list[dict]:
    """前回比の価格変動を検出する。

    today_sources / prev_sources を渡すと、同一日付でソースが変わった場合は
    比較をスキップする（例: 前回=楽天, 今回=Booking系 の価格差を「変動」と
    誤検出しないため）。複数ソース併用時の誤アラート防止。
    """
    changes = []
    for hotel_key, dates in today_prices.items():
        prev_hotel = prev_prices.get(hotel_key, {})
        for check_date, today_price in dates.items():
            if today_price is None:
                continue
            prev_price = prev_hotel.get(check_date)
            if prev_price is None:
                continue
            # ソース情報があり、前回と今回でソースが異なる場合は比較不能として除外
            if today_sources is not None and prev_sources is not None:
                ts = today_sources.get(hotel_key, {}).get(check_date)
                ps = prev_sources.get(hotel_key, {}).get(check_date)
                if ts and ps and ts != ps:
                    continue
            change_rate = (today_price - prev_price) / prev_price
            if abs(change_rate) >= ALERT_THRESHOLD:
                changes.append(
                    {
                        "hotel_key": hotel_key,
                        "hotel_name": HOTEL_NAMES.get(hotel_key, hotel_key),
                        "check_date": check_date,
                        "prev_price": prev_price,
                        "today_price": today_price,
                        "change_rate": change_rate,
                        "direction": "up" if change_rate > 0 else "down",
                    }
                )
    changes.sort(key=lambda c: (c["check_date"], c["hotel_key"]))
    return changes
