"""Website Enrichment Service.

For each company that has a website, fetch the homepage plus common
contact/about pages and extract the first plausible email address.
"""
import asyncio
import re
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .config import settings
from .models import Company

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
CONTACT_PATHS = ["", "contact", "contact-us", "contactus", "about", "about-us", "support"]
# Skip junk / image-bait addresses.
BAD_EMAIL_HINTS = ("example.com", "sentry.io", "wixpress.com", ".png", ".jpg", ".gif", ".webp")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def _pick_email(candidates: List[str], domain: Optional[str]) -> Optional[str]:
    cleaned = []
    for e in candidates:
        el = e.lower().strip(".,;:")
        if any(h in el for h in BAD_EMAIL_HINTS):
            continue
        cleaned.append(el)
    if not cleaned:
        return None
    # Prefer an address on the company's own domain.
    if domain:
        for e in cleaned:
            if e.endswith("@" + domain) or e.endswith("." + domain):
                return e
    # Prefer info@/contact@/sales@.
    for prefix in ("info@", "contact@", "sales@", "hello@", "enquiry@", "support@"):
        for e in cleaned:
            if e.startswith(prefix):
                return e
    return cleaned[0]


async def _fetch(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        r = await client.get(url, timeout=12.0, follow_redirects=True)
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            return r.text
    except Exception:
        return None
    return None


def _extract_emails(html: str) -> List[str]:
    emails = set(EMAIL_RE.findall(html))
    # Also catch mailto: links explicitly.
    soup = BeautifulSoup(html, "lxml")
    for a in soup.select("a[href^='mailto:']"):
        addr = a.get("href", "")[7:].split("?")[0]
        if addr:
            emails.add(addr)
    return list(emails)


async def _enrich_one(client: httpx.AsyncClient, company: Company) -> Company:
    if not company.website:
        return company
    base = company.website
    domain = urlparse(base).netloc.replace("www.", "")
    found: List[str] = []
    for path in CONTACT_PATHS:
        url = urljoin(base if base.endswith("/") else base + "/", path)
        html = await _fetch(client, url)
        if html:
            found.extend(_extract_emails(html))
        if found and path in ("contact", "contact-us"):
            break  # contact page is the best source; stop early
    email = _pick_email(found, domain)
    if email:
        company.email = email
    return company


async def enrich_companies(companies: List[Company]) -> List[Company]:
    if not settings.enrich_websites:
        return companies
    async with httpx.AsyncClient(headers=HEADERS) as client:
        sem = asyncio.Semaphore(6)

        async def bound(c: Company) -> Company:
            async with sem:
                try:
                    return await _enrich_one(client, c)
                except Exception:
                    return c

        return await asyncio.gather(*(bound(c) for c in companies))
