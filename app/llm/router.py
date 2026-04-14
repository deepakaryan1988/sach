from app.core.exceptions import LLMError
from app.llm.base import LLMInterface
from app.llm.ollama import OllamaClient
from app.llm.openrouter import OpenRouterClient


class LLMRouter:
    def __init__(self):
        self.local_client = OllamaClient()
        self.cloud_client = OpenRouterClient()

    async def generate(self, prompt: str, force_cloud: bool = False) -> tuple[str, str]:
        if force_cloud:
            result = await self.cloud_client.generate(prompt)
            return result, "cloud"

        try:
            result = await self.local_client.generate(prompt)
            return result, "local"
        except LLMError:
            result = await self.cloud_client.generate(prompt)
            return result, "cloud"

    async def close(self) -> None:
        await self.local_client.close()
        await self.cloud_client.close()
