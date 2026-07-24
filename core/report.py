from datetime import date, datetime, timedelta
from pathlib import Path

from jinja2 import Template

from core import config

DOCS_DIR = config.DOCS_DIR

_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>競合価格モニター | Sevenxseven 由布院</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Hiragino Sans',sans-serif;background:#f4f4f4;color:#333}
.header{background:#1a1a2e;color:#fff;padding:18px 24px}
.header h1{font-size:1.1rem;font-weight:600;letter-spacing:.02em}
.header .sub{font-size:.78rem;color:#aaa;margin-top:4px}
.container{max-width:1100px;margin:0 auto;padding:20px}
.card{background:#fff;border-radius:8px;padding:20px;margin-bottom:20px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.card h2{font-size:.95rem;font-weight:600;margin-bottom:14px;color:#222}
.no-alert{color:#888;font-size:.88rem}
.alert-tbl,.main-tbl{width:100%;border-collapse:collapse;font-size:.83rem}
.alert-tbl th,.main-tbl th{background:#1a1a2e;color:#fff;padding:9px 12px;text-align:center;font-weight:500;white-space:nowrap}
.alert-tbl td,.main-tbl td{padding:7px 12px;border-bottom:1px solid #eee;text-align:right;white-space:nowrap}
.alert-tbl td:first-child,.main-tbl td:first-child{text-align:left;font-weight:500;color:#555}
tr:hover td{background:#fafafa}
.up{background:#fff2f2;color:#c0392b;font-weight:700}
.down{background:#f0f5ff;color:#2471a3;font-weight:700}
.badge-up{background:#fff2f2;color:#c0392b;padding:2px 8px;border-radius:10px;font-weight:700;font-size:.8rem}
.badge-down{background:#f0f5ff;color:#2471a3;padding:2px 8px;border-radius:10px;font-weight:700;font-size:.8rem}
.sec-title{font-size:.9rem;font-weight:600;color:#555;margin:20px 0 10px}
.sat{color:#2471a3}
.sun{color:#c0392b}
.health{display:flex;gap:10px;flex-wrap:wrap;margin-top:6px}
.chip{font-size:.78rem;padding:3px 10px;border-radius:12px;font-weight:600}
.chip.ok{background:#eafaf1;color:#1e8449}
.chip.degraded{background:#fef9e7;color:#b9770e}
.chip.empty{background:#fdedec;color:#c0392b}
.status-banner{padding:10px 14px;border-radius:6px;font-size:.85rem;margin-bottom:16px;font-weight:600}
.status-banner.failed{background:#fdedec;color:#c0392b;border:1px solid #f5b7b1}
.status-banner.degraded{background:#fef9e7;color:#b9770e;border:1px solid #f9e79f}
.src{font-size:.62rem;color:#999;display:block;font-weight:400;margin-top:1px}
.legend{font-size:.75rem;color:#777;margin-top:8px}
.legend .src-badge{display:inline-block;background:#eef;color:#556;border-radius:6px;padding:1px 7px;margin-right:6px}
</style>
</head>
<body>
<div class="header">
  <h1>競合価格モニター｜Sevenxseven 由布院</h1>
  <div class="sub">最終更新: {{ updated_at }} JST　|　2名1室・最安価格（複数OTA横断）</div>
</div>
<div class="container">

  {% if health and health.verdict == "failed" %}
  <div class="status-banner failed">🔴 取得失敗: 本日の取得はほぼ全滅（合計 {{ health.total_rows }} 件）。表は直近の取得データを保持しています。</div>
  {% elif health and health.verdict == "degraded" %}
  <div class="status-banner degraded">🟡 データ劣化: 一部施設の取得件数が不足しています。下記の取得状況をご確認ください。</div>
  {% endif %}

  {% if health %}
  <div class="card">
    <h2>📡 データ取得状況</h2>
    <div class="health">
      {% for h in health.hotels %}
      <span class="chip {{ h.status }}">{{ h.hotel_name }}: {{ h.row_count }}件</span>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  <div class="card">
    <h2>⚠️ 直近の変動アラート（前回取得比 ±5%以上）</h2>
    {% if changes %}
    <table class="alert-tbl">
      <thead><tr><th>宿泊日</th><th>施設</th><th>前日価格</th><th>本日価格</th><th>変動率</th></tr></thead>
      <tbody>
      {% for c in changes %}
      <tr>
        <td>{{ c.check_date }}</td>
        <td>{{ c.hotel_name }}</td>
        <td>¥{{ "{:,}".format(c.prev_price) }}</td>
        <td>¥{{ "{:,}".format(c.today_price) }}</td>
        <td>
          {% if c.direction == "up" %}
          <span class="badge-up">▲{{ "%.1f"|format(c.change_rate * 100) }}%</span>
          {% else %}
          <span class="badge-down">▼{{ "%.1f"|format(c.change_rate * -100) }}%</span>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
    {% else %}
    <p class="no-alert">前回取得から5%以上の変動はありません。</p>
    {% endif %}
  </div>

  <div class="sec-title">全日程一覧（今日から{{ horizon_days }}日分・各セルは最安OTAの価格）</div>
  <div class="card" style="padding:0;overflow:auto">
    <table class="main-tbl">
      <thead>
        <tr>
          <th>宿泊日</th>
          <th>界 由布院</th>
          <th>亀の井別荘</th>
          <th>ENOWA YUFUIN</th>
        </tr>
      </thead>
      <tbody>
      {% for row in rows %}
      <tr>
        <td class="{{ row.day_cls }}">{{ row.label }}</td>
        <td class="{{ row.kai_cls }}">{{ row.kai }}{% if row.kai_src %}<span class="src">{{ row.kai_src }}</span>{% endif %}</td>
        <td class="{{ row.kamenoi_cls }}">{{ row.kamenoi }}{% if row.kamenoi_src %}<span class="src">{{ row.kamenoi_src }}</span>{% endif %}</td>
        <td class="{{ row.enowa_cls }}">{{ row.enowa }}{% if row.enowa_src %}<span class="src">{{ row.enowa_src }}</span>{% endif %}</td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
  <div class="legend">
    価格の取得元:
    {% for key, label in source_legend %}<span class="src-badge">{{ label }}</span>{% endfor %}
    各セルの下に実際に採用したOTAを表示しています。
  </div>

</div>
</body>
</html>"""

_WEEKDAY_NAMES = ["月", "火", "水", "木", "金", "土", "日"]


def _fmt(price: int | None) -> str:
    return f"¥{price:,}" if price is not None else "―"


def generate_report(
    today_prices: dict,
    prev_prices: dict,
    changes: list[dict],
    run_date: str,
    health=None,
    source_map: dict | None = None,
) -> Path:
    DOCS_DIR.mkdir(exist_ok=True)
    source_map = source_map or {}

    change_map = {(c["hotel_key"], c["check_date"]): c["direction"] for c in changes}

    def cls(hotel_key: str, ds: str) -> str:
        d = change_map.get((hotel_key, ds))
        return "up" if d == "up" else ("down" if d == "down" else "")

    def src_label(hotel_key: str, ds: str) -> str:
        s = source_map.get(hotel_key, {}).get(ds)
        return config.SOURCE_LABELS.get(s, s) if s else ""

    today = date.fromisoformat(run_date)
    rows = []
    current = today
    while current <= today + timedelta(days=config.HORIZON_DAYS):
        ds = current.isoformat()
        wd = current.weekday()
        rows.append(
            {
                "label": f"{current.strftime('%Y/%m/%d')}（{_WEEKDAY_NAMES[wd]}）",
                "day_cls": "sun" if wd == 6 else ("sat" if wd == 5 else ""),
                "kai": _fmt(today_prices.get("kai_yufuin", {}).get(ds)),
                "kai_cls": cls("kai_yufuin", ds),
                "kai_src": src_label("kai_yufuin", ds),
                "kamenoi": _fmt(today_prices.get("kamenoi_bessho", {}).get(ds)),
                "kamenoi_cls": cls("kamenoi_bessho", ds),
                "kamenoi_src": src_label("kamenoi_bessho", ds),
                "enowa": _fmt(today_prices.get("enowa_yufuin", {}).get(ds)),
                "enowa_cls": cls("enowa_yufuin", ds),
                "enowa_src": src_label("enowa_yufuin", ds),
            }
        )
        current += timedelta(days=1)

    # レポートに登場したソースだけを凡例に出す
    used = {s for h in source_map.values() for s in h.values()}
    source_legend = [
        (k, config.SOURCE_LABELS.get(k, k))
        for k in config.SOURCE_PRIORITY + ["legacy"]
        if k in used
    ]

    html = Template(_TEMPLATE).render(
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        changes=changes,
        rows=rows,
        health=health,
        horizon_days=config.HORIZON_DAYS,
        source_legend=source_legend,
    )
    out = DOCS_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    return out
