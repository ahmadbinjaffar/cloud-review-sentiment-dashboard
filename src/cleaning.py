"""Review text cleaning used by the processing handler and keyword extraction."""
from __future__ import annotations

import html
import re
import unicodedata

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_MENTION_RE = re.compile(r"@\w+")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # emoticons, symbols, pictographs
    "\U00002600-\U000027BF"  # misc symbols
    "\U0001F1E6-\U0001F1FF"  # flags
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\u200d"  # zero-width joiner
    "]+",
    flags=re.UNICODE,
)


def clean_text(raw: str) -> str:
    """Normalise review text: HTML, URLs, emojis, unicode, whitespace."""
    text = html.unescape(str(raw))
    text = _TAG_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    text = _MENTION_RE.sub(" ", text)
    text = _EMOJI_RE.sub(" ", text)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")  # drop leftover non-ascii
    text = text.lower()
    text = re.sub(r"[^a-z0-9'\s]", " ", text)
    text = _WS_RE.sub(" ", text).strip()
    # collapse accidental word joins like "dayThe" -> keep as-is; only drop 1-char leftovers
    text = " ".join(w for w in text.split() if len(w) > 1 or w in ("i", "a"))
    return text
