
"""Discover and ingest public CBIT PDF documents.

Responsibilities:
- Discover PDF links on an approved public webpage
- Respect robots.txt for HTML and PDF requests
- Validate hosts, HTTPS, and download sizes
- Download PDF files safely
- Extract text with the existing PDF/OCR parser
- Write JSONL records for ingestion.sync

This module does not generate embeddings or write to databases.
"""

import argparse
import json
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urldefrag
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from database.config import settings
from ingestion.parsers.pdf_parser import (
    PDFParsingError,
    parse_pdf,
)


MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
DEFAULT_DELAY = 1.5

USER_AGENT = (
    "CBITAcademicAssistant/2.0 "
    "(contact: configure-your-contact-email)"
)


def allowed_hosts() -> set[str]:
    """Return the configured approved crawling hosts."""

    return {
        host.strip().lower()
        for host in settings().allowed_crawl_hosts.split(",")
        if host.strip()
    }


def is_approved_url(url: str) -> bool:
    """Validate a public HTTPS URL against the host allowlist."""

    try:
        parsed = urlsplit(url)

        return (
            parsed.scheme == "https"
            and parsed.hostname in allowed_hosts()
            and parsed.port in (None, 443)
            and parsed.username is None
            and parsed.password is None
        )

    except ValueError:
        return False


def allowed_pdf_url(url: str) -> bool:
    """Check whether a URL is an approved PDF URL."""

    if not is_approved_url(url):
        return False

    return urlsplit(url).path.lower().endswith(".pdf")


def discover_pdfs(
    html: str,
    page_url: str,
) -> list[dict]:
    """Find direct PDF links in a webpage."""

    soup = BeautifulSoup(html, "html.parser")
    found = {}

    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()

        if not href:
            continue

        url = urldefrag(
            urljoin(page_url, href)
        )[0]

        if not allowed_pdf_url(url):
            continue

        if url in found:
            continue

        title = anchor.get_text(
            " ",
            strip=True,
        )

        if not title:
            title = Path(
                urlsplit(url).path
            ).stem.replace("-", " ")

        found[url] = {
            "url": url,
            "title": title,
            "source_page": page_url,
        }

    return list(found.values())


def get_robots_policy(
    session: requests.Session,
    hostname: str,
) -> RobotFileParser:
    """Fetch robots.txt and fail closed on unexpected responses."""

    robots_url = (
        f"https://{hostname}/robots.txt"
    )

    response = session.get(
        robots_url,
        timeout=(10, 20),
        allow_redirects=False,
    )

    if response.status_code not in (200, 404):
        raise RuntimeError(
            "Unable to verify robots.txt: "
            f"HTTP {response.status_code}"
        )

    robots = RobotFileParser()
    robots.set_url(robots_url)

    if response.status_code == 404:
        robots.parse([])
    else:
        response.encoding = "utf-8"
        robots.parse(
            response.text.splitlines()
        )

    return robots


def download_pdf(
    session: requests.Session,
    url: str,
    destination: Path,
) -> None:
    """Download a validated PDF with a strict size limit."""

    if not allowed_pdf_url(url):
        raise ValueError(
            f"Unapproved PDF URL: {url}"
        )

    with session.get(
        url,
        timeout=(10, 60),
        stream=True,
        allow_redirects=False,
    ) as response:

        if response.status_code != 200:
            raise ValueError(
                "Unexpected PDF HTTP status: "
                f"{response.status_code}"
            )

        content_length = response.headers.get(
            "Content-Length"
        )

        if content_length:
            if int(content_length) > MAX_DOWNLOAD_BYTES:
                raise ValueError(
                    "PDF exceeds maximum download size"
                )

        content_type = response.headers.get(
            "Content-Type", ""
        ).lower()

        if (
            content_type
            and "application/pdf" not in content_type
            and "application/octet-stream" not in content_type
        ):
            raise ValueError(
                f"Unexpected content type: {content_type}"
            )

        total_bytes = 0

        with destination.open("wb") as output:

            for chunk in response.iter_content(
                chunk_size=65536
            ):
                if not chunk:
                    continue

                total_bytes += len(chunk)

                if total_bytes > MAX_DOWNLOAD_BYTES:
                    raise ValueError(
                        "PDF exceeds download size limit"
                    )

                output.write(chunk)

    # Verify actual file format, not just extension.
    with destination.open("rb") as file:
        if file.read(5) != b"%PDF-":
            raise ValueError(
                "Downloaded file is not a valid PDF"
            )


