"""
Citation Engine and Strategy Pattern Style Formatters for CiteNest.
Implements:
- CitationStyleFormatter (Abstract Strategy)
- APAFormatter
- MLAFormatter
- IEEEFormatter
- CitationEngine (Strategy context & dispatcher)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import re
from models import CitationStyle, ReferenceType


def parse_authors(authors_str: str) -> List[Dict[str, str]]:
    """
    Parses author string into a list of author dicts: [{"last": ..., "first": ...}].
    Handles formats:
    - "Goodfellow, I., Bengio, Y., & Courville, A."
    - "Vaswani, A., Shazeer, N., & Parmar, N."
    - "Smith, John and Doe, Jane"
    - "American Psychological Association" (corporate)
    """
    if not authors_str or not authors_str.strip():
        return []

    cleaned = authors_str.strip()
    # Normalize ampersands and 'and'
    cleaned = re.sub(r"\s+and\s+", ", ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*&\s*", ", ", cleaned)

    # Split by comma or semicolon
    raw_parts = [p.strip() for p in re.split(r";", cleaned) if p.strip()]
    if len(raw_parts) == 1 and "," in raw_parts[0]:
        # Might be "Last, First, Last, First" or "Last, F."
        tokens = [t.strip() for t in raw_parts[0].split(",") if t.strip()]
        # Check if paired (Last, Initials/First)
        if len(tokens) >= 2 and all(len(tokens[i]) <= 4 or "." in tokens[i] for i in range(1, len(tokens), 2)):
            pairs = []
            for i in range(0, len(tokens), 2):
                last = tokens[i]
                first = tokens[i+1] if i+1 < len(tokens) else ""
                pairs.append({"last": last, "first": first})
            return pairs
        elif len(tokens) == 2:
            return [{"last": tokens[0], "first": tokens[1]}]
        else:
            # Fallback or corporate name
            if len(tokens) > 2:
                # Group pairs if possible
                pairs = []
                idx = 0
                while idx < len(tokens):
                    last = tokens[idx]
                    first = tokens[idx+1] if idx+1 < len(tokens) and len(tokens[idx+1]) <= 6 else ""
                    if first:
                        idx += 2
                    else:
                        idx += 1
                    pairs.append({"last": last, "first": first})
                return pairs

    authors = []
    for part in raw_parts:
        if "," in part:
            sub = [s.strip() for s in part.split(",", 1)]
            authors.append({"last": sub[0], "first": sub[1]})
        else:
            # Single word or organization name
            words = part.split()
            if len(words) > 1 and len(words[-1]) > 1:
                # e.g. "John Smith"
                authors.append({"last": words[-1], "first": " ".join(words[:-1])})
            else:
                authors.append({"last": part, "first": ""})

    return authors if authors else [{"last": authors_str.strip(), "first": ""}]


def get_first_author_sort_key(ref: Dict[str, Any]) -> str:
    """Returns sort key for alphabetical bibliography sorting."""
    authors = parse_authors(ref.get("authors") or "")
    if authors:
        return (authors[0].get("last") or "").lower()
    site_name = (ref.get("siteName") or "").strip().lower()
    if site_name:
        return site_name
    return (ref.get("title") or "").strip().lower()


class CitationStyleFormatter(ABC):
    """Abstract Strategy interface for Citation Styles."""

    @abstractmethod
    def format_in_text(self, ref: Dict[str, Any], context: Dict[str, Any]) -> str:
        """
        Formats in-text citation string.
        context can contain: {"ieee_index": int, "pages": str, ...}
        """
        pass

    @abstractmethod
    def format_bibliography_entry(self, ref: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, str]:
        """
        Formats a bibliography entry.
        Returns dict: {"html": ..., "text": ..., "referenceId": ref["referenceId"]}
        """
        pass

    @abstractmethod
    def sort_bibliography(self, entries: List[Dict[str, Any]], refs_by_id: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sorts the bibliography entries list according to the style rules."""
        pass


