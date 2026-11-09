
"""Public CBIT website crawler.

Features:
- Robots.txt compliance
- HTTPS and approved-host restrictions
- UTF-8-aware HTML decoding
- URL normalization and deduplication
- Controlled redirect handling
- Request throttling
- JSONL output compatible with ingestion.sync

This crawler extracts HTML pages only.
PDF and image ingestion are separate pipeline stages.
"""

import argparse
import json
import time
from collections import deque
from pathlib import Path
from urllib.parse import (
    urljoin,
    urlsplit,
    urlunsplit,
    parse_qsl,
    urlencode,
)
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup, UnicodeDammit

from database.config import settings
from ingestion.parsers.html_parser import parse_html
from ingestion.parsers.homepage_parser import parse_homepage


USER_AGENT = (
    "CBITAcademicAssistant/2.0 "
    "(contact: configure-your-contact-email)"
)

SKIP_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png",
    ".gif", ".webp", ".svg", ".ico",
    ".zip", ".rar", ".7z", ".mp4",
    ".mp3", ".doc", ".docx",
    ".xls", ".xlsx", ".ppt", ".pptx",
)

TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def normalize_url(url: str) -> str:
    """Normalize URLs without discarding meaningful query parameters."""

    parsed = urlsplit(url)

    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()

    if parsed.username or parsed.password:
        return ""

    if parsed.port not in (None, 443):
        return ""

    if scheme != "https" or not hostname:
        return ""

    path = parsed.path or "/"

    # Use one canonical trailing-slash convention
    # for HTML-style paths.
    if not path.endswith("/") and "." not in path.rsplit("/", 1)[-1]:
        path += "/"

    params = [
        (key, value)
        for key, value in parse_qsl(
            parsed.query,
            keep_blank_values=True
        )
        if key.lower() not in TRACKING_PARAMS
        and not key.lower().startswith("utm_")
    ]

    query = urlencode(sorted(params))

    return urlunsplit(
        (scheme, hostname, path, query, "")
    )


def is_allowed_url(url: str, allowed_hosts: set) -> bool:
    """Restrict crawling to approved public HTTPS hosts."""

    parsed = urlsplit(url)

    if parsed.scheme != "https":
        return False

    if parsed.hostname not in allowed_hosts:
        return False

    if parsed.username or parsed.password:
        return False

    if parsed.port not in (None, 443):
        return False

    if parsed.path.lower().endswith(SKIP_EXTENSIONS):
        return False

    return True


def decode_html(content: bytes) -> str:
    """Decode HTML, preferring UTF-8 where valid."""

    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = UnicodeDammit(
            content,
            is_html=True
        ).unicode_markup

        if decoded is None:
            raise ValueError(
                "Unable to decode HTML response"
            )

        return decoded


def load_robots(
    session: requests.Session,
    host: str,
) -> RobotFileParser:
    """Load robots.txt; fail closed on unexpected errors."""

    robots_url = f"https://{host}/robots.txt"

    response = session.get(
        robots_url,
        timeout=20,
        allow_redirects=False,
    )

    robots = RobotFileParser()
    robots.set_url(robots_url)

    if response.status_code == 404:
        robots.parse([])
        return robots

    if response.status_code != 200:
        raise RuntimeError(
            "Cannot verify robots.txt: "
            f"HTTP {response.status_code}"
        )

    robots.parse(
        decode_html(response.content).splitlines()
    )

    return robots


