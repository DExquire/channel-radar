"""AI layer — LLM calls are mocked; no network, no key required.

Covers the two behaviours that matter for the "graceful degradation" requirement:
* When disabled/failing, the service falls back (category) or returns None (digest).
* When the API responds, the response is parsed correctly.
"""
from __future__ import annotations

from unittest.mock import patch

from app.services.ai import AIService, _keyword_category


def test_keyword_fallback_category():
    assert _keyword_category("New GPT model release for developers") == "Tech"
    assert _keyword_category("bitcoin and eth are up") == "Crypto"
    assert _keyword_category("random unrelated text") == "Other"


def test_categorize_uses_fallback_when_disabled():
    ai = AIService()
    ai._enabled = False
    assert ai.categorize("A startup raised funding") == "Business"


def test_digest_returns_none_when_disabled():
    ai = AIService()
    ai._enabled = False
    assert ai.digest("T", ["some post"], "7d") is None


def test_categorize_parses_api_response():
    ai = AIService()
    ai._enabled = True
    with patch.object(ai, "_generate", return_value="Politics"):
        assert ai.categorize("election news") == "Politics"


def test_categorize_falls_back_on_api_failure():
    ai = AIService()
    ai._enabled = True
    with patch.object(ai, "_generate", return_value=None):  # simulate 429/error
        assert ai.categorize("crypto token launch") == "Crypto"


def test_digest_parses_api_response():
    ai = AIService()
    ai._enabled = True
    with patch.object(ai, "_generate", return_value="A concise summary."):
        assert ai.digest("Chan", ["p1", "p2"], "7d") == "A concise summary."


def test_generate_handles_rate_limit(monkeypatch):
    """A 429 from Gemini must return None, not raise."""
    import httpx

    ai = AIService()
    ai._enabled = True

    class FakeResp:
        status_code = 429

        def raise_for_status(self):  # pragma: no cover - not reached
            raise AssertionError

        def json(self):  # pragma: no cover
            return {}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    assert ai._generate("prompt") is None
