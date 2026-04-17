import asyncio

from app.core.exceptions import LLMError
from app.llm.base import LLMInterface
from app.llm.ollama import OllamaClient
from app.llm.openrouter import OpenRouterClient
from app.llm.nvidia import NvidiaClient


class LLMRouter:
    def __init__(self):
        self.local_client = OllamaClient()
        self.cloud_client = OpenRouterClient()
        self.nvidia_client = NvidiaClient()

    async def generate(self, prompt: str, force_cloud: bool = False) -> tuple[str, str]:
        if force_cloud:
            try:
                result = await self.cloud_client.generate(prompt)
                return result, "cloud"
            except LLMError:
                # Fallback to Nvidia if cloud (OpenRouter) fails
                try:
                    result = await self.nvidia_client.generate(prompt)
                    return result, "nvidia"
                except LLMError:
                    raise

        # Sequence: Local -> OpenRouter -> Nvidia
        try:
            result = await self.local_client.generate(prompt)
            return result, "local"
        except LLMError:
            try:
                result = await self.cloud_client.generate(prompt)
                return result, "cloud"
            except LLMError:
                result = await self.nvidia_client.generate(prompt)
                return result, "nvidia"

    async def generate_swarm(self, prompt: str, openrouter_models: list[str], nvidia_models: list[str]) -> list[str]:
        tasks = []
        for m in openrouter_models:
            tasks.append(self.cloud_client.generate(prompt, model_override=m))
        for m in nvidia_models:
            tasks.append(self.nvidia_client.generate(prompt, model_override=m))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_results = []
        for result in results:
            if isinstance(result, Exception):
                print(f"Swarm model failed: {result}")
            else:
                valid_results.append(str(result))
        
        if not valid_results:
            print("Swarm completely failed. Falling back to Local Ollama.")
            try:
                local_res = await self.local_client.generate(prompt)
                valid_results.append(str(local_res))
            except Exception as e:
                print(f"Local fallback failed: {e}")
                
        return valid_results

    async def close(self) -> None:
        await self.local_client.close()
        await self.cloud_client.close()
        await self.nvidia_client.close()