def crawl(
    start: str,
    output: str,
    max_pages: int = 100,
    delay: float = 1.5,
):
    """Crawl approved public HTML pages into JSONL."""

    if max_pages < 1:
        raise ValueError("max_pages must be positive")

    if delay < 0:
        raise ValueError("delay cannot be negative")

    allowed_hosts = {
        host.strip().lower()
        for host in settings().allowed_crawl_hosts.split(",")
        if host.strip()
    }

    start = normalize_url(start)

    if not is_allowed_url(start, allowed_hosts):
        raise ValueError(
            "Start URL must be an approved HTTPS host"
        )

    # Remain on the starting hostname.
    host = urlsplit(start).hostname
    permitted = {host}

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    })

    robots = load_robots(session, host)

    robots_delay = robots.crawl_delay(USER_AGENT)
    effective_delay = max(
        delay,
        float(robots_delay or 0),
    )

    queue = deque([start])
    seen = set()
    queued = {start}

    stats = {
        "visited": 0,
        "extracted": 0,
        "redirected": 0,
        "skipped": 0,
        "errors": 0,
    }

    output_path = Path(output)
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with output_path.open(
        "w",
        encoding="utf-8"
    ) as out:

        while queue and stats["visited"] < max_pages:

            url = queue.popleft()
            queued.discard(url)

            if url in seen:
                continue

            if not is_allowed_url(url, permitted):
                stats["skipped"] += 1
                continue

            if not robots.can_fetch(USER_AGENT, url):
                stats["skipped"] += 1
                continue

            seen.add(url)
            stats["visited"] += 1

            try:
                response = session.get(
                    url,
                    timeout=20,
                    allow_redirects=False,
                )

                # Follow redirects only after validating
                # the destination and its robots rules.
                if response.status_code in (
                    301, 302, 303, 307, 308
                ):
                    location = response.headers.get(
                        "Location"
                    )

                    if location:
                        target = normalize_url(
                            urljoin(url, location)
                        )

                        if (
                            is_allowed_url(target, permitted)
                            and target not in seen
                            and target not in queued
                            and robots.can_fetch(
                                USER_AGENT, target
                            )
                        ):
                            queue.append(target)
                            queued.add(target)

                    stats["redirected"] += 1
                    continue

                if response.status_code != 200:
                    stats["skipped"] += 1
                    continue

                content_type = response.headers.get(
                    "Content-Type", ""
                ).lower()

                if (
                    "text/html" not in content_type
                    and "application/xhtml+xml"
                    not in content_type
                ):
                    stats["skipped"] += 1
                    continue

                html = decode_html(
                    response.content
                )

                if urlsplit(url).path in ("", "/"):
                    title, body = parse_homepage(html)
                else:
                    title, body = parse_html(html)

                if not body.strip():
                    stats["skipped"] += 1
                    continue

                record = {
                    "url": url,
                    "title": title,
                    "text": body,
                    "category": "general",
                    "access_level": "public",
                }

                out.write(
                    json.dumps(
                        record,
                        ensure_ascii=False
                    ) + "\n"
                )

                out.flush()
                stats["extracted"] += 1

                # Discover links from the original HTML.
                soup = BeautifulSoup(
                    html,
                    "html.parser"
                )

                for anchor in soup.select("a[href]"):

                    href = anchor.get("href", "")

                    link = normalize_url(
                        urljoin(url, href)
                    )

                    if not is_allowed_url(
                        link, permitted
                    ):
                        continue

                    if (
                        link not in seen
                        and link not in queued
                    ):
                        queue.append(link)
                        queued.add(link)

                print(
                    f"[{stats['extracted']}] "
                    f"{title} | {url}",
                    flush=True,
                )

            except (
                requests.RequestException,
                ValueError,
            ) as exc:

                stats["errors"] += 1

                print(
                    f"Error processing {url}: {exc}",
                    flush=True,
                )

            finally:
                time.sleep(effective_delay)

    print("\nCrawl completed")
    print(json.dumps(stats, indent=2))

    return stats


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--start",
        default="https://www.cbit.ac.in/",
    )

    parser.add_argument(
        "--output",
        default="data/crawl.jsonl",
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=100,
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
    )

    args = parser.parse_args()

    crawl(
        start=args.start,
        output=args.output,
        max_pages=args.max_pages,
        delay=args.delay,
    )