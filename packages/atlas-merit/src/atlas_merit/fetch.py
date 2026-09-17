# merit/fetch.py
"""CLI-side URL fetching. Stdlib only; the graph core never imports this."""

import http.client
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import ClassVar
from urllib.parse import urlparse

MAX_BYTES = 2_000_000


class _TextExtractor(HTMLParser):
    _SKIP: ClassVar[set[str]] = {"script", "style"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth and data.strip():
            self.chunks.append(data.strip())


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return "\n".join(parser.chunks)


def fetch_posting(url: str, timeout: int = 20) -> str:
    scheme = urlparse(url).scheme
    if scheme not in ("http", "https"):
        raise ValueError(f"unsupported scheme {scheme!r}: only http/https allowed")
    # S310 suppressed on both calls: the scheme allowlist above is the control.
    req = urllib.request.Request(url, headers={"User-Agent": "merit/0.1"})  # noqa: S310
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        body = resp.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError(f"response too large: over {MAX_BYTES} bytes")
    return html_to_text(body.decode("utf-8", errors="replace"))


_JOB_VIEW_ID = re.compile(r"/jobs/view/(\d+)")
GUEST_JOB_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"


def job_id(url: str) -> str | None:
    match = _JOB_VIEW_ID.search(url)
    return match.group(1) if match else None


class _Section(HTMLParser):
    """Text inside the first element carrying `css_class`, subtree included.
    LinkedIn's guest job card is plain server-rendered HTML with stable
    `description__*` classes - no JSON payload to key off, so the class is
    the contract."""

    def __init__(self, css_class: str) -> None:
        super().__init__()
        self._css_class = css_class
        self._depth = 0
        self.chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if self._depth:
            self._depth += 1
        elif self._css_class in (dict(attrs).get("class") or ""):
            self._depth = 1

    def handle_endtag(self, tag):
        if self._depth:
            self._depth -= 1

    def handle_data(self, data):
        if self._depth and data.strip():
            self.chunks.append(data.strip())


def _section_text(html: str, css_class: str) -> list[str]:
    parser = _Section(css_class)
    parser.feed(html)
    return parser.chunks


# LinkedIn renders this verbatim on the guest card once the posting closes.
# It is the only closure signal the guest surface exposes - the URL itself
# still returns 200 with a full description.
CLOSED_MARKER = "No longer accepting applications"


@dataclass(frozen=True)
class Posting:
    description: str
    expired: bool
    criteria: dict[str, str]


def parse_job(html: str) -> Posting:
    # The criteria list is a flat run of subheader/value chunks ("Seniority
    # level", "Not Applicable", "Employment type", ...), so pairing is
    # positional. An odd trailing chunk is a subheader with no value: dropped
    # rather than paired with the next unrelated label.
    chunks = _section_text(html, "description__job-criteria-list")
    return Posting(
        description="\n".join(_section_text(html, "description__text")),
        expired=CLOSED_MARKER in html,
        criteria=dict(zip(chunks[::2], chunks[1::2], strict=False)),
    )


RETRY_SLEEP = 1.0


def fetch_job(job: str, tries: int = 3, timeout: int = 20) -> str | None:
    """Guest-surface HTML for a LinkedIn job id, or None when the posting is
    gone (404). Unlike the public job URL - which 301s an expired posting to a
    search page - this endpoint still serves the real card, so a closed job is
    reported by `parse_job(...).expired`, never by a missing response."""
    request = urllib.request.Request(  # noqa: S310 - fixed https host, id is digits-only
        GUEST_JOB_URL.format(job_id=job), headers={"User-Agent": "merit/0.1"}
    )
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310
                body = resp.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if attempt == tries - 1:
                raise
        except (http.client.IncompleteRead, OSError):
            if attempt == tries - 1:
                raise
        else:
            if len(body) > MAX_BYTES:
                raise ValueError(f"response too large: over {MAX_BYTES} bytes")
            return body.decode("utf-8", errors="replace")
        time.sleep(RETRY_SLEEP)
    return None
