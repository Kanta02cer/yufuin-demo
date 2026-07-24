import asyncio
import sys
from datetime import date

from scrapers.jalan_scraper import scrape_jalan_hotel
from scrapers.ikyu_scraper import scrape_ikyu_kamenoi, load_kamenoi_manual
from scrapers.rakuten_api import scrape_rakuten_kamenoi
from scrapers.serpapi_hotels import scrape_google_hotels
from core import config, quality
from core.compare import (
    save_prices,
    select_baseline_csv,
    load_prices_with_source,
    detect_changes,
    merge_sources,
)
from core.report import generate_report
from core.notify import send_slack_alert, send_health_alert

log = config.setup_logging()


async def collect_by_source() -> dict[str, dict[str, dict[str, int]]]:
    """全ソースから価格を取得する。

    戻り値: {hotel_key: {source: {check_date: price}}}
    個別ソースの失敗は握りつぶし、取れたものだけ返す。
    """
    by_source: dict[str, dict[str, dict[str, int]]] = {}

    def add(hotel_key: str, source: str, dates: dict[str, int]):
        if dates:
            by_source.setdefault(hotel_key, {})[source] = dates

    # ── じゃらん（界由布院 / ENOWA）──────────────────────────────────
    for hotel_key, label in [("kai_yufuin", "界 由布院"), ("enowa_yufuin", "ENOWA YUFUIN")]:
        log.info("%s 取得中（じゃらん）...", label)
        try:
            dates = await scrape_jalan_hotel(hotel_key)
            add(hotel_key, "jalan", dates)
            log.info("  → jalan %d 日分", len(dates))
        except Exception as e:
            log.error("  → %s じゃらん取得失敗: %s", label, e)

    # ── 亀の井別荘（楽天API → 一休 → 手動CSV）───────────────────────
    log.info("亀の井別荘 取得中...")
    try:
        rakuten = await asyncio.to_thread(scrape_rakuten_kamenoi)
        add("kamenoi_bessho", "rakuten", rakuten)
        log.info("  → 楽天API %d 日分", len(rakuten))
        if not rakuten:
            log.info("  → 楽天API未取得、一休スクレイパにフォールバック")
            ikyu = await scrape_ikyu_kamenoi()
            add("kamenoi_bessho", "ikyu", ikyu)
            log.info("  → 一休 %d 日分", len(ikyu))
        manual = load_kamenoi_manual()
        add("kamenoi_bessho", "manual", manual)
    except Exception as e:
        log.error("  → 亀の井別荘 取得失敗: %s", e)

    # ── SerpAPI (Google Hotels: Booking/Agoda/Expedia 集約) ─────────
    log.info("Google Hotels 取得中（SerpAPI）...")
    try:
        google = await asyncio.to_thread(scrape_google_hotels)
        for hotel_key, dates in google.items():
            add(hotel_key, "serpapi_google", dates)
    except Exception as e:
        log.error("  → SerpAPI 取得失敗: %s", e)

    return by_source


async def main() -> int:
    run_date = date.today().isoformat()
    log.info("[%s] 価格取得開始", run_date)

    by_source = await collect_by_source()

    # ── 複数ソースを優先度順にマージ（プライマリ価格 + 採用ソース）─────
    today_prices, today_sources = merge_sources(by_source)
    for hotel_key, sources in by_source.items():
        detail = ", ".join(f"{s}:{len(d)}" for s, d in sources.items())
        log.info("  %s ソース内訳: %s", config.HOTEL_NAMES.get(hotel_key, hotel_key), detail)

    # ── データ品質評価（サイレント障害/データ破壊の防止） ──────────────
    health = quality.assess(today_prices)
    log.info("データ健全性: %s（合計 %d 件）", health.verdict.upper(), health.total_rows)
    for h in health.hotels:
        log.info("  %s: %d 件 [%s]", h.hotel_name, h.row_count, h.status)

    # 比較対象: 同日の前回ポーリング → 無ければ前日以前の直近データCSV
    prev_csv = select_baseline_csv(run_date)
    prev_prices, prev_sources = load_prices_with_source(prev_csv) if prev_csv else ({}, {})
    if prev_csv:
        log.info("前回比較対象: %s", prev_csv.name)

    if health.is_failed:
        # 取得ほぼ全滅。過去の良データを空データで上書きしない。
        log.error(
            "取得失敗と判定（合計 %d 件 ≤ %d）。CSV書き込みをスキップし前回データを保護します。",
            health.total_rows,
            config.MIN_TOTAL_ROWS,
        )
        report_path = generate_report(
            prev_prices, prev_prices, [], run_date, health, prev_sources
        )
        log.info("レポート生成（前回データ表示）: %s", report_path)
        send_health_alert(health, run_date)
        return 1

    # ── 正常/劣化: 保存して比較 ──────────────────────────────────────
    csv_path = save_prices(today_prices, run_date, today_sources)
    log.info("CSV 保存: %s", csv_path)

    changes = detect_changes(today_prices, prev_prices, today_sources, prev_sources)
    log.info("変動検出: %d 件（前回比 ±%.0f%%以上）", len(changes), config.ALERT_THRESHOLD * 100)

    report_path = generate_report(
        today_prices, prev_prices, changes, run_date, health, today_sources
    )
    log.info("レポート生成: %s", report_path)

    send_slack_alert(changes, run_date)
    if changes:
        log.info("Slack通知: %d 件送信", len(changes))

    if health.verdict == "degraded":
        send_health_alert(health, run_date)
        log.warning("データ劣化を通知しました。")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
