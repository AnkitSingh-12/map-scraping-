"""Data Validation Service: dedupe, normalize phones, validate emails/websites."""
from typing import List
from urllib.parse import urlparse

import phonenumbers
from email_validator import validate_email, EmailNotValidError

from .models import Company


def _normalize_phone(raw: str | None, region: str = "IN") -> str | None:
    if not raw:
        return None
    try:
        num = phonenumbers.parse(raw, region)
        if phonenumbers.is_valid_number(num):
            return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    except Exception:
        pass
    return raw.strip()  # keep original if it can't be parsed


def _valid_email(email: str | None) -> str | None:
    if not email:
        return None
    try:
        return validate_email(email, check_deliverability=False).normalized
    except EmailNotValidError:
        return None


def _clean_website(url: str | None) -> str | None:
    if not url:
        return None
    p = urlparse(url)
    if p.scheme in ("http", "https") and p.netloc:
        return url
    return None


def dedupe_key(c: Company) -> str:
    """Stable key for de-duplication: prefer website domain, else name+address."""
    if c.website:
        return urlparse(c.website).netloc.replace("www.", "").lower()
    return f"{c.name.lower().strip()}|{(c.address or '').lower().strip()}"


def validate_companies(companies: List[Company], region: str = "IN") -> List[Company]:
    seen = set()
    out: List[Company] = []
    for c in companies:
        c.phone = _normalize_phone(c.phone, region)
        c.email = _valid_email(c.email)
        c.website = _clean_website(c.website)

        key = dedupe_key(c)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out
