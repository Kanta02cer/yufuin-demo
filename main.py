import asyncio
import sys
from datetime import date

from scrapers.jalan_scraper import scrape_jalan_hotel
from scrapers.ikyu_scraper import scrape_ikyu_kamenoi
from core.compare import save_prices, find_previous_csv, load_prices, detect_changes
from core.report import generate_report
from core.notify import send_slack_alert


async def main():
    run_date = date.today().isoformat()
    print(f"[{run_date}] 価格取得開始")

    today_prices: dict[str, dict] = {}

    for hotel_key, label in [
        ("kai_yufuin", "界 由布院"),
        ("enowa_yufuin", "ENOWA YUFUIN"),
    ]:
        print(f"{label} 取得中...")
        try:
            today_prices[hotel_key] = await scrape_jalan_hotel(hotel_key)
            print(f"  → {len(today_prices[hotel_key])} 日分取得")
        except Exception as e:
            print(f"  → ERROR: {e}", file=sys.stderr)
            today_prices[hotel_key] = {}

    print("亀の井別荘 取得中...")
    try:
        today_prices["kamenoi_bessho"] = await scrape_ikyu_kamenoi()
        print(f"  → {len(today_prices['kamenoi_bessho'])} 日分取得")
    except Exception as e:
        print(f"  → ERROR: {e}", file=sys.stderr)
        today_prices["kamenoi_bessho"] = {}

    csv_path = save_prices(today_prices, run_date)
    print(f"CSV 保存: {csv_path}")

    prev_csv = find_previous_csv(exclude_date=run_date)
    prev_prices = load_prices(prev_csv) if prev_csv else {}

    changes = detect_changes(today_prices, prev_prices)
    print(f"変動検出: {len(changes)} 件（±5%以上）")

    report_path = generate_report(today_prices, prev_prices, changes, run_date)
    print(f"レポート生成: {report_path}")

    send_slack_alert(changes, run_date)
    if changes:
        print(f"Slack通知: {len(changes)} 件送信")


if __name__ == "__main__":
    asyncio.run(main())
