import logging
from typing import List

from app.core.exceptions import FAISSIndexNotFoundError
from app.models.responses import Source
from app.pipeline.faiss_manager import FAISSIndexManager

logger = logging.getLogger(__name__)


class RetrievalModule:
    def __init__(self):
        self.faiss_manager = FAISSIndexManager()

    async def retrieve(self, query: str, top_k: int = 5) -> List[Source]:
        try:
            results = self.faiss_manager.search(query, top_k)
            return [
                Source(
                    title=result.get("title", "Unknown"),
                    content=result.get("content", ""),
                )
                for result in results
            ]
        except FAISSIndexNotFoundError:
            logger.warning("FAISS index not found, returning empty sources")
            return []
        except Exception as e:
            logger.error(f"Retrieval error: {e}")
            return []