class APAFormatter(CitationStyleFormatter):
    """
    APA 7th Edition Style Formatter.
    - In-text: (LastName, Year), (LastName1 & LastName2, Year), (FirstAuthor et al., Year)
    - Bibliography: Sorted alphabetically by first author's last name.
    """

    def format_in_text(self, ref: Dict[str, Any], context: Dict[str, Any]) -> str:
        authors = parse_authors(ref.get("authors") or "")
        year = str(ref.get("year") or "n.d.").strip()

        if not authors:
            name = ref.get("siteName") or ref.get("title") or "Unknown"
            if len(name) > 30:
                name = name[:27] + "..."
            return f"({name}, {year})"

        if len(authors) == 1:
            return f"({authors[0]['last']}, {year})"
        elif len(authors) == 2:
            return f"({authors[0]['last']} & {authors[1]['last']}, {year})"
        else:
            return f"({authors[0]['last']} et al., {year})"

    def format_bibliography_entry(self, ref: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, str]:
        ref_type = ref.get("type")
        authors_raw = (ref.get("authors") or "").strip()
        year = str(ref.get("year") or "n.d.").strip()
        title = (ref.get("title") or "").strip()

        # Format Author string: Last, F. M., & Last, F. M.
        author_display = authors_raw
        parsed = parse_authors(authors_raw)
        if parsed:
            formatted_authors = []
            for a in parsed:
                if a.get("first"):
                    formatted_authors.append(f"{a['last']}, {a['first']}")
                else:
                    formatted_authors.append(a['last'])
            if len(formatted_authors) == 1:
                author_display = formatted_authors[0]
            elif len(formatted_authors) == 2:
                author_display = f"{formatted_authors[0]} & {formatted_authors[1]}"
            else:
                author_display = ", ".join(formatted_authors[:-1]) + ", & " + formatted_authors[-1]

        if not author_display:
            author_display = (ref.get("siteName") or ref.get("title") or "").strip()

        if not author_display.endswith("."):
            author_display += "."

        if ref_type == ReferenceType.JOURNAL_ARTICLE or ref_type == "Journal Article":
            journal = (ref.get("journalName") or "").strip()
            vol_issue = (ref.get("volumeIssue") or "").strip()
            pages = (ref.get("pages") or "").strip()

            journal_part_html = f"<i>{journal}</i>"
            journal_part_text = journal
            if vol_issue:
                journal_part_html += f", {vol_issue}"
                journal_part_text += f", {vol_issue}"
            if pages:
                journal_part_html += f", {pages}"
                journal_part_text += f", {pages}"

            html = f"{author_display} ({year}). {title}. {journal_part_html}."
            text = f"{author_display} ({year}). {title}. {journal_part_text}."

        elif ref_type == ReferenceType.BOOK or ref_type == "Book":
            publisher = (ref.get("publisher") or "").strip()
            edition = (ref.get("editionPlace") or "").strip()
            edition_str = f" ({edition})" if edition else ""

            html = f"{author_display} ({year}). <i>{title}</i>{edition_str}. {publisher}."
            text = f"{author_display} ({year}). {title}{edition_str}. {publisher}."

        elif ref_type == ReferenceType.WEBSITE or ref_type == "Website":
            site_name = (ref.get("siteName") or "").strip()
            access_date = (ref.get("accessDate") or "").strip()
            url = (ref.get("url") or "").strip()
            site_part = f" {site_name}." if site_name else ""

            html = f"{author_display} ({year}). {title}.{site_part} Retrieved {access_date}, from <a href='{url}' target='_blank'>{url}</a>"
            text = f"{author_display} ({year}). {title}.{site_part} Retrieved {access_date}, from {url}"

        else:
            html = f"{author_display} ({year}). {title}."
            text = f"{author_display} ({year}). {title}."

        return {
            "referenceId": ref.get("referenceId", ""),
            "html": html,
            "text": text,
            "style": "APA"
        }

    def sort_bibliography(self, entries: List[Dict[str, Any]], refs_by_id: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        # APA is sorted alphabetically by first author's last name
        return sorted(entries, key=lambda e: get_first_author_sort_key(refs_by_id.get(e["referenceId"], {})))


class MLAFormatter(CitationStyleFormatter):
    """
    MLA 9th Edition Style Formatter.
    - In-text: (LastName) or (LastName Pages) / (FirstAuthor et al. Pages)
    - Bibliography: Sorted alphabetically by author's last name.
    """

    def format_in_text(self, ref: Dict[str, Any], context: Dict[str, Any]) -> str:
        authors = parse_authors(ref.get("authors") or "")
        pages = context.get("pages") or (ref.get("pages") or "").split("-")[0].strip()

        page_suffix = f" {pages}" if pages else ""

        if not authors:
            name = ref.get("siteName") or ref.get("title") or "Unknown"
            if len(name) > 25:
                name = name[:22] + "..."
            return f"({name}{page_suffix})"

        if len(authors) == 1:
            return f"({authors[0]['last']}{page_suffix})"
        elif len(authors) == 2:
            return f"({authors[0]['last']} and {authors[1]['last']}{page_suffix})"
        else:
            return f"({authors[0]['last']} et al.{page_suffix})"

    def format_bibliography_entry(self, ref: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, str]:
        ref_type = ref.get("type")
        authors_raw = (ref.get("authors") or "").strip()
        year = str(ref.get("year") or "").strip()
        title = (ref.get("title") or "").strip()

        parsed = parse_authors(authors_raw)
        author_display = authors_raw
        if parsed:
            if len(parsed) == 1:
                first = f", {parsed[0]['first']}" if parsed[0]['first'] else ""
                author_display = f"{parsed[0]['last']}{first}"
            elif len(parsed) == 2:
                f1 = f", {parsed[0]['first']}" if parsed[0]['first'] else ""
                f2 = f"{parsed[1]['first']} " if parsed[1]['first'] else ""
                author_display = f"{parsed[0]['last']}{f1}, and {f2}{parsed[1]['last']}"
            else:
                first = f", {parsed[0]['first']}" if parsed[0]['first'] else ""
                author_display = f"{parsed[0]['last']}{first}, et al"

        if not author_display:
            author_display = (ref.get("siteName") or "").strip()

        if author_display and not author_display.endswith("."):
            author_display += "."

        prefix = f"{author_display} " if author_display else ""

        if ref_type == ReferenceType.JOURNAL_ARTICLE or ref_type == "Journal Article":
            journal = (ref.get("journalName") or "").strip()
            vol_issue = (ref.get("volumeIssue") or "").strip()
            pages = (ref.get("pages") or "").strip()

            container_html = f"<i>{journal}</i>"
            container_text = journal
            if vol_issue:
                container_html += f", {vol_issue}"
                container_text += f", {vol_issue}"
            if year:
                container_html += f", {year}"
                container_text += f", {year}"
            if pages:
                container_html += f", pp. {pages}"
                container_text += f", pp. {pages}"

            html = f"{prefix}\"{title}.\" {container_html}."
            text = f"{prefix}\"{title}.\" {container_text}."

        elif ref_type == ReferenceType.BOOK or ref_type == "Book":
            publisher = (ref.get("publisher") or "").strip()
            edition = (ref.get("editionPlace") or "").strip()
            ed_part = f"{edition}, " if edition else ""

            html = f"{prefix}<i>{title}</i>. {ed_part}{publisher}, {year}."
            text = f"{prefix}{title}. {ed_part}{publisher}, {year}."

        elif ref_type == ReferenceType.WEBSITE or ref_type == "Website":
            site_name = (ref.get("siteName") or "").strip()
            access_date = (ref.get("accessDate") or "").strip()
            url = (ref.get("url") or "").strip()
            site_html = f"<i>{site_name}</i>, " if site_name else ""
            site_text = f"{site_name}, " if site_name else ""

            html = f"{prefix}\"{title}.\" {site_html}{year}, <a href='{url}' target='_blank'>{url}</a>. Accessed {access_date}."
            text = f"{prefix}\"{title}.\" {site_text}{year}, {url}. Accessed {access_date}."

        else:
            html = f"{prefix}\"{title}.\" {year}."
            text = f"{prefix}\"{title}.\" {year}."

        return {
            "referenceId": ref.get("referenceId", ""),
            "html": html,
            "text": text,
            "style": "MLA"
        }

    def sort_bibliography(self, entries: List[Dict[str, Any]], refs_by_id: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        # MLA is sorted alphabetically by first author's last name
        return sorted(entries, key=lambda e: get_first_author_sort_key(refs_by_id.get(e["referenceId"], {})))


class IEEEFormatter(CitationStyleFormatter):
    """
    IEEE Style Formatter.
    - In-text: [1], [2], ... based on appearance order in the document text.
    - Bibliography: Ordered numerically [1], [2], ... in order of appearance.
    """

    def format_in_text(self, ref: Dict[str, Any], context: Dict[str, Any]) -> str:
        idx = context.get("ieee_index", 1)
        return f"[{idx}]"

    def format_bibliography_entry(self, ref: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, str]:
        idx = context.get("ieee_index", 1)
        ref_type = ref.get("type")
        authors_raw = (ref.get("authors") or "").strip()
        year = str(ref.get("year") or "").strip()
        title = (ref.get("title") or "").strip()

        parsed = parse_authors(authors_raw)
        author_display = authors_raw
        if parsed:
            parts = []
            for a in parsed:
                initials = f"{a['first'][0]}. " if a.get("first") else ""
                parts.append(f"{initials}{a['last']}")
            if len(parts) == 1:
                author_display = parts[0]
            elif len(parts) == 2:
                author_display = f"{parts[0]} and {parts[1]}"
            elif len(parts) > 2:
                author_display = f"{parts[0]} et al."

        if not author_display:
            author_display = (ref.get("siteName") or "").strip()

        prefix = f"[{idx}] {author_display}, " if author_display else f"[{idx}] "

        if ref_type == ReferenceType.JOURNAL_ARTICLE or ref_type == "Journal Article":
            journal = (ref.get("journalName") or "").strip()
            vol_issue = (ref.get("volumeIssue") or "").strip()
            pages = (ref.get("pages") or "").strip()

            j_details_html = f"<i>{journal}</i>"
            j_details_text = journal
            if vol_issue:
                j_details_html += f", {vol_issue}"
                j_details_text += f", {vol_issue}"
            if pages:
                j_details_html += f", pp. {pages}"
                j_details_text += f", pp. {pages}"
            if year:
                j_details_html += f", {year}"
                j_details_text += f", {year}"

            html = f"{prefix}\"{title},\" {j_details_html}."
            text = f"{prefix}\"{title},\" {j_details_text}."

        elif ref_type == ReferenceType.BOOK or ref_type == "Book":
            publisher = (ref.get("publisher") or "").strip()
            edition = (ref.get("editionPlace") or "").strip()
            ed_part = f"{edition}. " if edition else ""

            html = f"{prefix}<i>{title}</i>, {ed_part}{publisher}, {year}."
            text = f"{prefix}{title}, {ed_part}{publisher}, {year}."

        elif ref_type == ReferenceType.WEBSITE or ref_type == "Website":
            site_name = (ref.get("siteName") or "").strip()
            access_date = (ref.get("accessDate") or "").strip()
            url = (ref.get("url") or "").strip()
            site_part = f"<i>{site_name}</i>, " if site_name else ""
            site_text = f"{site_name}, " if site_name else ""

            html = f"{prefix}\"{title},\" {site_part}{year}. [Online]. Available: <a href='{url}' target='_blank'>{url}</a>. [Accessed: {access_date}]."
            text = f"{prefix}\"{title},\" {site_text}{year}. [Online]. Available: {url}. [Accessed: {access_date}]."

        else:
            html = f"{prefix}\"{title},\" {year}."
            text = f"{prefix}\"{title},\" {year}."

        return {
            "referenceId": ref.get("referenceId", ""),
            "html": html,
            "text": text,
            "style": "IEEE",
            "index": idx
        }

    def sort_bibliography(self, entries: List[Dict[str, Any]], refs_by_id: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        # IEEE is ordered numerically [1], [2], ... based on appearance index
        return sorted(entries, key=lambda e: e.get("index", 9999))


class CitationEngine:
    """Strategy Context & Dispatcher for Citation Style Formatting."""

    _formatters: Dict[CitationStyle, CitationStyleFormatter] = {
        CitationStyle.APA: APAFormatter(),
        CitationStyle.MLA: MLAFormatter(),
        CitationStyle.IEEE: IEEEFormatter(),
    }

    @classmethod
    def get_formatter(cls, style: CitationStyle | str) -> CitationStyleFormatter:
        try:
            if isinstance(style, str):
                style_enum = CitationStyle(style)
            else:
                style_enum = style
        except Exception:
            style_enum = CitationStyle.APA

        return cls._formatters.get(style_enum, cls._formatters[CitationStyle.APA])
