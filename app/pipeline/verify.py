import time
from typing import List

from app.config import get_config
from app.llm.router import LLMRouter
from app.models.requests import VerifyRequest
from app.models.responses import Source, VerifyResponse
from app.pipeline.retrieval import RetrievalModule


VERDICT_PROMPT = """You are a fact-checking assistant. Given a claim and supporting sources, determine if the claim is true, false, or uncertain.

Claim: {query}

Sources:
{sources}

Respond with a JSON object containing:
- truth_score: a float between 0.0 (clearly false) and 1.0 (clearly true)
- verdict: "Likely True", "Likely False", or "Uncertain"
- explanation: a brief explanation of your reasoning

Respond ONLY with valid JSON."""


class VerificationPipeline:
    def __init__(self):
        self.retrieval = RetrievalModule()
        self.router = LLMRouter()
        self.config = get_config()

    async def verify(self, request: VerifyRequest) -> VerifyResponse:
        start_time = time.perf_counter()

        sources = await self.retrieval.retrieve(
            request.query, self.config.retrieval_top_k
        )

        sources_text = "\n\n".join(f"[Source: {s.title}]\n{s.content}" for s in sources)

        prompt = VERDICT_PROMPT.format(query=request.query, sources=sources_text)

        response_text, model_used = await self.router.generate(
            prompt, force_cloud=request.use_cloud
        )

        truth_score, verdict, explanation = self._parse_llm_response(response_text)

        latency_ms = (time.perf_counter() - start_time) * 1000

        return VerifyResponse(
            query=request.query,
            truth_score=truth_score,
            verdict=verdict,
            sources=sources,
            explanation=explanation,
            model_used=model_used,
            latency_ms=round(latency_ms, 2),
        )

    def _parse_llm_response(self, response: str) -> tuple[float, str, str]:
        import json
        import re

        json_match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return (
                    float(data.get("truth_score", 0.5)),
                    str(data.get("verdict", "Uncertain")),
                    str(data.get("explanation", "No explanation provided.")),
                )
            except (json.JSONDecodeError, ValueError):
                pass

        return 0.5, "Uncertain", response

    async def close(self) -> None:
        await self.router.close()
