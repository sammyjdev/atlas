import http.client
import time
import urllib.error
import urllib.request
from pathlib import Path

from atlas_merit.fetch import fetch_job, job_id, parse_job

FIXTURES = Path(__file__).parent / "fixtures" / "linkedin"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_job_returns_the_posting_description():
    posting = parse_job(_fixture("job_live.html"))

    assert "Vertex AI" in posting.description
    assert "Sign in with Email" not in posting.description


def test_parse_job_flags_a_posting_that_no_longer_accepts_applications():
    assert parse_job(_fixture("job_expired.html")).expired is True
    assert parse_job(_fixture("job_live.html")).expired is False


def test_parse_job_pairs_the_job_criteria_into_a_mapping():
    criteria = parse_job(_fixture("job_live.html")).criteria

    assert criteria["Seniority level"] == "Not Applicable"
    assert criteria["Employment type"] == "Full-time"
    assert criteria["Industries"] == "IT Services and IT Consulting"


def test_job_id_reads_the_posting_id_out_of_a_linkedin_url():
    assert job_id("https://www.linkedin.com/jobs/view/4448247247/") == "4448247247"
    assert job_id("https://www.linkedin.com/feed/") is None


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self, *_args):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def test_fetch_job_retries_a_truncated_response(monkeypatch):
    """LinkedIn's guest endpoint cuts the chunked stream on roughly a quarter
    of requests; a retry recovers it, so a truncated read is never a dead job."""
    attempts = []

    def flaky(_request, timeout=0):
        attempts.append(1)
        if len(attempts) < 3:
            raise http.client.IncompleteRead(b"partial")
        return _FakeResponse(b"<html>ok</html>")

    monkeypatch.setattr(urllib.request, "urlopen", flaky)
    monkeypatch.setattr(time, "sleep", lambda _s: None)

    assert fetch_job("4448247247") == "<html>ok</html>"
    assert len(attempts) == 3


def test_fetch_job_returns_none_for_a_deleted_posting(monkeypatch):
    def gone(_request, timeout=0):
        raise urllib.error.HTTPError("url", 404, "Not Found", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", gone)

    assert fetch_job("4448247247") is None
