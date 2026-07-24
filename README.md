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

### 3. 楽天トラベル API（亀の井別荘の安定取得・推奨）

亀の井別荘は一休(ikyu)のボット検知で自動取得できません（下記「既知の課題」参照）。
**楽天トラベル公式API** を使うとボット検知なしで安定取得できます。

1. https://webservice.rakuten.co.jp/ でアプリID(applicationId)を無料発行
2. Actions Secret に登録:
   - `RAKUTEN_APP_ID`（必須）
   - `RAKUTEN_ACCESS_KEY`（発行時に併記されていれば設定）
3. ワークフローの env に受け渡す（`daily_price_check.yml` 設定済み）

`RAKUTEN_APP_ID` を設定すると `main.py` は亀の井別荘を楽天API優先で取得し、
未設定/失敗時は従来の一休スクレイパ＋手動CSVにフォールバックします。
施設番号は `core/config.py` の `RAKUTEN_HOTEL_NOS`（亀の井別荘=180627）で管理します。

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

## データソース検証結果

各サイトへの到達性を実地検証した結果（この環境から確認）:

| ソース | 到達性 | 備考 |
|--------|--------|------|
| 一休(ikyu) HTML | ❌ 403 | ボット検知で取得不可 |
| 楽天トラベル 施設ページ HTML | ❌ 403 | サイトHTMLは楽天もブロック |
| **楽天トラベル 公式API** | ✅ 到達可 | `VacantHotelSearch` が JSON を返す（要 applicationId、無料）。亀の井別荘=180627 |
| じゃらん HTML | ⚠️ 200 | 現行動作するがDOM/プラン変更に脆い |

**要点: サイトHTMLの直接スクレイピングは弱いサイトを探しても403の壁に当たる。**
**突破口は "スクレイピング" ではなく "公式API"。** 亀の井別荘は楽天API(`scrapers/rakuten_api.py`)で安定取得できる。

## 既知の課題 / 今後の改善

- **亀の井別荘の取得**: 一休(ikyu)はボット検知(403)で不可。**楽天トラベルAPIの利用を推奨**
  （上記「セットアップ 3」）。API未設定時は一休スクレイパ＋`data/kamenoi_manual.csv` に
  フォールバックします。
- **じゃらんの取得安定性**: プランコード/DOMの変更で取得0件になる日があります。
  将来的には界由布院・ENOWA も楽天トラベルAPIへ移行すると安定します
  （`RAKUTEN_HOTEL_NOS` に施設番号を追加すれば同じ仕組みで取得可能）。
- 取得失敗は障害保護（前日データ保護）と Slack 通知で検知できます。
