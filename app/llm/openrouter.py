from typing import Any, Dict

import httpx

from app.config import get_config
from app.core.exceptions import OpenRouterError
from app.llm.base import LLMInterface


class OpenRouterClient(LLMInterface):
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        config = get_config()
        self.api_key = api_key or config.openrouter_api_key
        self.base_url = base_url or config.openrouter_base_url
        self.model = model or config.openrouter_model
        self.client = httpx.AsyncClient(timeout=60.0)

    @property
    def provider(self) -> str:
        return "cloud"

    async def generate(self, prompt: str) -> str:
        if not self.api_key:
            raise OpenRouterError(
                "OpenRouter API key is not configured. Set OPENROUTER_API_KEY in .env"
            )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except httpx.HTTPStatusError as e:
            raise OpenRouterError(
                f"OpenRouter returned error {e.response.status_code}: {e.response.text}"
            )
        except (KeyError, IndexError) as e:
            raise OpenRouterError(f"Unexpected response format from OpenRouter: {e}")

    async def close(self) -> None:
        await self.client.aclose()
