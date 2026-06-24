from datetime import date, datetime, timedelta
from pathlib import Path

from jinja2 import Template

DOCS_DIR = Path(__file__).parent.parent / "docs"

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
</style>
</head>
<body>
<div class="header">
  <h1>競合価格モニター｜Sevenxseven 由布院</h1>
  <div class="sub">最終更新: {{ updated_at }} JST　|　2名1室・指定プラン最低価格</div>
</div>
<div class="container">

  <div class="card">
    <h2>⚠️ 本日の変動アラート（前日比 ±5%以上）</h2>
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
    <p class="no-alert">前日から5%以上の変動はありません。</p>
    {% endif %}
  </div>

  <div class="sec-title">全日程一覧（今日から180日分）</div>
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
        <td class="{{ row.kai_cls }}">{{ row.kai }}</td>
        <td class="{{ row.kamenoi_cls }}">{{ row.kamenoi }}</td>
        <td class="{{ row.enowa_cls }}">{{ row.enowa }}</td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
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
) -> Path:
    DOCS_DIR.mkdir(exist_ok=True)

    change_map = {(c["hotel_key"], c["check_date"]): c["direction"] for c in changes}

    def cls(hotel_key: str, ds: str) -> str:
        d = change_map.get((hotel_key, ds))
        return "up" if d == "up" else ("down" if d == "down" else "")

    today = date.fromisoformat(run_date)
    rows = []
    current = today
    while current <= today + timedelta(days=180):
        ds = current.isoformat()
        wd = current.weekday()
        rows.append(
            {
                "label": f"{current.strftime('%Y/%m/%d')}（{_WEEKDAY_NAMES[wd]}）",
                "day_cls": "sun" if wd == 6 else ("sat" if wd == 5 else ""),
                "kai": _fmt(today_prices.get("kai_yufuin", {}).get(ds)),
                "kai_cls": cls("kai_yufuin", ds),
                "kamenoi": _fmt(today_prices.get("kamenoi_bessho", {}).get(ds)),
                "kamenoi_cls": cls("kamenoi_bessho", ds),
                "enowa": _fmt(today_prices.get("enowa_yufuin", {}).get(ds)),
                "enowa_cls": cls("enowa_yufuin", ds),
            }
        )
        current += timedelta(days=1)

    html = Template(_TEMPLATE).render(
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        changes=changes,
        rows=rows,
    )
    out = DOCS_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    return out
