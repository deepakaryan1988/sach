import pickle
from pathlib import Path
from typing import List, Optional

import faiss
import numpy as np

from app.config import get_config
from app.core.exceptions import EmbeddingError, FAISSIndexNotFoundError, RetrievalError
from app.pipeline.embedding import EmbeddingModel


class FAISSIndexManager:
    def __init__(
        self,
        index_path: str = None,
        embedding_model: EmbeddingModel = None,
    ):
        config = get_config()
        self.index_path = index_path or config.retrieval_index_path
        self.embedding_model = embedding_model or EmbeddingModel()
        self.index: Optional[faiss.Index] = None
        self.documents: List[dict] = []

    def _ensure_index_dir(self) -> Path:
        path = Path(self.index_path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def load_index(self) -> None:
        index_file = self._ensure_index_dir() / "index.faiss"
        docs_file = self._ensure_index_dir() / "documents.pkl"
        vec_file = self._ensure_index_dir() / "vectorizer.pkl"

        if not index_file.exists() or not docs_file.exists():
            raise FAISSIndexNotFoundError(
                f"Index not found at {self.index_path}. Run indexing script first."
            )

        self.index = faiss.read_index(str(index_file))
        with open(docs_file, "rb") as f:
            self.documents = pickle.load(f)
        self.embedding_model.load(vec_file)

    def save_index(self) -> None:
        if self.index is None:
            raise RetrievalError("No index to save. Build index first.")

        self._ensure_index_dir()
        index_file = self._ensure_index_dir() / "index.faiss"
        docs_file = self._ensure_index_dir() / "documents.pkl"
        vec_file = self._ensure_index_dir() / "vectorizer.pkl"

        faiss.write_index(self.index, str(index_file))
        with open(docs_file, "wb") as f:
            pickle.dump(self.documents, f)
        self.embedding_model.save(vec_file)

    def build_index(self, documents: List[dict]) -> None:
        if not documents:
            raise RetrievalError("Cannot build index from empty document list")

        texts = [doc["content"] for doc in documents]
        self.embedding_model.fit(texts)
        embeddings = self.embedding_model.encode(texts)

        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(embeddings)
        self.documents = documents

        self.save_index()

    def search(self, query: str, top_k: int = 5) -> List[dict]:
        if self.index is None:
            try:
                self.load_index()
            except FAISSIndexNotFoundError:
                return []

        if not self.documents:
            return []

        query_embedding = self.embedding_model.encode_query(query)
        distances, indices = self.index.search(
            query_embedding, min(top_k, len(self.documents))
        )

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx >= 0 and idx < len(self.documents):
                doc = self.documents[idx].copy()
                doc["distance"] = float(dist)
                results.append(doc)

        return results

    def index_exists(self) -> bool:
        index_file = Path(self.index_path) / "index.faiss"
        docs_file = Path(self.index_path) / "documents.pkl"
        vec_file = Path(self.index_path) / "vectorizer.pkl"
        return index_file.exists() and docs_file.exists() and vec_file.exists()
