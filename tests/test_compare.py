import csv

import pytest

from core import compare


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["run_date", "hotel_key", "check_date", "price"])
        w.writeheader()
        w.writerows(rows)


def test_detect_changes_flags_over_threshold():
    today = {"kai_yufuin": {"2026-08-01": 22000}}
    prev = {"kai_yufuin": {"2026-08-01": 20000}}  # +10%
    changes = compare.detect_changes(today, prev)
    assert len(changes) == 1
    assert changes[0]["direction"] == "up"
    assert changes[0]["change_rate"] == pytest.approx(0.10)


def test_detect_changes_ignores_small_moves():
    today = {"kai_yufuin": {"2026-08-01": 20400}}  # +2%
    prev = {"kai_yufuin": {"2026-08-01": 20000}}
    assert compare.detect_changes(today, prev) == []


def test_detect_changes_down_direction():
    today = {"enowa_yufuin": {"2026-08-01": 18000}}  # -10%
    prev = {"enowa_yufuin": {"2026-08-01": 20000}}
    changes = compare.detect_changes(today, prev)
    assert changes[0]["direction"] == "down"


def test_detect_changes_skips_missing_prev():
    today = {"kai_yufuin": {"2026-08-01": 22000}}
    prev = {}  # 前日データなし → 比較不能
    assert compare.detect_changes(today, prev) == []


def test_detect_changes_skips_none_price():
    today = {"kai_yufuin": {"2026-08-01": None}}
    prev = {"kai_yufuin": {"2026-08-01": 20000}}
    assert compare.detect_changes(today, prev) == []


def test_find_previous_csv_skips_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(compare, "DATA_DIR", tmp_path)
    # 古い日: データあり / 新しい日: 空(ヘッダのみ、障害日)
    _write_csv(
        tmp_path / "prices_2026-07-10.csv",
        [{"run_date": "2026-07-10", "hotel_key": "kai_yufuin", "check_date": "2026-08-01", "price": 20000}],
    )
    _write_csv(tmp_path / "prices_2026-07-11.csv", [])  # 空
    prev = compare.find_previous_csv(exclude_date="2026-07-12")
    assert prev is not None
    assert prev.name == "prices_2026-07-10.csv"  # 空をスキップして良データを選ぶ


def test_find_previous_csv_none_when_all_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(compare, "DATA_DIR", tmp_path)
    _write_csv(tmp_path / "prices_2026-07-10.csv", [])
    assert compare.find_previous_csv(exclude_date="2026-07-12") is None
