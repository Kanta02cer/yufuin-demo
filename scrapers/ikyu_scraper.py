import asyncio
import csv
import json
import re
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from playwright.async_api import async_playwright

DEBUG_DIR = Path(__file__).parent.parent / "data" / "debug"
MANUAL_CSV = Path(__file__).parent.parent / "data" / "kamenoi_manual.csv"

HOTEL_ID = "00002470"

LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
]

_EXTRA_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def _extract_prices_from_json(obj, prices: dict, year: int, month: int):
    if isinstance(obj, dict):
        stay = (
            obj.get("date") or obj.get("checkin") or obj.get("checkInDate")
            or obj.get("stayDate") or obj.get("ymd")
        )
        price = (
            obj.get("price") or obj.get("minPrice") or obj.get("lowestPrice")
            or obj.get("amount") or obj.get("planPrice") or obj.get("totalPrice")
        )
        if stay and price:
            raw = str(stay).replace("/", "-")[:10]
            try:
                d = date.fromisoformat(raw)
                if d.year == year and d.month == month:
                    prices[raw] = int(str(price).replace(",", ""))
            except (ValueError, TypeError):
                pass
        for v in obj.values():
            _extract_prices_from_json(v, prices, year, month)
    elif isinstance(obj, list):
        for item in obj:
            _extract_prices_from_json(item, prices, year, month)


