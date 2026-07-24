import asyncio
import sys
from datetime import date

from scrapers.jalan_scraper import scrape_jalan_hotel
from scrapers.ikyu_scraper import scrape_ikyu_kamenoi, load_kamenoi_manual
from scrapers.rakuten_api import scrape_rakuten_kamenoi
from core import config, quality
from core.compare import save_prices, find_previous_csv, load_prices, detect_changes
from core.report import generate_report
from core.notify import send_slack_alert, send_health_alert

log = config.setup_logging()


async def collect_prices() -> dict[str, dict]:
    """全施設の価格を取得する。個別施設の失敗は握りつぶし空dictを返す。"""
    today_prices: dict[str, dict] = {}

    for hotel_key, label in [
        ("kai_yufuin", "界 由布院"),
        ("enowa_yufuin", "ENOWA YUFUIN"),
    ]:
        log.info("%s 取得中...", label)
        try:
            today_prices[hotel_key] = await scrape_jalan_hotel(hotel_key)
            log.info("  → %d 日分取得", len(today_prices[hotel_key]))
        except Exception as e:
            log.error("  → %s 取得失敗: %s", label, e)
            today_prices[hotel_key] = {}

    log.info("亀の井別荘 取得中...")
    try:
        # 優先: 楽天トラベル公式API（RAKUTEN_APP_ID 設定時）。
        # 一休(ikyu)はボット検知で取得不可のため、API があればそちらを主とする。
        kamenoi = await asyncio.to_thread(scrape_rakuten_kamenoi)
        source = "rakuten-api"
        # 楽天APIが無効/失敗なら従来の一休スクレイパにフォールバック
        if not kamenoi:
            log.info("  → 楽天API未取得、一休スクレイパにフォールバック")
            kamenoi = await scrape_ikyu_kamenoi()
            source = "ikyu-scrape"
        today_prices["kamenoi_bessho"] = kamenoi
        log.info("  → 亀の井別荘 ソース: %s", source)
        manual = load_kamenoi_manual()
        if manual:
            added = sum(
                1 for k in manual if k not in today_prices["kamenoi_bessho"]
            )
            today_prices["kamenoi_bessho"].update(
                {k: v for k, v in manual.items() if k not in today_prices["kamenoi_bessho"]}
            )
            if added:
                log.info("  → 手動CSV補完: %d 件追加", added)
        log.info("  → %d 日分取得", len(today_prices["kamenoi_bessho"]))
    except Exception as e:
        log.error("  → 亀の井別荘 取得失敗: %s", e)
        today_prices["kamenoi_bessho"] = {}

    return today_prices


async def main() -> int:
    run_date = date.today().isoformat()
    log.info("[%s] 価格取得開始", run_date)

    today_prices = await collect_prices()

    # ── データ品質評価（サイレント障害/データ破壊の防止） ──────────────
    health = quality.assess(today_prices)
    log.info(
        "データ健全性: %s（合計 %d 件）", health.verdict.upper(), health.total_rows
    )
    for h in health.hotels:
        log.info("  %s: %d 件 [%s]", h.hotel_name, h.row_count, h.status)

    # 比較対象は「データの入った」直近CSV（空CSVはスキップ）
    prev_csv = find_previous_csv(exclude_date=run_date)
    prev_prices = load_prices(prev_csv) if prev_csv else {}
    if prev_csv:
        log.info("前日比較対象: %s", prev_csv.name)

    if health.is_failed:
        # 取得ほぼ全滅。過去の良データを空データで上書きしない。
        # レポートは直近の良データを表示し、失敗バナーを出す。
        log.error(
            "取得失敗と判定（合計 %d 件 ≤ %d）。CSV書き込みをスキップし前日データを保護します。",
            health.total_rows,
            config.MIN_TOTAL_ROWS,
        )
        report_path = generate_report(prev_prices, prev_prices, [], run_date, health)
        log.info("レポート生成（前日データ表示）: %s", report_path)
        send_health_alert(health, run_date)
        return 1

    # ── 正常/劣化: 保存して比較 ──────────────────────────────────────
    csv_path = save_prices(today_prices, run_date)
    log.info("CSV 保存: %s", csv_path)

    changes = detect_changes(today_prices, prev_prices)
    log.info("変動検出: %d 件（±%.0f%%以上）", len(changes), config.ALERT_THRESHOLD * 100)

    report_path = generate_report(today_prices, prev_prices, changes, run_date, health)
    log.info("レポート生成: %s", report_path)

    send_slack_alert(changes, run_date)
    if changes:
        log.info("Slack通知: %d 件送信", len(changes))

    # 劣化時は障害通知も送る（部分データは保存済み）
    if health.verdict == "degraded":
        send_health_alert(health, run_date)
        log.warning("データ劣化を通知しました。")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
