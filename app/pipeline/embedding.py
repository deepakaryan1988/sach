import pickle
from pathlib import Path
from typing import List, Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


class EmbeddingModel:
    def __init__(self, max_features: int = 384):
        self.max_features = max_features
        self.vectorizer: Optional[TfidfVectorizer] = None
        self._fitted = False

    def fit(self, texts: List[str]) -> "EmbeddingModel":
        self.vectorizer = TfidfVectorizer(
            max_features=self.max_features,
            stop_words="english",
            ngram_range=(1, 2),
        )
        self.vectorizer.fit(texts)
        self._fitted = True
        return self

    def encode(self, texts: List[str]) -> np.ndarray:
        if self.vectorizer is None:
            raise RuntimeError("Model not fitted. Call fit() first.")
        return self.vectorizer.transform(texts).toarray().astype(np.float32)

    def encode_query(self, query: str) -> np.ndarray:
        if self.vectorizer is None:
            raise RuntimeError("Model not fitted. Call fit() first.")
        return self.vectorizer.transform([query]).toarray().astype(np.float32)

    def save(self, path: Path) -> None:
        with open(path, "wb") as f:
            pickle.dump(self.vectorizer, f)

    def load(self, path: Path) -> "EmbeddingModel":
        with open(path, "rb") as f:
            self.vectorizer = pickle.load(f)
        self._fitted = True
        return self
