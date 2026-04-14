# =============================================================
# src/agent/advisor_agent.py
#
# The core AI brain of FinTrac.
#
# V3 Phase 5: Calibration context injection + confidence correction
# V3 Phase 6: Active improvement patches injected into prompt.
#             The prompt_evolver generates rules from failure analysis,
#             and this module loads them alongside calibration warnings.
#             The AI now sees both statistical bias corrections AND
#             targeted behavioral rules derived from its own mistakes.
#
# PRODUCTION SWAP (one change):
#   DEV:  llm = OllamaLLM(model="mistral", ...)
#   PROD: llm = ChatAnthropic(model="claude-sonnet-4-6", ...)
# =============================================================

import json
import re
from typing import Optional

from langchain_ollama import OllamaLLM
from loguru import logger
from pydantic import BaseModel

from src.agent.rag_pipeline import retrieve_context, format_rag_context
from src.agent.prompts import (
    INVESTMENT_PROMPT,
    COMPARISON_PROMPT,
    format_projection,
    format_horizon,
    format_assets_for_comparison,
)
from src.api.schemas.investment import (
    InvestmentQuery,
    MarketSnapshot,
    BudgetProjection,
)
from src.config import settings

# V3 Phase 5 — calibration
from src.engine.calibration_engine import (
    get_calibration_context,
    format_calibration_for_prompt,
    apply_confidence_correction,
)

# V3 Phase 6 — prompt evolution
from src.engine.prompt_evolver import (
    get_active_improvements,
    format_improvements_for_prompt,
    get_active_prompt_version,
)


# ── LLM INSTANCE ───────────────────────────────────────────────────────────────

llm = OllamaLLM(
    model       = settings.OLLAMA_MODEL,
    base_url    = settings.OLLAMA_BASE_URL,
    temperature = 0.1,
    num_ctx     = 4096,
    format      = "json",
)


# ── RESPONSE MODELS ────────────────────────────────────────────────────────────

class AlternativeAsset(BaseModel):
    ticker: str
    reason: str


class InvestmentVerdict(BaseModel):
    action:       str
    confidence:   float
    reasoning:    str
    risk_flags:   list[str]       = []
    alternatives: list[AlternativeAsset] = []
    data_gaps:    list[str]       = []


class RankedAsset(BaseModel):
    rank:      int
    ticker:    str
    action:    str
    score:     float
    reasoning: str


class ComparisonVerdict(BaseModel):
    ranking:                list[RankedAsset]
    recommended_allocation: dict[str, float]
    overall_reasoning:      str
    risk_flags:             list[str] = []


# ── JSON EXTRACTION ────────────────────────────────────────────────────────────

def _extract_json(raw: str) -> str:
    """Strip markdown code fences and whitespace from LLM output."""
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    return cleaned


# ── PING ───────────────────────────────────────────────────────────────────────

