import pytest
from agent_mesh.cache import SemanticCache


def test_exact_cache_hit():
    cache = SemanticCache(similarity_threshold=0.85)
    cache.store("What is Python?", "Python is a high-level programming language.")

    # Exact query
    hit, score = cache.query("What is Python?")
    assert hit == "Python is a high-level programming language."
    assert score == 1.0


def test_semantic_cache_hit_similar_phrasing():
    cache = SemanticCache(similarity_threshold=0.75)
    cache.store("Explain how to sort a list in Python using sort", "Use the list.sort() method or sorted() function.")

    # Similar phrasing
    hit, score = cache.query("How to sort list in Python sort method")
    assert hit is not None
    assert score >= 0.75


def test_semantic_cache_miss_different_topic():
    cache = SemanticCache(similarity_threshold=0.80)
    cache.store("What is Python?", "A programming language.")

    # Completely different topic
    result = cache.query("What is the recipe for chocolate cake?")
    assert result is None
