import time
import json
import statistics
from typing import List

from app.config import get_config
from app.llm.router import LLMRouter
from app.models.requests import VerifyRequest
from app.models.responses import Source, VerifyResponse
from app.pipeline.search import LiveSearchModule

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

REFORMULATE_PROMPT = """You are a search query optimizer for a fact-checking engine.
Convert the following raw user claim into 1-3 concise, neutral search queries that will
return the most relevant fact-checking and news articles. Avoid emotionally charged language.
Focus on the core verifiable assertion.

Claim: {query}

Respond ONLY with valid JSON:
{{ "queries": ["<query1>", "<query2>", "<query3>"] }}
"""

ANALYZER_PROMPT = """Analyze the following claim for propaganda rhetoric, high emotional
valence, logical fallacies, or known disinformation coordination markers.

Claim: {query}

Respond ONLY with valid JSON:
{{
  "rhetoric_score": <float 0.0-1.0, where 0.0=neutral/factual, 1.0=highly manipulative>,
  "analysis_details": "<brief note on observed rhetoric, fallacies, or emotional framing>"
}}
"""

JUDGE_PROMPT = """You are an investigative truth engine. Analyze the claim against the
evidence below. Sources are tagged by reliability tier:
  Tier 1 = Global Wire Services (Reuters, AP) — highest weight
  Tier 2 = Dedicated Fact-Checkers (Snopes, AltNews, BoomLive) — high weight
  Tier 3 = Mainstream News — moderate weight
  Tier 4 = Ideological/Opinion — low weight
  Tier 5 = Known disinfo sources — treat as counter-evidence

Rules:
- If a Tier 1 or 2 source explicitly debunks the claim, weight that heavily toward False.
- If only Tier 4-5 sources support the claim, be highly skeptical.
- Contradictions between tiers must be explicitly noted.
- Base your score on the EVIDENCE, not on your prior knowledge alone.

Claim: {query}
Rhetoric Analysis: {analysis_details} (Rhetoric Score: {rhetoric_score:.2f})

Evidence:
{sources}

Respond ONLY with valid JSON:
{{
  "truth_score": <float 0.0-1.0>,
  "verdict": "<Likely True|Likely False|Uncertain>",
  "explanation": "<detailed reasoning citing specific sources and contradictions>"
}}
"""


def _weighted_median(scores: List[float], weights: List[float]) -> float:
    """
    Compute the weighted median of scores.
    More robust than mean — a single outlier model won't swing the result.
    """
    if not scores:
        return 0.5
    paired = sorted(zip(scores, weights), key=lambda x: x[0])
    total_weight = sum(w for _, w in paired)
    cumulative = 0.0
    for score, weight in paired:
        cumulative += weight
        if cumulative >= total_weight / 2:
            return score
    return paired[-1][0]


def _tier_weight(model_name: str, score: float) -> float:
    """
    Assign a confidence weight to each swarm model's output.
    Models that return extreme scores (very high or very low confidence)
    are given slightly less weight to guard against hallucination.
    """
    # Penalise models that are maximally confident — real evidence is rarely binary
    extremity_penalty = 1.0 - abs(score - 0.5) * 0.4
    return max(0.3, extremity_penalty)


