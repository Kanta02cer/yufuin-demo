# Yufuin Price Monitor

Sevenxseven 由布院 競合価格モニタリングシステム

GitHub Actions が **6時間ごとにポーリング**し、競合3施設の価格を**複数のOTAソースを
横断して**取得します（各日付の最安を採用）。前回取得比 ±5%以上の変動をレポートページに
ハイライト表示します。

## データソース（複数併用）

Booking.com/Agoda/一休などは**サーバーからのHTML直接取得がボット検知でブロック**される
（下記「データソース検証結果」）。そこで**公式API・集約API**を優先的に併用します。

| 施設 | 主ソース | フォールバック |
|------|----------|----------------|
| 界 由布院 | SerpAPI(Google Hotels=Booking系) | じゃらん |
| 亀の井別荘 | 楽天トラベル公式API | 一休スクレイパ → 手動CSV |
| ENOWA YUFUIN | SerpAPI(Google Hotels=Booking系) | じゃらん |

各日付の価格は `SOURCE_PRIORITY`（`serpapi_google > rakuten > jalan > ikyu > manual`）の
順で採用され、レポート上に**採用ソースを明示**します。

## レポート確認

GitHub Pages URL（設定後）:  
`https://nyamaguchikc-alt.github.io/yufuin-price-monitor/`

## アーキテクチャ

```
main.py                … オーケストレーション（全ソース取得→マージ→品質評価→保存→比較→レポート→通知）
scrapers/
  serpapi_hotels.py    … SerpAPI(Google Hotels): Booking/Agoda/Expedia を集約
  rakuten_api.py       … 楽天トラベル公式API（亀の井別荘ほか）
  jalan_scraper.py     … じゃらん（界由布院 / ENOWA）フォールバック
  ikyu_scraper.py      … 一休（亀の井別荘）+ 手動CSV補完 フォールバック
core/
  config.py            … 集中設定（閾値・施設・監視期間・ソース優先度・APIキー・ログ）
  quality.py           … データ健全性評価（ok / degraded / failed）
  compare.py           … CSV入出力(source列)・ソースマージ・前回比較・変動検出
  report.py            … HTMLレポート生成（docs/index.html、採用ソース表示）
  notify.py            … Slack通知（価格変動 + 障害/劣化アラート）
tests/                 … pytest ユニットテスト（32件）
```

### 複数ソースのマージ

各ソースは `{hotel_key: {check_date: price}}` を返し、`compare.merge_sources()` が
`SOURCE_PRIORITY` 順にマージして「日付ごとの最優先ソースの価格」と「採用ソース」を決めます。
CSV には `source` 列を追加（旧フォーマットは `legacy` として後方互換読み込み）。
変動検出は**同一ソース同士**で比較し、ソースが切り替わった日付は誤アラートを避けてスキップします。

### ポーリングと比較基準

6時間ごとに実行し、比較基準は「同日の前回ポーリング → 無ければ前日以前の直近データ」を
自動選択（`compare.select_baseline_csv()`）。CSVは日付単位で上書きするためリポジトリは肥大しません。

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

### 4. SerpAPI（Booking.com 等の価格・推奨）

Booking.com/Agoda/Expedia はHTML直接取得が不可（Booking=202チャレンジ, Expedia=429）。
**Google Hotels を集約する SerpAPI** でこれらの価格を合法的に取得します。

1. https://serpapi.com/ でAPIキーを取得（無料枠 月100検索）
2. Actions Secret に `SERPAPI_KEY` を登録（`daily_price_check.yml` 設定済み）
3. 取得日数は Actions Variable `SERPAPI_HORIZON_DAYS`（既定30）で調整

**コストに関する重要な注意:** SerpAPI は 1検索=1課金で、エリア検索1回＝全施設×1日付。
つまり **1回の実行で「取得日数+1」検索**を消費します（既定30日＝31検索）。
6時間ごと(1日4回)×31検索 ≈ 124検索/日 となり**無料枠(月100)では数日で尽きます**。
運用時は次のいずれかを選んでください:
- SerpAPI の有料プラン（例: 月$75〜/5,000検索）を契約する
- `SERPAPI_HORIZON_DAYS` を小さく（例: 7）し、直近のみBooking系価格を取る
- SerpAPI未設定でも**楽天API＋じゃらんは無料で毎回稼働**します（Booking系価格のみ欠落）

### 5. 初回実行

Actions → **Price Check (polling)** → **Run workflow**

以降は6時間ごと（UTC 0/6/12/18 = JST 9/15/21/3時）に自動実行されます。
実行頻度は `.github/workflows/daily_price_check.yml` の cron で調整できます。

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
| `ALERT_THRESHOLD` | `0.05` | 前回比アラート閾値 |
| `HORIZON_DAYS` | `180` | 監視期間（今日から N 日先） |
| `MIN_ROWS_PER_HOTEL` | `30` | これ未満で施設を「劣化」判定 |
| `MIN_TOTAL_ROWS` | `10` | これ以下で「実行失敗」判定（前回データ保護） |
| `SLACK_WEBHOOK_URL` | なし | Slack Incoming Webhook |
| `RAKUTEN_APP_ID` / `RAKUTEN_ACCESS_KEY` | なし | 楽天トラベルAPIキー（亀の井別荘） |
| `SERPAPI_KEY` | なし | SerpAPI キー（Booking系価格） |
| `SERPAPI_HORIZON_DAYS` | `30` | SerpAPI で取得する日数（=検索数。コスト管理） |
| `SERPAPI_QUERY` | `由布院温泉 旅館` | Google Hotels のエリア検索クエリ |

## データソース検証結果

各サイトへの到達性を実地検証した結果（この環境から確認）:

| ソース | 到達性 | 備考 |
|--------|--------|------|
| Booking.com HTML | ❌ 202 | JSボット検知チャレンジページ（価格0件）。直接取得不可 |
| Expedia HTML | ❌ 429 | レート制限/ブロック |
| 一休(ikyu) HTML | ❌ 403 | ボット検知で取得不可 |
| 楽天トラベル 施設ページ HTML | ❌ 403 | サイトHTMLは楽天もブロック |
| **SerpAPI (Google Hotels)** | ✅ 到達可 | Booking/Agoda/Expedia を集約してJSON返却（要APIキー、無料枠あり） |
| **楽天トラベル 公式API** | ✅ 到達可 | `VacantHotelSearch` が JSON を返す（要 applicationId、無料）。亀の井別荘=180627 |
| じゃらん HTML | ⚠️ 200 | 現行動作するがDOM/プラン変更に脆い |

**要点: OTAサイトのHTML直接スクレイピングは、弱いサイトを探しても最終的に403/202/429の壁に当たる**
（Booking.comは業界最強クラスのボット検知）。**突破口は "スクレイピング" ではなく "API"。**
Booking系価格は Google Hotels 集約(SerpAPI)、日系OTAは楽天公式APIで取得する。

## 既知の課題 / 今後の改善

- **亀の井別荘の取得**: 一休(ikyu)はボット検知(403)で不可。**楽天トラベルAPIの利用を推奨**
  （上記「セットアップ 3」）。API未設定時は一休スクレイパ＋`data/kamenoi_manual.csv` に
  フォールバックします。
- **じゃらんの取得安定性**: プランコード/DOMの変更で取得0件になる日があります。
  将来的には界由布院・ENOWA も楽天トラベルAPIへ移行すると安定します
  （`RAKUTEN_HOTEL_NOS` に施設番号を追加すれば同じ仕組みで取得可能）。
- 取得失敗は障害保護（前日データ保護）と Slack 通知で検知できます。
