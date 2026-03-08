# =============================================================
# src/agent/advisor_agent.py
#
# The core AI brain of FinTrac.
#
# This module is responsible for:
#   1. Connecting to Ollama (local Mistral)
#   2. Building the prompt from real market data
#   3. Sending it to the LLM
#   4. Parsing and validating the JSON response
#   5. Returning a clean Python object the route can use
#
# PRODUCTION SWAP (one change):
#   DEV:  llm = OllamaLLM(model="mistral", ...)
#   PROD: llm = ChatAnthropic(model="claude-sonnet-4-6", ...)
#         (pip install langchain-anthropic anthropic)
#
# Everything else — prompts, parsing, response models — stays
# identical. The LangChain abstraction layer is why.
# =============================================================

import json
import re
from typing import Optional

from langchain_ollama import OllamaLLM
from loguru import logger
from pydantic import BaseModel

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


# ── LLM INSTANCE ───────────────────────────────────────────────────────────────
# Created once at module load time — not per request.
# Creating an LLM connection on every request would be slow and wasteful.
#
# Parameters explained:
#   model       → which Ollama model to use (from .env via config)
#   base_url    → where Ollama is running (host.docker.internal from Docker)
#   temperature → 0.1 = near-deterministic. Financial analysis should be
#                 consistent, not creative. Higher values (0.7-0.9) produce
#                 more varied responses but also more hallucinations.
#   num_ctx     → context window size in tokens. 4096 is the safe limit
#                 for Mistral on 6GB VRAM. Going higher spills to RAM.
#   format      → "json" tells Ollama to enforce JSON output mode at the
#                 model level, not just through prompting. Belt + suspenders.

llm = OllamaLLM(
    model       = settings.OLLAMA_MODEL,
    base_url    = settings.OLLAMA_BASE_URL,
    temperature = 0.1,
    num_ctx     = 4096,
    format      = "json",
)


# ── RESPONSE MODELS ────────────────────────────────────────────────────────────
# These Pydantic models define the shape of what we expect back from the AI.
# If the AI returns malformed JSON or missing fields, Pydantic catches it
# here rather than letting bad data flow into the route response.

class AlternativeAsset(BaseModel):
    ticker: str
    reason: str


class InvestmentVerdict(BaseModel):
    action:       str                           # BUY / HOLD / AVOID
    confidence:   float                         # 0.0 – 1.0
    reasoning:    str                           # AI explanation
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
    recommended_allocation: dict[str, float]    # {"AAPL": 60.0, "XOM": 40.0}
    overall_reasoning:      str
    risk_flags:             list[str] = []


# ── JSON EXTRACTION ────────────────────────────────────────────────────────────
# Even with format="json" and strict prompting, LLMs occasionally wrap
# their JSON in markdown code fences: ```json { ... } ```
# This function strips that noise before we try to parse.

def _extract_json(raw: str) -> str:
    """
    Strip markdown code fences and whitespace from LLM output.
    Returns a clean JSON string ready for json.loads().
    """
    # Remove ```json ... ``` or ``` ... ``` wrappers
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    return cleaned


# ── PING ───────────────────────────────────────────────────────────────────────
# Called during app startup (main.py lifespan) to confirm Ollama is reachable
# and the model is loaded before we start accepting requests.
# A short prompt is enough — we just need a response, not a useful one.

async def ping_ollama() -> bool:
    """
    Verify Ollama is reachable and the model responds.
    Returns True if healthy, False if not.
    """
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
# This is the function analysis.py calls to get the AI verdict.
#
# FLOW:
#   1. Build the prompt by substituting real data into the template
#   2. Send to Mistral via Ollama (blocking call in thread pool)
#   3. Extract and parse the JSON response
#   4. Validate with Pydantic
#   5. Return InvestmentVerdict or None on failure
#
# Why async + thread pool again?
# OllamaLLM.invoke() is synchronous and blocks for 5-30 seconds
# while Mistral generates. Same pattern as yf_client — we must
# run it in a thread pool to keep FastAPI responsive.

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

    # ── BUILD PROMPT ──────────────────────────────────────────
    # format_messages() substitutes all {placeholders} with real values
    # and returns a list of LangChain message objects ready for the LLM.

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
    )

    # Convert LangChain message objects to a single string for OllamaLLM
    # (OllamaLLM takes a string; ChatOllama takes messages — we use the
    # simpler OllamaLLM here because it has better JSON mode support)
    prompt_text = "\n\n".join(
        f"[{m.type.upper()}]\n{m.content}" for m in messages
    )

    logger.info(f"Sending evaluation prompt for {snapshot.ticker} to Mistral")

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
        logger.info(
            f"Verdict for {snapshot.ticker}: {verdict.action} "
            f"(confidence: {verdict.confidence:.0%})"
        )
        return verdict

    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.error(
            f"Failed to parse Mistral response for {snapshot.ticker}: {e}\n"
            f"Raw response: {raw_response}"
        )
        return None


# ── COMPARISON VERDICT ─────────────────────────────────────────────────────────
# Same pattern as get_investment_verdict but uses COMPARISON_PROMPT
# and returns a ComparisonVerdict with rankings and allocation.

async def get_comparison_verdict(
    snapshots:     list[MarketSnapshot],
    budget:        float,
    horizon_years: Optional[int],
    risk_tolerance: Optional[str],
) -> Optional[ComparisonVerdict]:
    """
    Compare multiple assets and return ranked recommendations.
    """
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