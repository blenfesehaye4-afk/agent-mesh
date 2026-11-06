"""Semantic vector cache using lightweight TF-IDF and Cosine Similarity."""

import hashlib
import math
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple


class SemanticCache:
    """In-memory semantic cache returning instant responses for semantically equivalent prompts."""

    def __init__(self, similarity_threshold: float = 0.85, max_size: int = 1000):
        self.similarity_threshold = similarity_threshold
        self.max_size = max_size
        self.exact_cache: Dict[str, str] = {}  # sha256_hash -> response_text
        self.entries: List[Tuple[str, Counter, float, str]] = []  # [(prompt, tf_vector, norm, response)]
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
        return [w for w in cleaned.split() if len(w) > 2]

    def _vectorize(self, text: str) -> Tuple[Counter, float]:
        tokens = self._tokenize(text)
        counts = Counter(tokens)
        norm = math.sqrt(sum(v * v for v in counts.values()))
        return counts, norm

    @staticmethod
    def _cosine_similarity(vec1: Counter, norm1: float, vec2: Counter, norm2: float) -> float:
        if norm1 == 0 or norm2 == 0:
            return 0.0
        # Dot product
        common_keys = set(vec1.keys()) & set(vec2.keys())
        dot = sum(vec1[k] * vec2[k] for k in common_keys)
        return dot / (norm1 * norm2)

    def query(self, prompt: str) -> Optional[Tuple[str, float]]:
        """Look up prompt in semantic cache. Returns (cached_response, similarity) or None."""
        normalized = prompt.strip().lower()
        exact_hash = hashlib.sha256(normalized.encode()).hexdigest()

        # 1. Exact match check O(1)
        if exact_hash in self.exact_cache:
            self.hits += 1
            return self.exact_cache[exact_hash], 1.0

        # 2. Semantic vector cosine check
        q_vec, q_norm = self._vectorize(prompt)
        if q_norm == 0:
            self.misses += 1
            return None

        best_score = 0.0
        best_response = None

        for cached_prompt, c_vec, c_norm, resp in self.entries:
            sim = self._cosine_similarity(q_vec, q_norm, c_vec, c_norm)
            if sim > best_score:
                best_score = sim
                best_response = resp

        if best_score >= self.similarity_threshold and best_response is not None:
            self.hits += 1
            return best_response, round(best_score, 3)

        self.misses += 1
        return None

    def store(self, prompt: str, response: str) -> None:
        """Store prompt-response pair in both exact and semantic indices."""
        normalized = prompt.strip().lower()
        exact_hash = hashlib.sha256(normalized.encode()).hexdigest()
        self.exact_cache[exact_hash] = response

        vec, norm = self._vectorize(prompt)
        if norm > 0:
            if len(self.entries) >= self.max_size:
                self.entries.pop(0)
            self.entries.append((prompt, vec, norm, response))

    def stats(self) -> dict:
        total = self.hits + self.misses
        hit_ratio = (self.hits / total) if total > 0 else 0.0
        return {
            "entries_count": len(self.entries),
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio": round(hit_ratio, 3),
        }
