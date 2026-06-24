import csv
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
ALERT_THRESHOLD = 0.05

HOTEL_NAMES = {
    "kai_yufuin": "界 由布院",
    "kamenoi_bessho": "亀の井別荘",
    "enowa_yufuin": "ENOWA YUFUIN",
}


def load_prices(csv_path: Path) -> dict[str, dict[str, int]]:
    prices: dict[str, dict[str, int]] = {}
    if not csv_path or not csv_path.exists():
        return prices
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            hotel = row["hotel_key"]
            if row["price"]:
                prices.setdefault(hotel, {})[row["check_date"]] = int(row["price"])
    return prices


def save_prices(prices_by_hotel: dict[str, dict], run_date: str) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    csv_path = DATA_DIR / f"prices_{run_date}.csv"
    rows = []
    for hotel_key, dates in prices_by_hotel.items():
        for check_date, price in sorted(dates.items()):
            rows.append(
                {
                    "run_date": run_date,
                    "hotel_key": hotel_key,
                    "check_date": check_date,
                    "price": price if price is not None else "",
                }
            )
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["run_date", "hotel_key", "check_date", "price"]
        )
        writer.writeheader()
        writer.writerows(rows)
    return csv_path


def find_previous_csv(exclude_date: str) -> Path | None:
    csvs = sorted(
        [p for p in DATA_DIR.glob("prices_*.csv") if exclude_date not in p.name],
        reverse=True,
    )
    return csvs[0] if csvs else None


def detect_changes(
    today_prices: dict[str, dict[str, int]],
    prev_prices: dict[str, dict[str, int]],
) -> list[dict]:
    changes = []
    for hotel_key, dates in today_prices.items():
        prev_hotel = prev_prices.get(hotel_key, {})
        for check_date, today_price in dates.items():
            if today_price is None:
                continue
            prev_price = prev_hotel.get(check_date)
            if prev_price is None:
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
