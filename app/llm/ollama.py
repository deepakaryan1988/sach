from typing import Any, Dict

import httpx

from app.config import get_config
from app.core.exceptions import OllamaConnectionError
from app.llm.base import LLMInterface


class OllamaClient(LLMInterface):
    def __init__(self, base_url: str = None, model: str = None):
        config = get_config()
        self.base_url = base_url or config.ollama_base_url
        self.model = model or config.ollama_model
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=2.0))

    @property
    def provider(self) -> str:
        return "local"

    async def generate(self, prompt: str) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        try:
            response = await self.client.post(
                f"{self.base_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise OllamaConnectionError(
                f"Failed to connect to Ollama at {self.base_url}: {e}"
            )
        except httpx.HTTPStatusError as e:
            raise OllamaConnectionError(
                f"Ollama returned error status {e.response.status_code}"
            )

    async def close(self) -> None:
        await self.client.aclose()
