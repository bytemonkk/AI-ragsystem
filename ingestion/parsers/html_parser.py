
import re
from bs4 import BeautifulSoup, Comment


# Repeated website layout elements that are not useful
# for semantic document retrieval.
REMOVE_SELECTORS = [
    "script",
    "style",
    "noscript",
    "iframe",
    "svg",
    "nav",
    "header",
    "footer",
    "[role='navigation']",
    "[role='banner']",
    "[role='contentinfo']",
    ".navbar",
    ".navigation",
    ".main-navigation",
    ".site-header",
    ".site-footer",
    ".breadcrumb",
    ".breadcrumbs",
    ".sidebar",
    ".widget-area",
    ".social-links",
    ".social-icons",
    ".menu-toggle",
    ".share-buttons",
    ".cookie-notice",
    ".cookie-banner",
]


def normalize_text(value: str) -> str:
    """Normalize whitespace without destroying Unicode."""
    value = value.replace("\xa0", " ")
    value = re.sub(r"[\t\r\f\v]+", " ", value)
    value = re.sub(r" {2,}", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def clean_page(soup: BeautifulSoup) -> None:
    """Remove unnecessary layout elements."""

    for comment in soup.find_all(
        string=lambda text: isinstance(text, Comment)
    ):
        comment.extract()

    for selector in REMOVE_SELECTORS:
        for element in soup.select(selector):
            element.decompose()


def extract_table(table) -> str:
    """Preserve table row and column boundaries."""

    rows = []

    for tr in table.find_all("tr"):
        cells = tr.find_all(
            ["th", "td"],
            recursive=False
        )

        values = [
            normalize_text(
                cell.get_text(" ", strip=True)
            )
            for cell in cells
        ]

        if any(values):
            rows.append(" | ".join(values))

    return "\n".join(rows)


def parse_html(content: str) -> tuple[str, str]:
    """
    Extract readable content from a CBIT webpage.

    Returns:
        (page_title, extracted_text)

    Compatible with the existing crawler.
    """

    soup = BeautifulSoup(content, "html.parser")

    title = (
        soup.title.get_text(" ", strip=True)
        if soup.title
        else "Untitled"
    )

    clean_page(soup)

    # Prefer content-specific containers.
    
    root = (
        soup.select_one(".adm-right-col")
        or soup.select_one(".adm-right-cont")
        or soup.select_one(".entry-content")
        or soup.select_one(".page-content")
        or soup.select_one("article")
        or soup.select_one("main")
        or soup.select_one("[role='main']")
        or soup.body
        or soup
    )


    # Remove repetitive navigation sections inside content.
    for element in root.select(
        ".breadcrumb, .breadcrumbs, "
        ".social-links, .share-buttons"
    ):
        element.decompose()

    # Replace HTML tables with readable row-based text.
    for table in list(root.find_all("table")):
        table_text = extract_table(table)
        table.replace_with(
            soup.new_string("\n" + table_text + "\n")
        )

    # Preserve headings and paragraph boundaries.
    for element in root.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6",
         "p", "li", "section"]
    ):
        element.insert_before("\n")
        element.insert_after("\n")

    text = normalize_text(
        root.get_text(" ", strip=True)
        .replace(" \n ", "\n")
    )

    return normalize_text(title), text