def load_kamenoi_manual() -> dict[str, int]:
    """data/kamenoi_manual.csv から手動入力価格を読み込む。
    CSVフォーマット: check_date,price (例: 2026-07-01,85000)
    """
    if not MANUAL_CSV.exists():
        return {}
    prices: dict[str, int] = {}
    with open(MANUAL_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                d = date.fromisoformat(row["check_date"].strip())
                prices[d.isoformat()] = int(row["price"].strip())
            except (KeyError, ValueError, TypeError):
                pass
    print(f"  [ikyu/manual] 手動CSV読込: {len(prices)} 件 ({MANUAL_CSV.name})")
    return prices


def _try_requests_month(year: int, month: int) -> dict[str, int]:
    """urllib（Playwright不使用）で月次価格を試行取得する。
    ikyu.com が Next.js の場合 __NEXT_DATA__ に価格データが含まれることがある。
    """
    prices: dict[str, int] = {}
    url = (
        f"https://www.ikyu.com/{HOTEL_ID}/"
        f"?adc=1&discsort=1&lc=1&ppc=2&rc=1&si=1"
        f"&st={year}{month:02d}01&top=plans"
    )
    req = urllib.request.Request(url, headers=_REQUEST_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw_bytes = resp.read()
            # gzip/br は urllib が自動デコードしないので UTF-8 を試みる
            try:
                content = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                content = raw_bytes.decode("shift_jis", errors="replace")
    except Exception as e:
        print(f"  [ikyu/http] {year}/{month:02d} 失敗: {e}")
        return prices

    if "アクセスが拒否されました" in content or "Forbidden" in content:
        print(f"  [ikyu/http] {year}/{month:02d} ブロック検知")
        return prices

    # ① __NEXT_DATA__ JSON（Next.js SSR ページ）
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)</script>', content)
    if m:
        try:
            _extract_prices_from_json(json.loads(m.group(1)), prices, year, month)
        except Exception:
            pass
    if prices:
        return prices

    # ② application/ld+json（構造化データ）
    for ld_m in re.finditer(r'<script[^>]+type="application/ld\+json"[^>]*>([\s\S]*?)</script>', content):
        try:
            _extract_prices_from_json(json.loads(ld_m.group(1)), prices, year, month)
        except Exception:
            pass
    if prices:
        return prices

    # ③ HTML内正規表現
    for pattern in [
        r'"date"\s*:\s*"(\d{4}-\d{2}-\d{2})"[^}]{0,300}"price"\s*:\s*(\d+)',
        r'"checkin"\s*:\s*"(\d{4}-\d{2}-\d{2})"[^}]{0,300}"price"\s*:\s*(\d+)',
        r'"ymd"\s*:\s*"(\d{4}-\d{2}-\d{2})"[^}]{0,300}"price"\s*:\s*(\d+)',
    ]:
        for match in re.finditer(pattern, content):
            raw = match.group(1)
            try:
                d = date.fromisoformat(raw)
                if d.year == year and d.month == month:
                    prices[raw] = int(match.group(2))
            except ValueError:
                pass
        if prices:
            return prices

    # デバッグ用にHTMLを保存
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    dbg = DEBUG_DIR / f"ikyu_http_{year}{month:02d}.html"
    dbg.write_text(content[:50000], encoding="utf-8")  # 最初の50KBのみ保存

    return prices


async def _warm_up_session(page):
    try:
        await page.goto("https://www.ikyu.com/", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
    except Exception:
        pass


async def _scrape_month_playwright(page, year: int, month: int) -> dict[str, int]:
    prices: dict[str, int] = {}
    intercepted: list = []

    async def handle_response(resp):
        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            try:
                body = await resp.json()
                intercepted.append(body)
            except Exception:
                pass

    page.on("response", handle_response)

    url = (
        f"https://www.ikyu.com/{HOTEL_ID}/"
        f"?adc=1&discsort=1&lc=1&ppc=2&rc=1&si=1"
        f"&st={year}{month:02d}01&top=plans"
    )
    await page.goto(url, wait_until="networkidle", timeout=45000)
    page.remove_listener("response", handle_response)

    for body in intercepted:
        _extract_prices_from_json(body, prices, year, month)
    if prices:
        return prices

    content = await page.content()

    if "アクセスが拒否されました" in content or "Forbidden" in content:
        print(f"  [ikyu/playwright] {year}/{month:02d} ボット検知")
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        (DEBUG_DIR / f"ikyu_{year}{month:02d}.html").write_text(content, encoding="utf-8")
        return prices

    for pattern in [
        r'"date"\s*:\s*"(\d{4}-\d{2}-\d{2})"[^}]{0,300}"price"\s*:\s*(\d+)',
        r'"checkin"\s*:\s*"(\d{4}-\d{2}-\d{2})"[^}]{0,300}"price"\s*:\s*(\d+)',
        r'"ymd"\s*:\s*"(\d{4}-\d{2}-\d{2})"[^}]{0,300}"price"\s*:\s*(\d+)',
        r'(\d{4}-\d{2}-\d{2})[^0-9]{1,30}([1-9][0-9]{4,6})',
    ]:
        for m in re.finditer(pattern, content):
            raw = m.group(1)
            try:
                d = date.fromisoformat(raw)
                if d.year == year and d.month == month:
                    prices[raw] = int(m.group(2).replace(",", ""))
            except (ValueError, IndexError):
                pass
        if prices:
            return prices

    for sel in [
        "[data-date]", "[data-ymd]", "[data-checkin]",
        "[class*='calendar'] td", "[class*='Calendar'] td", "[class*='price']",
    ]:
        cells = await page.query_selector_all(sel)
        for cell in cells:
            raw_date = (
                await cell.get_attribute("data-date")
                or await cell.get_attribute("data-ymd")
                or await cell.get_attribute("data-checkin")
            )
            text = await cell.inner_text()
            price_m = re.search(r"([1-9][0-9,]{4,})", text)
            if raw_date and price_m:
                key = raw_date[:10].replace("/", "-")
                try:
                    d = date.fromisoformat(key)
                    if d.year == year and d.month == month:
                        prices[key] = int(price_m.group(1).replace(",", ""))
                except ValueError:
                    pass
        if prices:
            return prices

    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    (DEBUG_DIR / f"ikyu_{year}{month:02d}.html").write_text(content, encoding="utf-8")
    print(f"  [debug] No prices found, saved HTML → ikyu_{year}{month:02d}.html")

    return prices


async def scrape_ikyu_kamenoi() -> dict[str, int | None]:
    today = date.today()
    end_date = today + timedelta(days=180)
    all_prices: dict[str, int | None] = {}

    # ── Step 1: urllib 直接 HTTP（Playwright フィンガープリント回避） ──────
    print("  [ikyu] urllib 直接取得を試行中...")
    http_total = 0
    for offset in range(7):
        first = (today.replace(day=1) + timedelta(days=32 * offset)).replace(day=1)
        print(f"  [ikyu/http] {first.year}/{first.month:02d} 取得中...")
        monthly = _try_requests_month(first.year, first.month)
        print(f"  [ikyu/http] {first.year}/{first.month:02d} → {len(monthly)} 件")
        all_prices.update(monthly)
        http_total += len(monthly)
        time.sleep(2)

    if http_total > 0:
        print(f"  [ikyu] urllib 取得成功: 合計 {http_total} 件")
        return {
            d: v for d, v in all_prices.items()
            if today.isoformat() <= d <= end_date.isoformat()
        }

    # ── Step 2: Playwright フォールバック ──────────────────────────────────
    print("  [ikyu] urllib 全滅、Playwright フォールバックを試みます...")
    all_prices = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=LAUNCH_ARGS)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
            extra_http_headers=_EXTRA_HEADERS,
        )
        await context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = await context.new_page()

        print("  [ikyu] セッション確立中...")
        await _warm_up_session(page)

        blocked_count = 0
        for offset in range(7):
            first = (today.replace(day=1) + timedelta(days=32 * offset)).replace(day=1)
            print(f"  [ikyu/playwright] {first.year}/{first.month:02d} 取得中...")
            monthly = await _scrape_month_playwright(page, first.year, first.month)
            print(f"  [ikyu/playwright] {first.year}/{first.month:02d} → {len(monthly)} 件")
            all_prices.update(monthly)
            if len(monthly) == 0:
                blocked_count += 1
            else:
                blocked_count = 0
            if blocked_count >= 3:
                print("  [ikyu] 連続ブロック検知、スクレイピングを中止します")
                break
            await asyncio.sleep(4)

        await browser.close()

    return {
        d: v for d, v in all_prices.items()
        if today.isoformat() <= d <= end_date.isoformat()
    }
