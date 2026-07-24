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

## アーキテクチャ

```
main.py                … オーケストレーション（取得→品質評価→保存→比較→レポート→通知）
scrapers/
  jalan_scraper.py     … じゃらん（界由布院 / ENOWA）
  ikyu_scraper.py      … 一休（亀の井別荘）+ 手動CSV補完
core/
  config.py            … 集中設定（閾値・施設・監視期間・データ品質基準・ログ）
  quality.py           … データ健全性評価（ok / degraded / failed）
  compare.py           … CSV入出力・前日比較・変動検出
  report.py            … HTMLレポート生成（docs/index.html）
  notify.py            … Slack通知（価格変動 + 障害/劣化アラート）
tests/                 … pytest ユニットテスト
```

## データ健全性と障害保護

本システムは対象サイトのボット検知・仕様変更でスクレイピングが失敗し得るため、
**サイレント障害とデータ破壊を防ぐ**仕組みを備えています（`core/quality.py`）。

| 判定 | 条件（既定値） | 挙動 |
|------|----------------|------|
| `ok` | 全施設が十分な件数 | 通常保存・比較・通知 |
| `degraded` | いずれかの施設が `MIN_ROWS_PER_HOTEL`(30) 未満 | 部分データを保存し、Slackに劣化通知。レポートに🟡バナー |
| `failed` | 全施設合計が `MIN_TOTAL_ROWS`(10) 以下 | **CSVを書かず前日データを保護**。Slackに失敗通知。レポートに🔴バナー。exit 1 |

- 変動比較の「前日」は**データの入った直近CSV**を選びます（空の障害日をスキップ）。
- 失敗時 CI ジョブは赤（失敗）になり、レポート/デプロイは継続します（監視性のため）。

## セットアップ

### 1. GitHub Pages を有効化

Settings → Pages → Source: **Deploy from a branch**  
Branch: `main` / Folder: `/docs` → Save

### 2. Slack 通知（任意・推奨）

Settings → Secrets and variables → Actions → **New repository secret**  
Name: `SLACK_WEBHOOK_URL` / Value: Incoming Webhook の URL

未設定でも動作しますが、**障害通知が飛ばない**ため本番では設定を推奨します。

### 3. 初回実行

Actions → **Daily Price Check** → **Run workflow**

以降は毎朝 07:00 JST に自動実行されます。

## ローカル実行

```bash
pip install -r requirements.txt
playwright install chromium
python main.py
```

## テスト

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

## 設定の上書き（環境変数）

| 変数 | 既定 | 説明 |
|------|------|------|
| `ALERT_THRESHOLD` | `0.05` | 前日比アラート閾値 |
| `HORIZON_DAYS` | `180` | 監視期間（今日から N 日先） |
| `MIN_ROWS_PER_HOTEL` | `30` | これ未満で施設を「劣化」判定 |
| `MIN_TOTAL_ROWS` | `10` | これ以下で「実行失敗」判定（前日データ保護） |
| `SLACK_WEBHOOK_URL` | なし | Slack Incoming Webhook |

## 既知の課題 / 今後の改善

- **亀の井別荘（一休）の自動取得**: 一休のボット検知が強く、実運用では取得が安定しません。
  現状は `data/kamenoi_manual.csv`（`check_date,price` 形式）による手動補完に依存します。
  安定化には一休の公式APIまたは取得プロキシの検討が必要です。
- **じゃらんの取得安定性**: プランコード/DOMの変更で取得0件になる日があります。
  失敗は上記の障害保護と Slack 通知で検知できます。
