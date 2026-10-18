"""Unit tests for text cleaning and keyword extraction."""
from __future__ import annotations

from src.cleaning import clean_text
from src.keywords import extract_keywords, keyword_document_counts, tokenize


# ---------------------------------------------------------------- cleaning
def test_clean_text_removes_urls_tags_mentions_emojis():
    raw = "<b>Great</b> food https://x.com @bob \U0001F600 dinner"
    assert clean_text(raw) == "great food dinner"


def test_clean_text_lowercases_and_collapses_whitespace():
    assert clean_text("  NICE   PLACE\ttonight ") == "nice place tonight"


def test_clean_text_unescapes_html_entities():
    assert clean_text("pizza &amp; pasta") == "pizza pasta"


def test_clean_text_keeps_i_and_a_but_drops_single_chars():
    assert clean_text("I had a meal of soup") == "i had a meal of soup"
    assert clean_text("x y z pizza") == "pizza"


def test_clean_text_of_emptyish_input_returns_empty():
    assert clean_text("😀😀 https://x.com") == ""


# ---------------------------------------------------------------- keywords
def test_tokenize_drops_stopwords_and_short_words():
    # "food", "really", "place" are domain stopwords and must be dropped
    assert tokenize("the pasta was really great tonight") == ["pasta", "great", "tonight"]


def test_extract_keywords_returns_top_n_unigrams_and_bigrams():
    kws = extract_keywords("slow service very slow service tonight", top_n=5)
    assert len(kws) <= 5
    assert "slow service" in kws  # weighted bigram beats its parts
    assert "the" not in kws


def test_extract_keywords_empty_for_stopword_only_text():
    assert extract_keywords("the and of") == []


def test_keyword_document_counts_is_set_based():
    counts = keyword_document_counts([["pizza", "nice"], ["pizza"], ["pizza", "nice", "cozy"]])
    assert counts["pizza"] == 3
    assert counts["nice"] == 2
    assert counts["cozy"] == 1
