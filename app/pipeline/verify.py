import asyncio
import time
import json
import re
import statistics
from typing import List, Dict

from app.config import get_config
from app.llm.router import LLMRouter
from app.models.requests import VerifyRequest
from app.models.responses import Source, SourceIndependence, VerifyResponse
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

OFFICIAL_CLAIM_PROMPT = """Determine whether the following claim originates from or is
attributed to a politician, political party, government body, or state official.
This includes claims like "PM said...", "Government announces...", "Ministry reports...",
"According to BJP/Congress/AAP...", or any claim where the source is an authority figure.

Claim: {query}

Respond ONLY with valid JSON:
{{
  "is_official": <true or false>,
  "claimant_type": "<politician|government|party|military|none>",
  "note": "<brief note on who is making the claim, if identifiable>"
}}
"""

JUDGE_PROMPT = """You are an investigative truth engine designed to resist state-level
disinformation. Analyze the claim against the evidence below.

## Source Reliability Tiers
  Tier 1 = Global Wire Services (Reuters, AP, AFP) — highest weight
  Tier 2 = IFCN-Certified Fact-Checkers (Snopes, AltNews, BoomLive) — high weight
  Tier 3 = Mainstream News — moderate weight
  Tier 4 = Ideological/Opinion — low weight
  Tier 5 = Known disinfo sources — treat as counter-evidence

  Sources marked ⚠GOVT-WIRE (e.g., ANI, PTI) are government-aligned wire services.
  They often republish official press releases verbatim. Do NOT treat multiple
  GOVT-WIRE sources as independent confirmation — they may all trace back to
  a single government statement.

## Circular Reporting Detection
  CRITICAL: Before scoring, check if multiple sources are reporting the SAME
  original claim from the SAME original source. Signs of circular reporting:
  - Multiple articles quoting the same press release or tweet
  - Phrases like "according to sources" or "as reported by ANI" appearing across articles
  - All articles published within minutes of each other with identical wording
  If you detect circular reporting, explicitly reduce your confidence and note it.

## Multi-Region Narrative Analysis
  Sources are tagged with their geographic region [India], [International], [UK/Europe].
  {narrative_divergence_instruction}

## Source Independence Report
  - Unique source domains: {unique_domains}
  - Regions with coverage: {region_coverage}
  - Government-aligned source ratio: {govt_aligned_ratio:.0%}
  - Circular reporting risk: {circular_warning}
  {dominant_domain_note}

## Official Claim Context
  {official_claim_context}

## Rules
  - If a Tier 2 (IFCN fact-checker) has already rated this claim, defer to their rating.
  - If a Tier 1 source (non-govt-aligned) explicitly debunks the claim, weight heavily.
  - If only domestic media or GOVT-WIRE sources support the claim but international
    sources contradict or ignore it, be highly skeptical.
  - If the claim is attributed to a politician/government, demand INDEPENDENT
    corroboration from non-govt sources. A government saying something does NOT
    make it true — look for third-party data or international verification.
  - Base your score on the EVIDENCE, not on your prior knowledge alone.

Claim: {query}
Rhetoric Analysis: {analysis_details} (Rhetoric Score: {rhetoric_score:.2f})

Evidence:
{sources}

Respond ONLY with valid JSON:
{{
  "truth_score": <float 0.0-1.0>,
  "verdict": "<Likely True|Likely False|Uncertain>",
  "explanation": "<detailed reasoning. Cite specific sources. Note contradictions between regions. Flag circular reporting if detected. If govt-aligned sources dominate, say so explicitly.>"
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
    Models that return extreme scores are given slightly less weight
    to guard against hallucination.
    """
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

        # STEP 1: Run three independent analyses concurrently
        # - Query reformulation
        # - Rhetoric/propaganda analysis
        # - Official claim detection
        reformulate_task = asyncio.create_task(
            self._reformulate_query(request.query)
        )
        analyzer_task = asyncio.create_task(
            self._analyze_rhetoric(request.query)
        )
        official_task = asyncio.create_task(
            self._detect_official_claim(request.query)
        )

        search_queries = await reformulate_task
        rhetoric_score, analysis_details = await analyzer_task
        is_official, claimant_type, official_note = await official_task

        # STEP 2: Multi-region live search with reformulated queries
        max_results = min(8, config.retrieval_top_k * 2)
        all_sources: List[Source] = []
        seen_urls: set = set()
        combined_independence: Dict = {}

        for q in search_queries:
            results, independence_meta = await self.searcher.search(
                q,
                max_results=max_results,
                fact_check_api_key=config.fact_check_api_key,
            )
            # Merge independence meta (keep the one with most data)
            if (
                not combined_independence
                or independence_meta.get("unique_domains", 0)
                > combined_independence.get("unique_domains", 0)
            ):
                combined_independence = independence_meta

            for src in results:
                url_line = next(
                    (l for l in src.content.splitlines() if l.startswith("URL:")),
                    "",
                )
                url = url_line.replace("URL:", "").strip()
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_sources.append(src)

        # Cap total sources
        sources = all_sources[:15]
        sources_text = (
            "\n\n---\n\n".join(f"{s.title}\n{s.content}" for s in sources)
            if sources
            else "No live web sources found."
        )

        # STEP 3: Detect narrative divergence between regions
        narrative_divergence = self._detect_narrative_divergence(sources)

        # Build dynamic judge prompt sections
        if narrative_divergence:
            narrative_instruction = (
                "⚠ NARRATIVE DIVERGENCE DETECTED: Indian/domestic sources and "
                "international sources appear to tell DIFFERENT stories about this "
                "claim. This is a strong signal of potential state-controlled "
                "narrative. Weight international sources MORE heavily and explain "
                "the divergence in your response."
            )
        else:
            narrative_instruction = (
                "No significant narrative divergence detected between regions."
            )

        meta = combined_independence
        circular_warning = (
            "⚠ HIGH — over 50% of sources come from one domain"
            if meta.get("single_origin_warning")
            else "Low"
        )
        dominant_note = (
            f"  - Dominant source domain: {meta.get('dominant_domain', 'N/A')}"
            if meta.get("single_origin_warning")
            else ""
        )

        if is_official:
            official_context = (
                f"⚠ THIS IS AN OFFICIAL/POLITICAL CLAIM (type: {claimant_type}). "
                f"{official_note}\n"
                f"  Apply heightened scrutiny. A government or politician making a "
                f"claim is NOT evidence of its truth. Look for INDEPENDENT data, "
                f"international verification, or fact-checker rulings."
            )
        else:
            official_context = "This claim does not appear to originate from an official/political source."

        # STEP 4: Swarm Consensus Judging
        judge_prompt = JUDGE_PROMPT.format(
            query=request.query,
            analysis_details=analysis_details,
            rhetoric_score=rhetoric_score,
            sources=sources_text,
            narrative_divergence_instruction=narrative_instruction,
            unique_domains=meta.get("unique_domains", 0),
            region_coverage=", ".join(meta.get("region_coverage", [])),
            govt_aligned_ratio=meta.get("govt_aligned_ratio", 0),
            circular_warning=circular_warning,
            dominant_domain_note=dominant_note,
            official_claim_context=official_context,
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
                source_independence=SourceIndependence(
                    unique_domains=meta.get("unique_domains", 0),
                    region_coverage=meta.get("region_coverage", []),
                    govt_aligned_ratio=meta.get("govt_aligned_ratio", 0),
                    single_origin_warning=meta.get("single_origin_warning", False),
                    dominant_domain=meta.get("dominant_domain") or "",
                    narrative_divergence=narrative_divergence,
                ),
                is_official_claim=is_official,
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

        # STEP 6: Apply penalties
        # 6a. Rhetoric penalty — pull toward uncertainty
        rhetoric_pull = rhetoric_score * 0.15
        if raw_truth_score > 0.5:
            adjusted_score = raw_truth_score - rhetoric_pull
        else:
            adjusted_score = raw_truth_score + rhetoric_pull

        # 6b. Official claim penalty — if it's a political claim with
        #     high govt-aligned source ratio, apply additional skepticism
        official_penalty = 0.0
        if is_official and meta.get("govt_aligned_ratio", 0) > 0.4:
            official_penalty = 0.10
            if adjusted_score > 0.5:
                adjusted_score -= official_penalty
            else:
                adjusted_score += official_penalty

        # 6c. Circular reporting penalty
        circular_penalty = 0.0
        if meta.get("single_origin_warning"):
            circular_penalty = 0.08
            if adjusted_score > 0.5:
                adjusted_score -= circular_penalty
            else:
                adjusted_score += circular_penalty

        final_truth_score = max(0.0, min(1.0, adjusted_score))

        # Swarm agreement
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

        # Penalty disclosures
        penalties_applied = []
        if rhetoric_score > 0.4:
            penalties_applied.append(
                f"**Rhetoric Penalty** ({rhetoric_score:.2f}): "
                f"Claim uses manipulative language."
            )
        if official_penalty > 0:
            penalties_applied.append(
                f"**Official Claim Penalty** ({official_penalty:.2f}): "
                f"Claim attributed to {claimant_type}; "
                f"{meta.get('govt_aligned_ratio', 0):.0%} of sources are government-aligned wires."
            )
        if circular_penalty > 0:
            penalties_applied.append(
                f"**Circular Reporting Penalty** ({circular_penalty:.2f}): "
                f"Over 50% of sources come from {meta.get('dominant_domain', 'one domain')}."
            )
        if narrative_divergence:
            penalties_applied.append(
                "**Narrative Divergence Detected**: Domestic and international sources "
                "report different versions of this story."
            )

        if penalties_applied:
            consensus_expl += "---\n### Adjustments Applied:\n"
            for p in penalties_applied:
                consensus_expl += f"- {p}\n"

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
            source_independence=SourceIndependence(
                unique_domains=meta.get("unique_domains", 0),
                region_coverage=meta.get("region_coverage", []),
                govt_aligned_ratio=meta.get("govt_aligned_ratio", 0),
                single_origin_warning=meta.get("single_origin_warning", False),
                dominant_domain=meta.get("dominant_domain") or "",
                narrative_divergence=narrative_divergence,
            ),
            is_official_claim=is_official,
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

    async def _detect_official_claim(self, query: str) -> tuple[bool, str, str]:
        """
        Detect if the claim originates from a politician or government body.
        Returns (is_official, claimant_type, note).
        """
        try:
            prompt = OFFICIAL_CLAIM_PROMPT.format(query=query)
            text, _ = await self.router.generate(prompt)
            return self._parse_official_response(text)
        except Exception as e:
            print(f"Official claim detection failed: {e}")
            return False, "none", ""

    def _detect_narrative_divergence(self, sources: List[Source]) -> bool:
        """
        Heuristic: check if sources from different regions exist.
        If India-region and International-region sources are both present,
        the judge prompt will instruct the LLM to compare them.
        True narrative divergence scoring is done by the judge LLM itself,
        but we flag it as a possibility whenever multi-region sources exist.
        """
        regions_found = set()
        for s in sources:
            if "[India]" in s.title:
                regions_found.add("domestic")
            elif "[International]" in s.title or "[UK/Europe]" in s.title:
                regions_found.add("international")
        # If we have both domestic and international sources, flag for comparison
        return "domestic" in regions_found and "international" in regions_found

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

    def _parse_official_response(self, response: str) -> tuple[bool, str, str]:
        start = response.find("{")
        end = response.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(response[start:end + 1])
                return (
                    bool(data.get("is_official", False)),
                    str(data.get("claimant_type", "none")),
                    str(data.get("note", "")),
                )
            except (json.JSONDecodeError, ValueError):
                pass
        return False, "none", ""

    async def close(self) -> None:
        await self.router.close()
        await self.searcher.close()
