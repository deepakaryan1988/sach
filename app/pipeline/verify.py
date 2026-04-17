import time
from typing import List
import json
import re
import statistics

from app.config import get_config
from app.llm.router import LLMRouter
from app.models.requests import VerifyRequest
from app.models.responses import Source, VerifyResponse
from app.pipeline.search import LiveSearchModule

ANALYZER_PROMPT = """Analyze the following claim for propaganda rhetoric, high emotional valence, logical fallacies, or known coordination markers.
Claim: {query}

Respond ONLY with valid JSON containing:
- rhetoric_score: float (0.0 means neutral/factual language, 1.0 means highly manipulative/propaganda)
- analysis_details: str (A brief note on the observed rhetoric or emotional manipulation)
"""

JUDGE_PROMPT = """You are an investigative truth engine. Analyze the following claim against the retrieved live web sources. 
The sources have been tagged with a Tier (1 = Global Wire, 2 = Independent Fact-Checkers, 3 = Mainstream, 4 = Extreme/Ideological).
Pay attention to contradictions. If a Tier 1 or 2 source debunks the claim, weigh it heavily. If only Tier 4 sources report the claim, be highly skeptical.

Claim: {query}
Rhetoric Analysis of Claim: {analysis_details} (Rhetoric Score: {rhetoric_score})

Sources:
{sources}

Respond ONLY with valid JSON containing:
- truth_score: float between 0.0 (clearly false) and 1.0 (clearly true)
- verdict: "Likely True", "Likely False", or "Uncertain"
- explanation: A detailed explanation of your reasoning. Identify contradictions. Mention if low-tier sources differ from high-tier ones.
"""

class VerificationPipeline:
    def __init__(self):
        self.searcher = LiveSearchModule()
        self.router = LLMRouter()
        self.config = get_config()

    async def verify(self, request: VerifyRequest) -> VerifyResponse:
        start_time = time.perf_counter()

        # STEP 1: Analyzer (Propaganda Detection)
        analyzer_prompt = ANALYZER_PROMPT.format(query=request.query)
        analyzer_res_text, model_used = await self.router.generate(
            analyzer_prompt, force_cloud=request.use_cloud
        )
        rhetoric_score, analysis_details = self._parse_analyzer_response(analyzer_res_text)

        # STEP 2: Live Search
        max_results = min(10, self.config.retrieval_top_k * 2) # Pull more results for live web
        sources = await self.searcher.search(request.query, max_results=max_results)
        sources_text = "\n\n".join(f"[Source: {s.title}]\n{s.content}" for s in sources)

        if not sources:
            sources_text = "No live web sources found."

        # STEP 3: The Judge (Swarm Consensus)
        judge_prompt = JUDGE_PROMPT.format(
            query=request.query, 
            analysis_details=analysis_details, 
            rhetoric_score=rhetoric_score, 
            sources=sources_text
        )
        
        config = get_config()
        openrouter_raw = config.openrouter_swarm or "meta-llama/llama-3.3-70b-instruct:free"
        nvidia_raw = config.nvidia_swarm or "meta/llama-3.3-70b-instruct,google/gemma-2b-it"
        
        openrouter_models = [m.strip() for m in openrouter_raw.split(",") if m.strip()]
        nvidia_models = [m.strip() for m in nvidia_raw.split(",") if m.strip()]
        
        SWARM_MODELS = openrouter_models + nvidia_models
        
        swarm_outputs = await self.router.generate_swarm(
            judge_prompt, 
            openrouter_models=openrouter_models, 
            nvidia_models=nvidia_models
        )
        
        if not swarm_outputs:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return VerifyResponse(
                query=request.query,
                truth_score=0.0,
                verdict="Error",
                sources=sources,
                explanation="### System Warning\nAll upstream AI models (OpenRouter and NVIDIA) are currently rate-limited or offline.\n\n*Please ensure your API keys are valid and you have remaining credits/quota.*",
                rhetoric_score=rhetoric_score,
                swarm_agreement=0.0,
                analysis_details=analysis_details,
                model_used="Offline",
                latency_ms=round(latency_ms, 2)
            )
            
        scores = []
        swarm_details = []
        
        for i, (model_name, output) in enumerate(zip(SWARM_MODELS, swarm_outputs)):
            ts, _, expl = self._parse_judge_response(output)
            scores.append(ts)
            swarm_details.append(
                {
                    "model_name": model_name.split("/")[-1],
                    "truth_score": ts,
                    "explanation": expl,
                }
            )
            
        if scores:
            final_truth_score = sum(scores) / len(scores)
            swarm_agreement = 1.0 - (statistics.stdev(scores) if len(scores) > 1 else 0.0)
            # Ensure agreement is within 0.0 - 1.0
            swarm_agreement = max(0.0, min(1.0, swarm_agreement))
        else:
            final_truth_score = 0.5
            swarm_agreement = 0.0
            
        if final_truth_score > 0.65:
            final_verdict = "Likely True"
        elif final_truth_score < 0.35:
            final_verdict = "Likely False"
        else:
            final_verdict = "Uncertain"
            
        consensus_expl = "Unanimous Swarm Agreement:\n\n" if swarm_agreement > 0.8 else ("Debated Swarm Conclusion (%.0f%% Agreement):\n\n" % (swarm_agreement*100))
        
        for i, member in enumerate(swarm_details):
            consensus_expl += f"### Model {i+1} ({member['model_name']}):\n{member['explanation']}\n\n"

        latency_ms = (time.perf_counter() - start_time) * 1000

        return VerifyResponse(
            query=request.query,
            truth_score=round(final_truth_score, 2),
            verdict=final_verdict,
            sources=sources,
            explanation=consensus_expl,
            rhetoric_score=rhetoric_score,
            swarm_agreement=round(swarm_agreement, 2),
            analysis_details=analysis_details,
            swarm_details=swarm_details,
            model_used="swarm (3 models)",
            latency_ms=round(latency_ms, 2),
        )

    def _parse_analyzer_response(self, response: str) -> tuple[float, str]:
        start = response.find('{')
        end = response.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(response[start:end+1])
                return (
                    float(data.get("rhetoric_score", 0.0)),
                    str(data.get("analysis_details", "No detailed analysis found."))
                )
            except (json.JSONDecodeError, ValueError):
                pass
        return 0.0, "Parsing failed."

    def _parse_judge_response(self, response: str) -> tuple[float, str, str]:
        start = response.find('{')
        end = response.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(response[start:end+1])
                return (
                    float(data.get("truth_score", 0.5)),
                    str(data.get("verdict", "Uncertain")),
                    str(data.get("explanation", "No explanation provided."))
                )
            except (json.JSONDecodeError, ValueError):
                pass
        return 0.5, "Uncertain", response

    async def close(self) -> None:
        await self.router.close()
