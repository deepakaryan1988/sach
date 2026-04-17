from typing import Any, Dict

import httpx

from app.config import get_config
from app.core.exceptions import OpenRouterError
from app.llm.base import LLMInterface


class NvidiaClient(LLMInterface):
    def __init__(self, api_key: str = None, base_url: str = None):
        config = get_config()
        self.api_key = api_key or config.nvidia_api_key
        self.base_url = base_url or config.nvidia_base_url
        self.default_model = "meta/llama-3.3-70b-instruct"
        self.client = httpx.AsyncClient(timeout=60.0)

    @property
    def provider(self) -> str:
        return "nvidia"

    async def generate(self, prompt: str, model_override: str = None) -> str:
        if not self.api_key:
            raise OpenRouterError(
                "Nvidia API key is not configured. Set NVIDIA_API_KEY in .env"
            )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": model_override or self.default_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2048,
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
                f"Nvidia NIM returned error {e.response.status_code}: {e.response.text}"
            )
        except (KeyError, IndexError) as e:
            raise OpenRouterError(f"Unexpected response format from Nvidia: {e}")

    async def close(self) -> None:
        await self.client.aclose()
