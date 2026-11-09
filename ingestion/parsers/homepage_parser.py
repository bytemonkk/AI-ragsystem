
"""Specialized content extraction for the CBIT homepage."""

import re
from bs4 import BeautifulSoup

from ingestion.parsers.html_parser import (
    normalize_text,
    clean_page,
    extract_table,
)


REMOVE_SELECTORS = [
    ".cookie-notice",
    ".cookie-banner",
    ".modal",
    ".popup",
    ".enquiry-form",
    ".social-links",
    ".quick-links",
    "[aria-label='Close']",
]


def parse_homepage(content: str) -> tuple[str, str]:
    """Extract meaningful homepage text for document indexing."""

    soup = BeautifulSoup(content, "html.parser")

    title = (
        soup.title.get_text(" ", strip=True)
        if soup.title
        else "CBIT Homepage"
    )

    clean_page(soup)

    for selector in REMOVE_SELECTORS:
        for element in soup.select(selector):
            element.decompose()

    root = soup.select_one("main") or soup.body or soup

    for table in list(root.find_all("table")):
        table.replace_with(
            soup.new_string(
                "\n" + extract_table(table) + "\n"
            )
        )

    text = root.get_text(" ", strip=True)

    # Remove repeated presentation-only labels.
    text = re.sub(
        r"\bRead\s+More\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # Remove generic CTAs, not content.
    text = re.sub(
        r"\bOrder a prospectus\s+"
        r"Book an open day\s+Apply Now\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    return normalize_text(title), normalize_text(text)