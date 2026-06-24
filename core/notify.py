import json
import os
import urllib.request
from datetime import date


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

    payload = {"text": "\n".join(lines)}
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
