# Yufuin Price Monitor

Sevenxseven 由布院 競合価格モニタリングシステム

毎朝 07:00 JST に GitHub Actions が自動実行し、競合3施設の半年先までの価格を取得。  
前日比 ±5%以上の変動をレポートページにハイライト表示します。

## 競合施設

| 施設 | サイト | プラン・部屋 |
|------|--------|-------------|
| 界 由布院 | じゃらん | スタンダード◇棚田 / 露天風呂付き和室 |
| 亀の井別荘 | 一休 | 亀の井洋室プラン / 園林 本館洋室ツイン |
| ENOWA YUFUIN | じゃらん | ENOWA Standard Stay / The Rooms 半露天風呂付 |

## レポート確認

GitHub Pages URL（設定後）:  
`https://nyamaguchikc-alt.github.io/yufuin-price-monitor/`

## セットアップ

### 1. GitHub Pages を有効化

Settings → Pages → Source: **Deploy from a branch**  
Branch: `main` / Folder: `/docs` → Save

### 2. 初回実行

Actions → **Daily Price Check** → **Run workflow**

以降は毎朝 07:00 JST に自動実行されます。

## ローカル実行

```bash
pip install -r requirements.txt
playwright install chromium
python main.py
```
