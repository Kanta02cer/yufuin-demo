import asyncio
import calendar
import re
from datetime import date, timedelta
from pathlib import Path
from playwright.async_api import async_playwright

DEBUG_DIR = Path(__file__).parent.parent / "data" / "debug"

HOTELS = {
    "kai_yufuin": {
        "name": "界 由布院",
        "yadNo": "360321",
        "planCd": "03416947",
        "roomTypeCd": "0518226",
    },
    "enowa_yufuin": {
        "name": "ENOWA YUFUIN",
        "yadNo": "350146",
        "planCd": None,
        "roomTypeCd": None,
    },
}

LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
]


def _extract_prices_from_json(obj, prices: dict, year: int, month: int):
    """JSONオブジェクトを再帰的に探索してdate+priceペアを抽出"""
    if isinstance(obj, dict):
        stay = (
            obj.get("stayDate") or obj.get("date") or obj.get("ymd") or obj.get("checkInDate")
        )
        price = (
            obj.get("price") or obj.get("minPrice") or obj.get("planPrice")
            or obj.get("amount") or obj.get("noSrvTotalPrice")
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


def _extract_from_jalan_page_html(content: str) -> tuple[str | None, int | None]:
    """じゃらんnet 計画詳細ページから noSrvTotalPrice + searchCondition の日付を抽出"""
    price_m = re.search(r'"noSrvTotalPrice"\s*:\s*"(\d+)"', content)
    year_m = re.search(r'"stayYear"\s*:\s*"(\d{4})"', content)
    month_m = re.search(r'"stayMonth"\s*:\s*"(\d+)"', content)
    day_m = re.search(r'"stayDay"\s*:\s*"(\d+)"', content)
    if price_m and year_m and month_m and day_m:
        try:
            d = date(int(year_m.group(1)), int(month_m.group(1)), int(day_m.group(1)))
            return d.isoformat(), int(price_m.group(1))
        except ValueError:
            pass
    return None, None


async def _discover_plan(page, hotel_key: str) -> tuple[str | None, str | None]:
    hotel = HOTELS[hotel_key]
    url = (
        f"https://www.jalan.net/yad{hotel['yadNo']}/plan/"
        f"?screenId=UWW3001&yadNo={hotel['yadNo']}&smlCd=440602&distCd=01"
    )
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(4000)

    content = await page.content()
    matches = re.findall(r"planCd=(\w+)[^\"' ]*roomTypeCd=(\w+)", content)
    if matches:
        return matches[0]

    links = await page.query_selector_all("a[href*='planCd']")
    for link in links:
        href = await link.get_attribute("href") or ""
        plan_m = re.search(r"planCd=(\w+)", href)
        room_m = re.search(r"roomTypeCd=(\w+)", href)
        if plan_m and room_m:
            return plan_m.group(1), room_m.group(1)

    return None, None


async def _get_monthly_prices(
    page, yadNo: str, planCd: str, roomTypeCd: str, year: int, month: int
) -> dict[str, int]:
    prices: dict[str, int] = {}
    intercepted: list[dict] = []

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
        f"https://www.jalan.net/uw/uwp3200/uww3201init.do"
        f"?stayYear={year}&stayMonth={month:02d}&stayDay=01"
        f"&yadNo={yadNo}&stayCount=1&roomCount=1&adultNum=2"
        f"&distCd=01&smlCd=440602&roomCrack=200000"
        f"&planCd={planCd}&roomTypeCd={roomTypeCd}"
        f"&screenId=UWW3101"
    )
    await page.goto(url, wait_until="networkidle", timeout=45000)

    page.remove_listener("response", handle_response)

    # ① XHR傍受で取得したJSONを解析（月全体のカレンダーデータが取れることがある）
    for body in intercepted:
        _extract_prices_from_json(body, prices, year, month)
    if len(prices) > 5:
        return prices

    # ② ページHTML内の noSrvTotalPrice + searchCondition パターン（1日分）
    content = await page.content()
    ds, price_val = _extract_from_jalan_page_html(content)
    if ds and price_val:
        prices[ds] = price_val

    # ③ 既存の正規表現パターン
    for pattern in [
        r'"stayDate"\s*:\s*"(\d{4}[/\-]\d{2}[/\-]\d{2})"[^}]{0,400}"(?:price|noSrvTotalPrice)"\s*:\s*"?(\d+)"?',
        r'"date"\s*:\s*"(\d{4}[/\-]\d{2}[/\-]\d{2})"[^}]{0,300}"price"\s*:\s*(\d+)',
        r'"ymd"\s*:\s*"(\d{4}[/\-]\d{2}[/\-]\d{2})"[^}]{0,300}"price"\s*:\s*(\d+)',
    ]:
        for m in re.finditer(pattern, content):
            raw = m.group(1).replace("/", "-")
            try:
                d = date.fromisoformat(raw)
                if d.year == year and d.month == month:
                    prices[raw] = int(m.group(2).replace(",", ""))
            except (ValueError, IndexError):
                pass
        if len(prices) > 5:
            return prices

    # ④ DOMセレクタ
    for sel in [
        "td[data-date]", "[data-ymd]", "[data-checkin]",
        "[class*='calendar'] td", "[class*='Calendar'] td", ".planCalendarList td",
    ]:
        cells = await page.query_selector_all(sel)
        for cell in cells:
            raw_date = (
                await cell.get_attribute("data-date")
                or await cell.get_attribute("data-ymd")
            )
            text = await cell.inner_text()
            price_m = re.search(r"([1-9][0-9,]{4,})", text)
            if price_m:
                price_v = int(price_m.group(1).replace(",", ""))
                if raw_date:
                    key = raw_date[:10].replace("/", "-")
                    try:
                        date.fromisoformat(key)
                        prices[key] = price_v
                    except ValueError:
                        pass
        if len(prices) > 5:
            return prices

    # ⑤ フォールバック: 日別ループ（XHRで月全体が取れなかった場合）
    print(f"  [jalan/{yadNo}] XHR不発、日別ループに切替 {year}/{month:02d}")
    _, days_in_month = calendar.monthrange(year, month)
    today_d = date.today()
    for day in range(1, days_in_month + 1):
        target = date(year, month, day)
        if target < today_d:
            continue
        day_url = (
            f"https://www.jalan.net/uw/uwp3200/uww3201init.do"
            f"?stayYear={year}&stayMonth={month:02d}&stayDay={day:02d}"
            f"&yadNo={yadNo}&stayCount=1&roomCount=1&adultNum=2"
            f"&distCd=01&smlCd=440602&roomCrack=200000"
            f"&planCd={planCd}&roomTypeCd={roomTypeCd}"
            f"&screenId=UWW3101"
        )
        try:
            await page.goto(day_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1500)
            day_html = await page.content()
            ds2, pv2 = _extract_from_jalan_page_html(day_html)
            if ds2 and pv2:
                prices[ds2] = pv2
        except Exception as e:
            print(f"  [jalan/{yadNo}] {target} skip: {e}")
        await asyncio.sleep(1)

    if not prices:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        debug_file = DEBUG_DIR / f"jalan_{yadNo}_{year}{month:02d}.html"
        debug_file.write_text(content, encoding="utf-8")
        print(f"  [debug] No prices found, saved HTML → {debug_file}")

    return prices


