from core import config, quality


def _full(n):
    return {f"2026-08-{i:02d}": 20000 for i in range(1, n + 1)}


def test_healthy_when_all_hotels_ok():
    prices = {
        "kai_yufuin": _full(40),
        "kamenoi_bessho": _full(40),
        "enowa_yufuin": _full(40),
    }
    h = quality.assess(prices)
    assert h.verdict == "ok"
    assert h.is_healthy
    assert h.problems() == []


def test_failed_when_all_empty():
    prices = {"kai_yufuin": {}, "kamenoi_bessho": {}, "enowa_yufuin": {}}
    h = quality.assess(prices)
    assert h.verdict == "failed"
    assert h.is_failed
    assert h.total_rows == 0


def test_degraded_when_one_hotel_empty():
    prices = {
        "kai_yufuin": _full(40),
        "kamenoi_bessho": {},  # 亀の井が常に空 = 実データの状況
        "enowa_yufuin": _full(40),
    }
    h = quality.assess(prices)
    assert h.verdict == "degraded"
    problems = {p.hotel_key: p.status for p in h.problems()}
    assert problems["kamenoi_bessho"] == "empty"


def test_degraded_when_below_min_rows():
    prices = {
        "kai_yufuin": _full(40),
        "kamenoi_bessho": _full(40),
        "enowa_yufuin": _full(config.MIN_ROWS_PER_HOTEL - 1),
    }
    h = quality.assess(prices)
    assert h.verdict == "degraded"


def test_none_prices_not_counted():
    prices = {
        "kai_yufuin": {"2026-08-01": None, "2026-08-02": None},
        "kamenoi_bessho": {},
        "enowa_yufuin": {},
    }
    h = quality.assess(prices)
    assert h.total_rows == 0
    assert h.verdict == "failed"
