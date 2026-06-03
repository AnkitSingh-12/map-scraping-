"""Query parser layer (rule-based).

Parses a free-text user request to extract search category and location using regex.
"""
import re

from .models import ParsedQuery


def understand_query(query: str) -> ParsedQuery:
    """Parse a free-text query into a structured search using rules (category + location)."""
    location = ""
    category = query
    m = re.search(r"\b(?:in|at|near|around)\s+(.+)$", query, flags=re.IGNORECASE)
    if m:
        location = m.group(1).strip(" .?")
        category = query[: m.start()].strip()
    category = re.sub(r"^(show me|find|list|get|search)\s+", "", category, flags=re.IGNORECASE).strip()
    category = re.sub(r"^(the)\s+", "", category, flags=re.IGNORECASE).strip()
    category = category or "businesses"
    search_term = f"{category} in {location}".strip() if location else category
    return ParsedQuery(category=category, location=location, search_term=search_term)