def ingest_pdfs(
    page_url: str,
    output: str,
    max_pdfs: int = 5,
) -> dict:
    """Download and extract approved PDFs from one public page."""

    if not is_approved_url(page_url):
        raise ValueError(
            f"Unapproved webpage URL: {page_url}"
        )

    if max_pdfs < 1:
        raise ValueError(
            "max_pdfs must be positive"
        )

    session = requests.Session()

    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/pdf",
    })

    hostname = urlsplit(page_url).hostname

    # Load robots policies for approved hosts.
    robots_cache = {}

    def get_policy(host: str) -> RobotFileParser:
        if host not in robots_cache:
            robots_cache[host] = get_robots_policy(
                session,
                host,
            )

        return robots_cache[host]

    def check_permission(url: str) -> bool:
        host = urlsplit(url).hostname

        return get_policy(host).can_fetch(
            USER_AGENT,
            url,
        )

    if not check_permission(page_url):
        raise PermissionError(
            f"robots.txt disallows {page_url}"
        )

    page_policy = get_policy(hostname)

    crawl_delay = page_policy.crawl_delay(
        USER_AGENT
    )

    request_delay = max(
        DEFAULT_DELAY,
        float(crawl_delay or 0),
    )

    # Fetch source HTML.
    response = session.get(
        page_url,
        timeout=(10, 30),
        allow_redirects=False,
    )

    if response.status_code != 200:
        raise ValueError(
            "Unable to fetch webpage: "
            f"HTTP {response.status_code}"
        )

    content_type = response.headers.get(
        "Content-Type", ""
    ).lower()

    if (
        "text/html" not in content_type
        and "application/xhtml+xml" not in content_type
    ):
        raise ValueError(
            "Source webpage is not HTML"
        )

    response.encoding = "utf-8"

    pdf_links = discover_pdfs(
        response.text,
        page_url,
    )

    output_path = Path(output)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    stats = {
        "discovered": len(pdf_links),
        "processed": 0,
        "failed": 0,
        "disallowed": 0,
    }

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as out:

        for item in pdf_links[:max_pdfs]:

            url = item["url"]

            try:
                if not check_permission(url):
                    print(
                        "Robots disallowed:",
                        url,
                    )
                    stats["disallowed"] += 1
                    continue

                pdf_policy = get_policy(
                    urlsplit(url).hostname
                )

                pdf_delay = max(
                    request_delay,
                    float(
                        pdf_policy.crawl_delay(
                            USER_AGENT
                        ) or 0
                    ),
                )

                time.sleep(pdf_delay)

                with tempfile.TemporaryDirectory() as temp:

                    pdf_path = (
                        Path(temp) / "document.pdf"
                    )

                    download_pdf(
                        session,
                        url,
                        pdf_path,
                    )

                    _, text = parse_pdf(
                        str(pdf_path)
                    )

                record = {
                    "url": url,
                    "title": item["title"],
                    "text": text,
                    "category": "pdf",
                    "access_level": "public",
                }

                out.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                    ) + "\n"
                )

                out.flush()

                stats["processed"] += 1

                print(
                    "Processed:",
                    item["title"],
                    "|",
                    url,
                    flush=True,
                )

            except (
                requests.RequestException,
                PDFParsingError,
                ValueError,
                OSError,
                RuntimeError,
            ) as exc:

                stats["failed"] += 1

                print(
                    "Failed:",
                    url,
                    "|",
                    str(exc),
                    flush=True,
                )

    print("\nPDF ingestion completed")
    print(
        json.dumps(
            stats,
            indent=2,
        )
    )

    return stats


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--page",
        default="https://www.cbit.ac.in/",
    )

    parser.add_argument(
        "--output",
        default="data/cbit_pdfs.jsonl",
    )

    parser.add_argument(
        "--max-pdfs",
        type=int,
        default=5,
    )

    args = parser.parse_args()

    ingest_pdfs(
        page_url=args.page,
        output=args.output,
        max_pdfs=args.max_pdfs,
    )
