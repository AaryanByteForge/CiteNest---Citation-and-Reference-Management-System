"""
ReferenceValidator Module for CiteNest.
Implements strict per-type validation rules according to Annex A FR-007 and UC-004.
"""

from typing import Dict, Any, Tuple
import re
from models import ReferenceType


class ReferenceValidator:
    """
    Validates Reference fields according to type-specific rules.
    Returns (is_valid: bool, errors: dict[str, str]).
    """

    @staticmethod
    def validate(data: Dict[str, Any]) -> Tuple[bool, Dict[str, str]]:
        errors: Dict[str, str] = {}
        ref_type = data.get("type")

        # Basic type validation
        if not ref_type:
            errors["type"] = "Reference type is required."
            return False, errors

        # Universal requirements
        title = (data.get("title") or "").strip()
        if not title:
            errors["title"] = "Title is required for all reference types."

        year = str(data.get("year") or "").strip()
        if not year:
            errors["year"] = "Publication year is required."
        elif not re.match(r"^\d{4}$", year) and not re.match(r"^\d{4}\s*[-–]\s*\d{4}$", year):
            # Allow 4-digit years or year ranges like 2024 or 2020-2022
            # Also allow n.d. if explicitly requested, but standard is numeric year
            if not year.lower() in ["n.d.", "in press"]:
                errors["year"] = "Year must be a 4-digit year (e.g., 2024) or 'n.d.'."

        # Type-specific requirements
        if ref_type == ReferenceType.JOURNAL_ARTICLE or ref_type == "Journal Article":
            authors = (data.get("authors") or "").strip()
            if not authors:
                errors["authors"] = "Author(s) are required for Journal Articles."

            journal_name = (data.get("journalName") or "").strip()
            if not journal_name:
                errors["journalName"] = "Journal Name is required for Journal Articles."

        elif ref_type == ReferenceType.BOOK or ref_type == "Book":
            authors = (data.get("authors") or "").strip()
            if not authors:
                errors["authors"] = "Author(s) are required for Books."

            publisher = (data.get("publisher") or "").strip()
            if not publisher:
                errors["publisher"] = "Publisher is required for Books."

        elif ref_type == ReferenceType.WEBSITE or ref_type == "Website":
            authors = (data.get("authors") or "").strip()
            site_name = (data.get("siteName") or "").strip()
            if not authors and not site_name:
                errors["authors"] = "Either Author(s) or Site Name is required for Websites."
                errors["siteName"] = "Either Author(s) or Site Name is required for Websites."

            url = (data.get("url") or "").strip()
            if not url:
                errors["url"] = "URL is required for Websites."
            elif not (url.startswith("http://") or url.startswith("https://") or "://" in url):
                errors["url"] = "URL must start with http:// or https://"

            access_date = (data.get("accessDate") or "").strip()
            if not access_date:
                errors["accessDate"] = "Access Date is required for Websites (e.g. YYYY-MM-DD)."

        else:
            errors["type"] = f"Unknown reference type '{ref_type}'."

        return (len(errors) == 0, errors)
