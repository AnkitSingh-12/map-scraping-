"""Google Maps scraper using Playwright (no API key required).

Strategy:
  1. Open https://www.google.com/maps/search/<term>
  2. Scroll the results feed until enough place links are loaded.
  3. Open each place panel and read name, address, phone, website, etc.

Google Maps markup changes over time. Selectors below use the most
stable hooks available (data-item-id, aria-label, role=feed). Each
extraction is wrapped defensively so one bad card never aborts the run.
"""
import asyncio
import re
from typing import List, Callable, Optional
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, Page, TimeoutError as PWTimeout

from .config import settings
from .models import Company
from .validation import dedupe_key

CONSENT_BUTTON_SELECTORS = [
    "button[aria-label='Accept all']",
    "button[aria-label='Reject all']",
    "form[action*='consent'] button",
    "button:has-text('Accept all')",
    "button:has-text('I agree')",
]


def _maps_search_url(term: str) -> str:
    return f"https://www.google.com/maps/search/{quote_plus(term)}?hl=en"


async def _dismiss_consent(page: Page) -> None:
    for sel in CONSENT_BUTTON_SELECTORS:
        try:
            btn = page.locator(sel).first
            if await btn.count() and await btn.is_visible():
                await btn.click(timeout=3000)
                await page.wait_for_timeout(1000)
                return
        except Exception:
            continue


async def _collect_place_urls(page: Page, want: int, log: Callable[[str], None]) -> List[str]:
    """Scroll the results feed and gather unique /maps/place/ links."""
    feed_sel = "div[role='feed']"
    try:
        await page.wait_for_selector(feed_sel, timeout=15000)
    except PWTimeout:
        log("Results feed did not appear — query may have 0 results.")
        return []

    urls: List[str] = []
    seen = set()
    stagnant = 0
    for _ in range(40):  # hard cap on scroll iterations
        anchors = page.locator(f"{feed_sel} a[href*='/maps/place/']")
        n = await anchors.count()
        for i in range(n):
            href = await anchors.nth(i).get_attribute("href")
            if href and href not in seen:
                seen.add(href)
                urls.append(href)
        log(f"Found {len(urls)} places so far...")
        if len(urls) >= want:
            break
        # Scroll the feed to load more.
        await page.evaluate(
            "(s) => { const f = document.querySelector(s); if (f) f.scrollBy(0, f.scrollHeight); }",
            feed_sel,
        )
        await page.wait_for_timeout(1800)
        # Detect end-of-list.
        end = await page.locator("text=You've reached the end of the list").count()
        if end:
            break
        if await anchors.count() == n:
            stagnant += 1
            if stagnant >= 3:
                break
        else:
            stagnant = 0
    return urls[:want]


def _clean_phone(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    raw = re.sub(r"^(Phone:|Phone)\s*", "", raw, flags=re.IGNORECASE).strip()
    return raw or None


async def _attr_or_text(page: Page, selector: str, attr: Optional[str] = None) -> Optional[str]:
    try:
        loc = page.locator(selector).first
        if not await loc.count():
            return None
        val = await loc.get_attribute(attr) if attr else (await loc.inner_text())
        return val.strip() if val else None
    except Exception:
        return None


async def _scrape_place(page: Page, url: str) -> Optional[Company]:
    """Open a place URL and extract its details from the side panel."""
    try:
        await page.goto(url, timeout=settings.scrape_timeout_ms, wait_until="domcontentloaded")
        await page.wait_for_selector("h1", timeout=12000)
        await page.wait_for_timeout(800)
    except Exception:
        return None

    name = await _attr_or_text(page, "h1")
    if not name:
        return None

    # Website: the "authority" action button links to the site.
    website = await _attr_or_text(page, "a[data-item-id='authority']", attr="href")
    if not website:
        website = await _attr_or_text(page, "a[aria-label^='Website']", attr="href")

    # Phone: button data-item-id starts with 'phone:tel:'
    phone = await _attr_or_text(page, "button[data-item-id^='phone:tel:']", attr="aria-label")
    phone = _clean_phone(phone)
    if not phone:
        di = await _attr_or_text(page, "button[data-item-id^='phone:tel:']", attr="data-item-id")
        if di:
            phone = di.split("phone:tel:")[-1]

    # Address.
    address = await _attr_or_text(page, "button[data-item-id='address']", attr="aria-label")
    if address:
        address = re.sub(r"^Address:\s*", "", address).strip()

    # Category & rating (best-effort).
    category = await _attr_or_text(page, "button[jsaction*='category']")
    rating = await _attr_or_text(page, "div.F7nice span[aria-hidden='true']")

    return Company(
        name=name,
        maps_url=url,
        website=website,
        phone=phone,
        address=address,
        category=category,
        rating=rating,
    )


async def scrape_maps(
    search_term: str,
    max_results: int,
    log: Callable[[str], None] = lambda m: None,
) -> List[Company]:
    """Main entry point: scrape Google Maps for `search_term`."""
    results: List[Company] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=settings.headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            locale="en-US",
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        try:
            log(f"Opening Google Maps for '{search_term}'...")
            await page.goto(_maps_search_url(search_term), timeout=settings.scrape_timeout_ms,
                            wait_until="domcontentloaded")
            await _dismiss_consent(page)

            # Over-fetch a generous candidate pool: some place pages fail to
            # extract and some are duplicates, so collecting exactly
            # `max_results` links would leave us short. We scrape from the pool
            # and stop once we have `max_results` unique companies.
            pool_target = max(max_results * 3, max_results + 10)
            urls = await _collect_place_urls(page, pool_target, log)
            log(f"Collected {len(urls)} place links. Extracting up to {max_results} companies...")

            seen_keys: set = set()
            for url in urls:
                if len(results) >= max_results:
                    break
                company = await _scrape_place(page, url)
                if not company:
                    continue  # could not read this card — try the next one
                key = dedupe_key(company)
                if key in seen_keys:
                    continue  # duplicate of one we already have — skip
                seen_keys.add(key)
                results.append(company)
                log(f"[{len(results)}/{max_results}] {company.name}")

            if len(results) < max_results:
                log(f"Only {len(results)} unique places available for this search "
                    f"(requested {max_results}).")
        finally:
            await context.close()
            await browser.close()
    return results


def scrape_maps_sync(search_term: str, max_results: int,
                     log: Callable[[str], None] = lambda m: None) -> List[Company]:
    """Synchronous wrapper for use outside an event loop."""
    return asyncio.run(scrape_maps(search_term, max_results, log))
