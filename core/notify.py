import json
import os
import urllib.request


def _post(webhook_url: str, text: str) -> None:
    payload = {"text": text}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                print(f"  [slack] 送信失敗: HTTP {resp.status}")
    except Exception as e:
        print(f"  [slack] 送信エラー: {e}")


def send_health_alert(health, run_date: str) -> None:
    """スクレイピング障害/劣化をSlackに通知する。

    health: core.quality.RunHealth
    価格変動とは別に「パイプライン自体が壊れた」ことを運用者に知らせる。
    サイレント障害（空データを黙って書き込む）を防ぐための通知。
    """
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return
    if health.is_healthy:
        return

    if health.is_failed:
        head = f":rotating_light: *価格監視 実行失敗｜{run_date}*"
        head += f"\n全施設合計 {health.total_rows} 件しか取得できませんでした。前日データは保護されています。"
    else:
        head = f":warning: *価格監視 データ劣化｜{run_date}*"

    lines = [head]
    for h in health.problems():
        mark = "❌" if h.status == "empty" else "△"
        lines.append(f"• {mark} {h.hotel_name}: {h.row_count} 件 ({h.status})")

    _post(webhook_url, "\n".join(lines))


def send_slack_alert(changes: list[dict], run_date: str) -> None:
    """変動アラートをSlackに送信する（SLACK_WEBHOOK_URL が設定されていれば）"""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return

    if not changes:
        return

    lines = [f"*競合価格アラート｜{run_date}*（前日比 ±5%以上）"]
    for c in changes[:20]:  # 最大20件
        direction = "▲" if c["direction"] == "up" else "▼"
        rate = abs(c["change_rate"]) * 100
        lines.append(
            f"• {c['check_date']} {c['hotel_name']} "
            f"¥{c['prev_price']:,} → ¥{c['today_price']:,} "
            f"({direction}{rate:.1f}%)"
        )
    if len(changes) > 20:
        lines.append(f"… 他 {len(changes) - 20} 件")

    _post(webhook_url, "\n".join(lines))
