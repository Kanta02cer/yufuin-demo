import asyncio
import re
from datetime import date, timedelta
from pathlib import Path
from playwright.async_api import async_playwright

DEBUG_DIR = Path(__file__).parent.parent / "data" / "debug"

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


async def _warm_up_session(page):
    """一休.comのトップページを訪問してCookieとセッションを確立する"""
    try:
        await page.goto("https://www.ikyu.com/", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
    except Exception:
        pass


async def _scrape_month(page, year: int, month: int) -> dict[str, int]:
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

    # ① XHR傍受
    for body in intercepted:
        _extract_prices_from_json(body, prices, year, month)
    if prices:
        return prices

    content = await page.content()

    # ボット検知ページの場合はスキップ
    if "アクセスが拒否されました" in content or "Forbidden" in content:
        print(f"  [ikyu] {year}/{month:02d} ボット検知でブロック")
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        debug_file = DEBUG_DIR / f"ikyu_{year}{month:02d}.html"
        debug_file.write_text(content, encoding="utf-8")
        return prices

    # ② HTML内の正規表現
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

    # ③ DOMセレクタ（6種類）
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
    debug_file = DEBUG_DIR / f"ikyu_{year}{month:02d}.html"
    debug_file.write_text(content, encoding="utf-8")
    print(f"  [debug] No prices found, saved HTML → {debug_file}")

    return prices


async def scrape_ikyu_kamenoi() -> dict[str, int | None]:
    today = date.today()
    end_date = today + timedelta(days=180)
    all_prices: dict[str, int | None] = {}

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

        # セッション確立のためトップページを先に訪問
        print("  [ikyu] セッション確立中...")
        await _warm_up_session(page)

        blocked_count = 0
        for offset in range(7):
            first = (today.replace(day=1) + timedelta(days=32 * offset)).replace(day=1)
            print(f"  [ikyu] {first.year}/{first.month:02d} 取得中...")
            monthly = await _scrape_month(page, first.year, first.month)
            print(f"  [ikyu] {first.year}/{first.month:02d} → {len(monthly)} 件")
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
        d: v
        for d, v in all_prices.items()
        if today.isoformat() <= d <= end_date.isoformat()
    }
