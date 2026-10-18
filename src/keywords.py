"""Keyword extraction for reviews: stopword-aware unigrams + bigrams."""
from __future__ import annotations

import itertools
import re
from collections import Counter

STOPWORDS = frozenset(
    ["a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can", "cannot", "could", "couldn", "did", "didn", "do", "does", "doesn", "doing", "don", "down", "during", "each", "few", "for", "from", "further", "had", "hadn", "has", "hasn", "have", "haven", "having", "he", "her", "here", "hers", "herself", "him", "himself", "his", "how", "i", "if", "in", "into", "is", "isn", "it", "its", "itself", "let", "me", "more", "most", "mustn", "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan", "she", "should", "shouldn", "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves", "then", "there", "these", "they", "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "wasn", "we", "were", "weren", "what", "when", "where", "which", "while", "who", "whom", "why", "with", "won", "would", "wouldn", "you", "your", "yours", "yourself", "yourselves", "ive", "youve", "dont", "didnt", "cant", "couldnt", "wouldnt", "wasnt", "werent", "also", "got", "get", "went", "go", "going", "really", "one", "two", "even", "much", "many", "still", "back", "another", "thing", "things", "lot", "bit", "day", "days", "time", "times", "week", "weeks", "month", "year", "place", "place", "food", "restaurant", "meal", "visit", "visited", "visiting", "tripadvisor"]
)

_WORD_RE = re.compile(r"[a-z][a-z']+")


def tokenize(clean_text: str) -> list[str]:
    """Content words from already-cleaned text."""
    return [w for w in _WORD_RE.findall(clean_text.lower()) if len(w) > 2 and w not in STOPWORDS]


def extract_keywords(clean_text: str, top_n: int = 8) -> list[str]:
    """Top keywords for one review (unigrams + salient bigrams)."""
    tokens = tokenize(clean_text)
    if not tokens:
        return []
    unigrams = Counter(tokens)
    bigrams = Counter(
        f"{a} {b}"
        for a, b in itertools.pairwise(tokens)
        if a not in STOPWORDS and b not in STOPWORDS
    )
    # Bigrams get a weight bonus so "slow service" beats its parts when frequent
    scores = Counter({w: c for w, c in unigrams.items()})
    for bg, c in bigrams.items():
        scores[bg] = c * 1.5
    return [w for w, _ in scores.most_common(top_n)]


def keyword_document_counts(reviews_keywords: list[list[str]]) -> Counter:
    """How many reviews mention each keyword (document frequency)."""
    counts: Counter = Counter()
    for kws in reviews_keywords:
        counts.update(set(kws))
    return counts
