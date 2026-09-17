"""AI layer (Google Gemini, free tier) — meaningful processing with graceful
degradation.

Contract (see docs/adr/0003-llm-provider.md and README):
* If no API key is configured, or the API errors / hits its rate limit, every
  function returns None (digest) or falls back to a cheap keyword heuristic
  (category). The dashboard NEVER breaks because of the LLM — it just shows
  "AI unavailable" and keeps serving collected data.
* Calls go over plain httpx REST so we don't pull a heavy SDK, and so failures
  are easy to catch and classify (401 = bad key, 429 = quota).

Two features are implemented:
  1. digest(...)   — "what did this channel write about this period" summary.
  2. categorize(...) — topic/category label for a single post.
"""
from __future__ import annotations

import re

import httpx
from loguru import logger

from app.config import get_settings

settings = get_settings()

# Cheap, deterministic fallback so posts still get a category when the LLM is
# unavailable. Not a replacement for the LLM — a safety net.
_KEYWORD_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Tech": ("ai", "software", "code", "developer", "gpt", "release", "app", "tech"),
    "Business": ("market", "revenue", "invest", "funding", "business", "sales", "deal"),
    "Politics": ("election", "government", "president", "policy", "war", "sanction"),
    "Crypto": ("crypto", "bitcoin", "btc", "eth", "token", "blockchain", "defi"),
    "Media": ("video", "photo", "podcast", "stream", "youtube", "film", "movie"),
}


def _keyword_category(text: str) -> str:
    # Word-boundary match so short keywords like "ai" don't match inside
    # unrelated words (e.g. "raised").
    tokens = set(re.findall(r"[a-z0-9]+", (text or "").lower()))
    for label, keywords in _KEYWORD_CATEGORIES.items():
        if tokens & set(keywords):
            return label
    return "Other"


class AIService:
    """Thin, defensive wrapper around Gemini generateContent."""

    def __init__(self) -> None:
        self._enabled = settings.ai_enabled
        self._model = settings.gemini_model

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _generate(self, prompt: str, max_output_tokens: int = 512) -> str | None:
        """Low-level call. Returns text or None on any failure."""
        if not self._enabled:
            return None
        url = (
            f"{settings.gemini_base_url}/models/{self._model}:generateContent"
            f"?key={settings.gemini_api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": max_output_tokens,
                # gemini-3.x flash is a "thinking" model; without this the token
                # budget is spent on reasoning and the visible answer is cut off.
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        try:
            with httpx.Client(timeout=settings.ai_timeout_seconds) as client:
                resp = client.post(url, json=payload)
            if resp.status_code == 429:
                logger.warning("Gemini rate limit hit (429) — degrading gracefully")
                return None
            resp.raise_for_status()
            data = resp.json()
            # Join every text part of the first candidate (output can be split).
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts).strip()
            return text or None
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            logger.warning("Gemini call failed, degrading gracefully: {}", exc)
            return None

    def categorize(self, text: str) -> str:
        """Return a short category label. Always returns something usable."""
        text = (text or "").strip()
        if not text:
            return "Other"
        if not self._enabled:
            return _keyword_category(text)
        prompt = (
            "Classify the Telegram post below into ONE short category "
            "(1-2 words, English, e.g. Tech, Business, Politics, Crypto, Media, "
            "Sports, Entertainment, Other). Reply with the label only.\n\n"
            f"Post:\n{text[:1500]}"
        )
        label = self._generate(prompt, max_output_tokens=64)
        if not label:
            return _keyword_category(text)
        # Keep it clean: first line, strip punctuation.
        label = re.split(r"[\n.]", label)[0].strip().strip('"').title()
        return label[:64] or _keyword_category(text)

    def digest(self, channel_title: str, post_texts: list[str], period_label: str) -> str | None:
        """Summarize what the channel wrote about in the period. None if AI off/failed."""
        texts = [t for t in post_texts if t and t.strip()]
        if not self._enabled or not texts:
            return None
        joined = "\n---\n".join(t[:600] for t in texts[:40])
        prompt = (
            f"You are an analyst. Below are recent posts from the Telegram channel "
            f"\"{channel_title}\" over the last {period_label}. Write a concise digest "
            f"(3-5 sentences) in English covering the main themes and notable points. "
            f"Be specific and useful for a reader who missed them.\n\nPosts:\n{joined}"
        )
        return self._generate(prompt, max_output_tokens=1024)


def get_ai_service() -> AIService:
    return AIService()
