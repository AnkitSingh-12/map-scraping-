"""Pydantic models shared across the app."""
from typing import Optional, List
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Incoming user query, e.g. 'IT companies in Mohali'."""
    query: str = Field(..., min_length=2, examples=["IT companies in Mohali"])
    max_results: Optional[int] = Field(None, ge=1, le=120)
    enrich: Optional[bool] = None


class ParsedQuery(BaseModel):
    """Output of the AI agent layer."""
    category: str = Field(..., description="Business category, e.g. 'IT companies'")
    location: str = Field(..., description="City / area, e.g. 'Mohali'")
    search_term: str = Field(..., description="Phrase to type into Google Maps")


class Company(BaseModel):
    """A single discovered company."""
    name: str
    maps_url: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    category: Optional[str] = None
    rating: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    parsed: ParsedQuery
    count: int
    results: List[Company]