async def scrape_jalan_hotel(hotel_key: str) -> dict[str, int | None]:
    hotel = HOTELS[hotel_key]
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
            viewport={"width": 1280, "height": 800},
            locale="ja-JP",
            extra_http_headers={
                "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            },
        )
        await context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = await context.new_page()

        plan_cd = hotel["planCd"]
        room_type_cd = hotel["roomTypeCd"]

        if plan_cd is None:
            print(f"  [{hotel_key}] planCd 探索中...")
            plan_cd, room_type_cd = await _discover_plan(page, hotel_key)
            if plan_cd:
                HOTELS[hotel_key]["planCd"] = plan_cd
                HOTELS[hotel_key]["roomTypeCd"] = room_type_cd
                print(f"  [{hotel_key}] planCd={plan_cd} roomTypeCd={room_type_cd}")
            else:
                print(f"  [{hotel_key}] planCd not found, skipping")
                await browser.close()
                return {}

        for offset in range(7):
            first = (today.replace(day=1) + timedelta(days=32 * offset)).replace(day=1)
            print(f"  [{hotel_key}] {first.year}/{first.month:02d} 取得中...")
            monthly = await _get_monthly_prices(
                page, hotel["yadNo"], plan_cd, room_type_cd, first.year, first.month
            )
            print(f"  [{hotel_key}] {first.year}/{first.month:02d} → {len(monthly)} 件")
            all_prices.update(monthly)
            await asyncio.sleep(2)

        await browser.close()

    return {
        d: v
        for d, v in all_prices.items()
        if today.isoformat() <= d <= end_date.isoformat()
    }
