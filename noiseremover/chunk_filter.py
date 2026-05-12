from __future__ import annotations

from functools import lru_cache
from typing import List, Sequence

import numpy as np

from core.fastembed_cache import get_fastembed_cache_dir


@lru_cache(maxsize=4)
def _get_sentence_transformer(model_name: str):
    from fastembed import TextEmbedding

    return TextEmbedding(
        model_name=model_name,
        cache_dir=get_fastembed_cache_dir(),
        providers=["CPUExecutionProvider"],
    )

def preload_text_embedding_model(model_name: str) -> None:
    _get_sentence_transformer(model_name)


class ChunkFilter:
    def __init__(
        self,
        threshold: float = 0.4,
        model_name: str = "BAAI/bge-small-en-v1.5",
    ):
        self.model = _get_sentence_transformer(model_name)
        self.threshold = threshold
        self.seed_embedding = None

    def set_seed(self, seed_texts: Sequence[str]) -> None:
        usable_seed_texts = [text.strip() for text in seed_texts if text and text.strip()]
        if not usable_seed_texts:
            raise ValueError("seed_texts must contain at least one non-empty string")

        embeddings = list(self.model.embed(usable_seed_texts))
        self.seed_embedding = np.mean(embeddings, axis=0)

    def _cosine_sim(self, a: np.ndarray, b: np.ndarray) -> float:
        denominator = np.linalg.norm(a) * np.linalg.norm(b)
        if denominator == 0:
            return 0.0
        return float(np.dot(a, b) / denominator)

    def score_texts(self, texts: Sequence[str], show_progress_bar: bool = False) -> List[tuple[str, float]]:
        if self.seed_embedding is None:
            raise ValueError("Seed embedding is not set. Call set_seed() first.")

        usable_texts = [text for text in texts if text and text.strip()]
        if not usable_texts:
            return []

        embeddings = list(self.model.embed(usable_texts))
        return [
            (text, self._cosine_sim(emb, self.seed_embedding))
            for text, emb in zip(usable_texts, embeddings)
        ]

    def filter(self, texts: Sequence[str], show_progress_bar: bool = False) -> List[str]:
        scored_texts = self.score_texts(texts, show_progress_bar=show_progress_bar)
        return [
            text
            for text, score in scored_texts
            if score >= self.threshold
        ]