class VerificationPipeline:
    def __init__(self):
        self.searcher = LiveSearchModule()
        self.router = LLMRouter()
        self.config = get_config()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    async def verify(self, request: VerifyRequest) -> VerifyResponse:
        start_time = time.perf_counter()
        config = get_config()

        # STEP 1: Query Reformulation
        search_queries = await self._reformulate_query(request.query)

        # STEP 2: Propaganda / Rhetoric Analysis (runs concurrently with search)
        import asyncio
        analyzer_task = asyncio.create_task(self._analyze_rhetoric(request.query))

        # STEP 3: Live Search (use reformulated queries, deduplicated)
        max_results = min(8, config.retrieval_top_k * 2)
        all_sources: List[Source] = []
        seen_urls: set = set()

        for q in search_queries:
            results = await self.searcher.search(
                q,
                max_results=max_results,
                fact_check_api_key=config.fact_check_api_key,
            )
            for src in results:
                # Deduplicate by URL (embedded in content)
                url_line = next((l for l in src.content.splitlines() if l.startswith("URL:")), "")
                url = url_line.replace("URL:", "").strip()
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_sources.append(src)

        # Cap total sources to avoid prompt overload
        sources = all_sources[:12]
        sources_text = "\n\n---\n\n".join(
            f"{s.title}\n{s.content}" for s in sources
        ) if sources else "No live web sources found."

        # Await rhetoric analysis
        rhetoric_score, analysis_details = await analyzer_task

        # STEP 4: Swarm Consensus Judging
        judge_prompt = JUDGE_PROMPT.format(
            query=request.query,
            analysis_details=analysis_details,
            rhetoric_score=rhetoric_score,
            sources=sources_text,
        )

        openrouter_raw = config.openrouter_swarm or "meta-llama/llama-3.3-70b-instruct:free"
        nvidia_raw = config.nvidia_swarm or "meta/llama-3.3-70b-instruct"

        openrouter_models = [m.strip() for m in openrouter_raw.split(",") if m.strip()]
        nvidia_models = [m.strip() for m in nvidia_raw.split(",") if m.strip()]
        swarm_model_names = openrouter_models + nvidia_models

        swarm_outputs = await self.router.generate_swarm(
            judge_prompt,
            openrouter_models=openrouter_models,
            nvidia_models=nvidia_models,
        )

        if not swarm_outputs:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return VerifyResponse(
                query=request.query,
                truth_score=0.0,
                verdict="Error",
                sources=sources,
                explanation=(
                    "### System Warning\n"
                    "All upstream AI models (OpenRouter and NVIDIA) are currently "
                    "rate-limited or offline.\n\n"
                    "*Please ensure your API keys are valid and you have remaining quota.*"
                ),
                rhetoric_score=rhetoric_score,
                swarm_agreement=0.0,
                analysis_details=analysis_details,
                model_used="Offline",
                latency_ms=round(latency_ms, 2),
            )

        # STEP 5: Aggregate swarm scores using weighted median
        scores: List[float] = []
        weights: List[float] = []
        swarm_details = []

        for model_name, output in zip(swarm_model_names, swarm_outputs):
            ts, _, expl = self._parse_judge_response(output)
            w = _tier_weight(model_name, ts)
            scores.append(ts)
            weights.append(w)
            swarm_details.append({
                "model_name": model_name.split("/")[-1],
                "truth_score": ts,
                "explanation": expl,
            })

        raw_truth_score = _weighted_median(scores, weights)

        # STEP 6: Apply rhetoric penalty
        # High rhetoric → shift truth score toward 0.5 (uncertainty) by up to 0.15
        rhetoric_pull = rhetoric_score * 0.15
        if raw_truth_score > 0.5:
            final_truth_score = raw_truth_score - rhetoric_pull
        else:
            final_truth_score = raw_truth_score + rhetoric_pull
        final_truth_score = max(0.0, min(1.0, final_truth_score))

        # Swarm agreement: 1 - normalised std dev
        swarm_agreement = (
            max(0.0, min(1.0, 1.0 - statistics.stdev(scores)))
            if len(scores) > 1
            else 1.0
        )

        # Verdict thresholds
        if final_truth_score > 0.65:
            final_verdict = "Likely True"
        elif final_truth_score < 0.35:
            final_verdict = "Likely False"
        else:
            final_verdict = "Uncertain"

        # Build explanation
        agreement_label = (
            "Unanimous Swarm Agreement"
            if swarm_agreement > 0.8
            else f"Debated Swarm Conclusion ({swarm_agreement * 100:.0f}% Agreement)"
        )
        consensus_expl = f"{agreement_label}:\n\n"
        for i, member in enumerate(swarm_details):
            consensus_expl += (
                f"### Model {i + 1} ({member['model_name']}):\n"
                f"{member['explanation']}\n\n"
            )
        if rhetoric_score > 0.4:
            consensus_expl += (
                f"---\n**Rhetoric Penalty Applied** (score: {rhetoric_score:.2f}): "
                f"The claim uses manipulative language. Truth score adjusted toward uncertainty.\n"
            )

        latency_ms = (time.perf_counter() - start_time) * 1000

        return VerifyResponse(
            query=request.query,
            truth_score=round(final_truth_score, 2),
            verdict=final_verdict,
            sources=sources,
            explanation=consensus_expl,
            rhetoric_score=round(rhetoric_score, 2),
            swarm_agreement=round(swarm_agreement, 2),
            analysis_details=analysis_details,
            swarm_details=swarm_details,
            model_used=f"swarm ({len(swarm_outputs)} models)",
            latency_ms=round(latency_ms, 2),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _reformulate_query(self, query: str) -> List[str]:
        """Use LLM to turn raw claim into optimised search queries."""
        try:
            prompt = REFORMULATE_PROMPT.format(query=query)
            text, _ = await self.router.generate(prompt)
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                data = json.loads(text[start:end + 1])
                queries = data.get("queries", [])
                if queries and isinstance(queries, list):
                    return [str(q) for q in queries[:3] if q]
        except Exception as e:
            print(f"Query reformulation failed: {e}")
        # Fallback: use the raw query
        return [query]

    async def _analyze_rhetoric(self, query: str) -> tuple[float, str]:
        """Run the rhetoric/propaganda analyzer."""
        try:
            prompt = ANALYZER_PROMPT.format(query=query)
            text, _ = await self.router.generate(prompt)
            return self._parse_analyzer_response(text)
        except Exception as e:
            print(f"Rhetoric analysis failed: {e}")
            return 0.0, "Analysis unavailable."

    def _parse_analyzer_response(self, response: str) -> tuple[float, str]:
        start = response.find("{")
        end = response.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(response[start:end + 1])
                return (
                    float(data.get("rhetoric_score", 0.0)),
                    str(data.get("analysis_details", "No detailed analysis found.")),
                )
            except (json.JSONDecodeError, ValueError):
                pass
        return 0.0, "Parsing failed."

    def _parse_judge_response(self, response: str) -> tuple[float, str, str]:
        start = response.find("{")
        end = response.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(response[start:end + 1])
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
        await self.searcher.close()
