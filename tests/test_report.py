from core import quality
from core.report import generate_report


def test_generate_report_writes_html(tmp_path, monkeypatch):
    import core.report as report_mod

    monkeypatch.setattr(report_mod, "DOCS_DIR", tmp_path)
    today = {"kai_yufuin": {"2026-07-24": 25000}}
    health = quality.assess(
        {"kai_yufuin": {"2026-07-24": 25000}, "kamenoi_bessho": {}, "enowa_yufuin": {}}
    )
    out = generate_report(today, {}, [], "2026-07-24", health)
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "競合価格モニター" in html
    assert "データ取得状況" in html  # health section rendered


def test_report_shows_failed_banner(tmp_path, monkeypatch):
    import core.report as report_mod

    monkeypatch.setattr(report_mod, "DOCS_DIR", tmp_path)
    health = quality.assess(
        {"kai_yufuin": {}, "kamenoi_bessho": {}, "enowa_yufuin": {}}
    )
    out = generate_report({}, {}, [], "2026-07-24", health)
    html = out.read_text(encoding="utf-8")
    assert "取得失敗" in html


def test_report_without_health_still_renders(tmp_path, monkeypatch):
    import core.report as report_mod

    monkeypatch.setattr(report_mod, "DOCS_DIR", tmp_path)
    out = generate_report({"kai_yufuin": {"2026-07-24": 25000}}, {}, [], "2026-07-24")
    assert out.exists()
