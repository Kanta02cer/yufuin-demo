import csv

from core import compare


def _write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["run_date", "hotel_key", "check_date", "price", "source"]
        )
        w.writeheader()
        w.writerows(rows)


def test_merge_sources_respects_priority():
    # serpapi_google が rakuten より優先（config.SOURCE_PRIORITY 順）
    by_source = {
        "kai_yufuin": {
            "rakuten": {"2026-08-01": 20000, "2026-08-02": 21000},
            "serpapi_google": {"2026-08-01": 19000},  # 同日はこちら優先
        }
    }
    prices, sources = compare.merge_sources(by_source)
    assert prices["kai_yufuin"]["2026-08-01"] == 19000
    assert sources["kai_yufuin"]["2026-08-01"] == "serpapi_google"
    # 08-02 は serpapi に無いので rakuten で補完
    assert prices["kai_yufuin"]["2026-08-02"] == 21000
    assert sources["kai_yufuin"]["2026-08-02"] == "rakuten"


def test_merge_sources_skips_none():
    by_source = {"x": {"jalan": {"2026-08-01": None, "2026-08-02": 100}}}
    prices, sources = compare.merge_sources(by_source)
    assert "2026-08-01" not in prices.get("x", {})
    assert prices["x"]["2026-08-02"] == 100


def test_detect_changes_skips_on_source_flip():
    today = {"kai_yufuin": {"2026-08-01": 30000}}
    prev = {"kai_yufuin": {"2026-08-01": 20000}}  # +50% だが…
    today_src = {"kai_yufuin": {"2026-08-01": "serpapi_google"}}
    prev_src = {"kai_yufuin": {"2026-08-01": "rakuten"}}  # ソースが違う
    # ソースが異なるため比較不能としてスキップ（誤アラート防止）
    assert compare.detect_changes(today, prev, today_src, prev_src) == []


def test_detect_changes_flags_when_same_source():
    today = {"kai_yufuin": {"2026-08-01": 30000}}
    prev = {"kai_yufuin": {"2026-08-01": 20000}}
    same = {"kai_yufuin": {"2026-08-01": "rakuten"}}
    changes = compare.detect_changes(today, prev, same, same)
    assert len(changes) == 1
    assert changes[0]["direction"] == "up"


def test_save_and_load_roundtrip_with_source(tmp_path, monkeypatch):
    monkeypatch.setattr(compare, "DATA_DIR", tmp_path)
    prices = {"kai_yufuin": {"2026-08-01": 19000}}
    sources = {"kai_yufuin": {"2026-08-01": "serpapi_google"}}
    compare.save_prices(prices, "2026-07-24", sources)
    p, s = compare.load_prices_with_source(tmp_path / "prices_2026-07-24.csv")
    assert p["kai_yufuin"]["2026-08-01"] == 19000
    assert s["kai_yufuin"]["2026-08-01"] == "serpapi_google"


def test_load_legacy_csv_without_source(tmp_path, monkeypatch):
    monkeypatch.setattr(compare, "DATA_DIR", tmp_path)
    # source 列の無い旧フォーマット
    path = tmp_path / "prices_2026-07-01.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["run_date", "hotel_key", "check_date", "price"])
        w.writeheader()
        w.writerow({"run_date": "2026-07-01", "hotel_key": "kai_yufuin", "check_date": "2026-08-01", "price": 20000})
    p, s = compare.load_prices_with_source(path)
    assert p["kai_yufuin"]["2026-08-01"] == 20000
    assert s["kai_yufuin"]["2026-08-01"] == "legacy"


def test_select_baseline_prefers_today_poll(tmp_path, monkeypatch):
    monkeypatch.setattr(compare, "DATA_DIR", tmp_path)
    _write(tmp_path / "prices_2026-07-23.csv", [
        {"run_date": "2026-07-23", "hotel_key": "kai_yufuin", "check_date": "2026-08-01", "price": 20000, "source": "rakuten"},
    ])
    # 同日に既に取得済み → こちらを基準にする（前回ポーリング比）
    _write(tmp_path / "prices_2026-07-24.csv", [
        {"run_date": "2026-07-24", "hotel_key": "kai_yufuin", "check_date": "2026-08-01", "price": 21000, "source": "rakuten"},
    ])
    baseline = compare.select_baseline_csv("2026-07-24")
    assert baseline.name == "prices_2026-07-24.csv"


def test_select_baseline_falls_back_to_prev_day(tmp_path, monkeypatch):
    monkeypatch.setattr(compare, "DATA_DIR", tmp_path)
    _write(tmp_path / "prices_2026-07-23.csv", [
        {"run_date": "2026-07-23", "hotel_key": "kai_yufuin", "check_date": "2026-08-01", "price": 20000, "source": "rakuten"},
    ])
    # 当日ファイルが未作成 → 前日にフォールバック
    baseline = compare.select_baseline_csv("2026-07-24")
    assert baseline.name == "prices_2026-07-23.csv"
