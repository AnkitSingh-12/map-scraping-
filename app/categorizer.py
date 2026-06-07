"""Automaton Layer for Company Categorization.

This module uses a Trie-based keyword matching search automaton (Aho-Corasick style keyword tree)
to automatically classify scraped companies into structured industry categories based on
their name, raw Google Maps category, and website URL.
"""
from typing import Dict, List, Optional
from .models import Company


class TrieNode:
    def __init__(self):
        self.children: Dict[str, TrieNode] = {}
        # Stores list of (category_name, weight)
        self.output: List[tuple[str, int]] = []


class CategorizationAutomaton:
    """Trie-based keyword matching automaton for classifying companies."""

    def __init__(self):
        self.root = TrieNode()
        self._build_trie()

    def _add_keyword(self, keyword: str, category: str, weight: int = 1):
        """Insert a keyword into the Trie."""
        node = self.root
        # Normalize keyword to lowercase words/chars
        normalized = keyword.lower().strip()
        for char in normalized:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
        node.output.append((category, weight))

    def _build_trie(self):
        # Category Definitions with matching keywords
        categories = {
            "IT & Software": [
                "software", "it services", "developer", "web development", 
                "app development", "information technology", "tech", "technology", 
                "coder", "coding", "programming", "networks", "cloud", "consultant",
                "web design", "systems", "cybersecurity", "saas", "hardware"
            ],
            "Digital Marketing & SEO": [
                "marketing", "seo", "search engine", "ad agency", "advertising", 
                "branding", "social media", "digital agency", "pr agency", "promotions"
            ],
            "Healthcare & Dentistry": [
                "dentist", "dental", "clinic", "hospital", "doctor", "medical", 
                "physio", "healthcare", "pharmacy", "therapist", "pediatrician", 
                "orthopedics", "surgeon", "nursing", "wellness"
            ],
            "Education & Training": [
                "school", "college", "university", "coaching", "training", 
                "academy", "tutor", "education", "institute", "learning", "classes"
            ],
            "Real Estate & Construction": [
                "real estate", "builder", "developer", "construction", "properties", 
                "broker", "architect", "interior design", "housing", "apartments"
            ],
            "Food & Hospitality": [
                "restaurant", "cafe", "hotel", "food", "bakery", "catering", 
                "resort", "pub", "bar", "kitchen", "lounge", "diner", "pizzeria"
            ],
            "Financial & Legal Services": [
                "finance", "bank", "accountant", "tax", "insurance", "lawyer", 
                "law firm", "attorney", "auditor", "wealth", "advisory", "legal"
            ],
            "Retail & Wholesale": [
                "store", "shop", "wholesale", "distributor", "clothing", "boutique", 
                "supermarket", "retailer", "mall", "mart", "sales", "grocer"
            ],
            "Automotive": [
                "car", "auto", "garage", "automotive", "dealer", "motorcycle", 
                "tyre", "wheel", "mechanic", "vehicle"
            ],
            "Other Services": [
                "salon", "spa", "cleaning", "courier", "logistics", "laundry", 
                "photographer", "travel", "dry clean", "plumbing", "electrician", 
                "security", "beauty", "fitness", "gym"
            ]
        }

        # Load keywords into Trie
        for category, keywords in categories.items():
            for kw in keywords:
                # Add the base keyword
                self._add_keyword(kw, category, weight=2)
                # Also add singular/plural variations if applicable
                if kw.endswith("y"):
                    self._add_keyword(kw[:-1] + "ies", category, weight=2)
                elif not kw.endswith("s"):
                    self._add_keyword(kw + "s", category, weight=2)

    def search(self, text: str) -> Dict[str, int]:
        """Search the text using the Trie and return category scores."""
        text = text.lower()
        scores: Dict[str, int] = {}

        # Standard sliding window search on Trie
        for i in range(len(text)):
            node = self.root
            for j in range(i, len(text)):
                char = text[j]
                if char not in node.children:
                    break
                node = node.children[char]
                for category, weight in node.output:
                    # To prevent matching substrings of words incorrectly,
                    # check if match has word boundaries around it.
                    start_boundary = (i == 0 or not text[i-1].isalnum())
                    end_boundary = (j == len(text) - 1 or not text[j+1].isalnum())
                    if start_boundary and end_boundary:
                        scores[category] = scores.get(category, 0) + weight

        return scores

    def categorize(self, company: Company) -> str:
        """Determine the best category for a company."""
        # Compile all available descriptive texts
        search_texts = []
        if company.name:
            search_texts.append(company.name)
        if company.category:
            search_texts.append(company.category)
        if company.website:
            # Add domain and path words
            search_texts.append(company.website.replace("http://", "").replace("https://", ""))

        combined_text = " | ".join(search_texts)
        scores = self.search(combined_text)

        if not scores:
            # Fallback: if there was a raw Google Maps category, use that capitalized,
            # otherwise default to "Other"
            if company.category:
                raw = company.category.strip()
                # Simple capitalization
                return raw[0].upper() + raw[1:] if raw else "Other"
            return "Other"

        # Find category with highest score
        best_category = max(scores, key=scores.get)
        return best_category


# Singleton instance of the categorizer automaton
company_categorizer = CategorizationAutomaton()