async def ping_ollama() -> bool:
    """Verify Ollama is reachable and the model responds."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    def _ping():
        try:
            result = llm.invoke("ping")
            return bool(result)
        except Exception as e:
            logger.error(f"Ollama ping failed: {e}")
            return False

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        healthy = await loop.run_in_executor(pool, _ping)

    if healthy:
        logger.info(f"Ollama reachable — model: {settings.OLLAMA_MODEL}")
    else:
        logger.warning("Ollama not reachable — AI verdicts will be unavailable")

    return healthy


# ── CORE: GET INVESTMENT VERDICT ───────────────────────────────────────────────
# FLOW:
#   1. Load active calibration profiles for this sector      (Phase 5)
#   2. Load active improvement patches                       (Phase 6)
#   3. Build the prompt with all context injected
#   4. Send to Mistral via Ollama
#   5. Parse and validate JSON response
#   6. Apply calibration confidence correction                (Phase 5)
#   7. Return InvestmentVerdict with prompt_version metadata  (Phase 6)

async def get_investment_verdict(
    query:      InvestmentQuery,
    snapshot:   MarketSnapshot,
    projection: Optional[BudgetProjection],
) -> Optional[InvestmentVerdict]:
    """
    Ask Mistral to evaluate an investment and return a structured verdict.
    Returns None if Ollama is unavailable or returns unparseable output.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    # ── V3 PHASE 5: LOAD CALIBRATION CONTEXT ──────────────────
    calibration_profiles = []
    calibration_text = ""
    try:
        calibration_profiles = await get_calibration_context(
            sector=snapshot.sector,
            asset_class='EQUITY',
        )
        calibration_text = format_calibration_for_prompt(calibration_profiles)
        
        if calibration_profiles:
            logger.info(
                f"V3: Loaded {len(calibration_profiles)} calibration profiles "
                f"for {snapshot.ticker} ({snapshot.sector})"
            )
    except Exception as e:
        logger.warning(f"V3: Failed to load calibration context: {e}")

    # ── V3 PHASE 6: LOAD ACTIVE IMPROVEMENTS ──────────────────
    active_improvements = []
    improvements_text = ""
    prompt_version = "v1.0.0"
    try:
        active_improvements = await get_active_improvements()
        improvements_text = format_improvements_for_prompt(active_improvements)
        prompt_version = get_active_prompt_version(active_improvements)
        
        if active_improvements:
            logger.info(
                f"V3: Loaded {len(active_improvements)} active improvement patches "
                f"(prompt version: {prompt_version})"
            )
    except Exception as e:
        logger.warning(f"V3: Failed to load active improvements: {e}")

    # ── RAG RETRIEVAL ─────────────────────────────────────────
    rag_query = (
        query.question
        or f"{snapshot.ticker} financial risks outlook revenue"
    )
    passages   = await retrieve_context(rag_query, snapshot.ticker, top_k=2)
    rag_context = format_rag_context(passages)

    if passages:
        logger.info(
            f"Injecting {len(passages)} RAG passages into prompt for "
            f"{snapshot.ticker} (top source: {passages[0]['doc_type']} "
            f"{passages[0]['filed_at'][:10]})"
        )

    # ── BUILD PROMPT ──────────────────────────────────────────
    messages = INVESTMENT_PROMPT.format_messages(
        budget          = query.budget,
        ticker          = snapshot.ticker,
        horizon         = format_horizon(
                            query.horizon_years or 3,
                            query.horizon_years or 30,
                          ),
        risk_tolerance  = (query.risk_tolerance.value
                           if query.risk_tolerance else "not specified"),
        question        = query.question or "General investment evaluation.",
        company_name    = snapshot.company_name    or "N/A",
        sector          = snapshot.sector          or "N/A",
        industry        = snapshot.industry        or "N/A",
        current_price   = snapshot.current_price   or "N/A",
        currency        = snapshot.currency        or "USD",
        market_cap      = f"{snapshot.market_cap/1e9:.1f}B" if snapshot.market_cap else "N/A",
        pe_ratio        = snapshot.pe_ratio        or "N/A",
        forward_pe      = snapshot.forward_pe      or "N/A",
        pb_ratio        = snapshot.pb_ratio        or "N/A",
        beta            = snapshot.beta            or "N/A",
        dividend_yield  = f"{snapshot.dividend_yield*100:.2f}" if snapshot.dividend_yield else "N/A",
        fifty_two_week_high = snapshot.fifty_two_week_high or "N/A",
        fifty_two_week_low  = snapshot.fifty_two_week_low  or "N/A",
        avg_volume      = f"{snapshot.avg_volume/1e6:.1f}M" if snapshot.avg_volume else "N/A",
        analyst_target_price = snapshot.analyst_target_price or "N/A",
        projection_text = format_projection(projection),
        calibration_context = calibration_text,       # Phase 5
        active_improvements = improvements_text,      # Phase 6
        rag_context     = rag_context,
    )

    prompt_text = "\n\n".join(
        f"[{m.type.upper()}]\n{m.content}" for m in messages
    )

    logger.info(
        f"Sending evaluation prompt for {snapshot.ticker} to Mistral "
        f"(prompt_version={prompt_version})"
    )

    # ── INVOKE LLM IN THREAD POOL ─────────────────────────────
    def _invoke():
        return llm.invoke(prompt_text)

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            raw_response = await loop.run_in_executor(pool, _invoke)
        except Exception as e:
            logger.error(f"Ollama invocation failed: {e}")
            return None

    logger.debug(f"Raw Mistral response for {snapshot.ticker}: {raw_response[:200]}...")

    # ── PARSE RESPONSE ────────────────────────────────────────
    try:
        clean_json  = _extract_json(raw_response)
        parsed_dict = json.loads(clean_json)
        verdict     = InvestmentVerdict(**parsed_dict)
        
        # ── V3 PHASE 5: APPLY CALIBRATION CORRECTION ──────────
        if calibration_profiles:
            original_confidence = verdict.confidence
            adjusted_confidence = apply_confidence_correction(
                verdict.confidence,
                calibration_profiles,
            )
            
            if adjusted_confidence != original_confidence:
                verdict.confidence = adjusted_confidence
                logger.info(
                    f"V3: Confidence adjusted for {snapshot.ticker}: "
                    f"{original_confidence:.2f} → {adjusted_confidence:.2f} "
                    f"({len(calibration_profiles)} corrections applied)"
                )
        
        logger.info(
            f"Verdict for {snapshot.ticker}: {verdict.action} "
            f"(confidence: {verdict.confidence:.0%}, "
            f"prompt: {prompt_version})"
        )
        return verdict

    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.error(
            f"Failed to parse Mistral response for {snapshot.ticker}: {e}\n"
            f"Raw response: {raw_response}"
        )
        return None


# ── COMPARISON VERDICT ─────────────────────────────────────────────────────────

async def get_comparison_verdict(
    snapshots:     list[MarketSnapshot],
    budget:        float,
    horizon_years: Optional[int],
    risk_tolerance: Optional[str],
) -> Optional[ComparisonVerdict]:
    """Compare multiple assets and return ranked recommendations."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    messages = COMPARISON_PROMPT.format_messages(
        budget          = budget,
        horizon         = format_horizon(horizon_years or 3, horizon_years or 30),
        risk_tolerance  = risk_tolerance or "not specified",
        assets_text     = format_assets_for_comparison(snapshots),
    )

    prompt_text = "\n\n".join(
        f"[{m.type.upper()}]\n{m.content}" for m in messages
    )

    logger.info(
        f"Sending comparison prompt for "
        f"{[s.ticker for s in snapshots]} to Mistral"
    )

    def _invoke():
        return llm.invoke(prompt_text)

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            raw_response = await loop.run_in_executor(pool, _invoke)
        except Exception as e:
            logger.error(f"Ollama comparison invocation failed: {e}")
            return None

    try:
        clean_json  = _extract_json(raw_response)
        parsed_dict = json.loads(clean_json)
        verdict     = ComparisonVerdict(**parsed_dict)
        return verdict

    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.error(f"Failed to parse comparison response: {e}")
        return None
