# =============================================================
# src/agent/prompts.py
#
# All prompt templates live here, separated from the agent logic.
#
# WHY SEPARATE PROMPTS FROM LOGIC?
# Prompts are closer to content than code — they change frequently
# as you tune the AI's behaviour. Keeping them here means you can
# improve the AI's output without touching the agent logic at all.
# It also makes them easy to version, compare, and test.
#
# HOW THESE WORK WITH LANGCHAIN:
# ChatPromptTemplate takes a template string with {placeholder}
# variables. When the agent calls prompt.format_messages(...),
# LangChain substitutes the real values and returns a list of
# messages the LLM can consume. Think of it like Python's
# str.format() but typed and structured for LLM conversations.
# =============================================================

from langchain_core.prompts import ChatPromptTemplate


# ── SYSTEM PROMPT ──────────────────────────────────────────────────────────────
# The system prompt defines WHO the AI is and HOW it should behave.
# It runs once at the start of every conversation and sets the rules.
#
# Key decisions made here:
#   1. Persona: financial analyst, not a general assistant
#   2. Output format: strict JSON — makes parsing reliable
#   3. Honesty rule: explicitly told to flag data gaps
#   4. No fabrication rule: if data is missing, say so
#
# Why force JSON output?
# If we ask for free text, parsing the verdict out of a paragraph
# is fragile. JSON gives us a contract: we always know where the
# action, reasoning, and alternatives live in the response.

SYSTEM_PROMPT = """You are FinTrac, an expert financial analyst AI.
Your job is to evaluate investment opportunities based on real market data
and give honest, evidence-based recommendations.

You ALWAYS respond in valid JSON with exactly this structure:
{{
  "action": "BUY" | "HOLD" | "AVOID",
  "confidence": 0.0-1.0,
  "reasoning": "detailed explanation referencing the actual data provided",
  "risk_flags": ["list of specific risks identified from the data"],
  "alternatives": [
    {{
      "ticker": "TICKER",
      "reason": "why this might be better"
    }}
  ],
  "data_gaps": ["any important data that was missing or unavailable"]
}}

Rules:
- Base every statement on the data provided. Never invent numbers.
- If a metric is null, acknowledge it as a data gap, do not guess.
- alternatives should be genuine peers, not random suggestions.
- confidence reflects how complete the data is, not how good the investment is.
- Keep reasoning under 200 words but make every word count.
"""


# ── INVESTMENT EVALUATION PROMPT ───────────────────────────────────────────────
# This is the user-facing prompt that carries the actual market data
# and user context into the conversation.
#
# Structure of what we pass to Mistral:
#   - User's intent (budget, horizon, risk tolerance, question)
#   - Live market snapshot (price, P/E, beta, dividend yield etc.)
#   - Budget projection (what $X could become over N years)
#
# The {placeholders} are filled in by advisor_agent.py when it calls
# INVESTMENT_PROMPT.format_messages(...)

INVESTMENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", """
Evaluate this investment request and return your JSON analysis.

=== USER INTENT ===
Budget:          ${budget:,.0f} USD
Ticker:          {ticker}
Horizon:         {horizon}
Risk tolerance:  {risk_tolerance}
User question:   {question}

=== LIVE MARKET DATA ===
Company:         {company_name}
Sector:          {sector}
Industry:        {industry}
Current price:   ${current_price} {currency}
Market cap:      ${market_cap}
P/E ratio:       {pe_ratio}
Forward P/E:     {forward_pe}
P/B ratio:       {pb_ratio}
Beta:            {beta}
Dividend yield:  {dividend_yield}%
52-week high:    ${fifty_two_week_high}
52-week low:     ${fifty_two_week_low}
Avg daily volume:{avg_volume}
Analyst target:  ${analyst_target_price}

=== BUDGET PROJECTION (historical CAGR estimate) ===
{projection_text}

{rag_context}

Respond ONLY with the JSON object. No preamble, no explanation outside the JSON.
"""),
])


# ── COMPARISON PROMPT ──────────────────────────────────────────────────────────
# Used by the /compare endpoint when the user wants two or more assets
# evaluated side by side.
#
# The key difference from INVESTMENT_PROMPT:
# We pass ALL snapshots at once and ask for a ranked recommendation.
# This is more useful than running N separate evaluations because
# the AI can reason about RELATIVE value (e.g. "GOOGL's P/E is lower
# than AAPL's despite similar growth prospects").

COMPARISON_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", """
Compare these investment options for the same budget and horizon.
Rank them and recommend the best allocation.

=== USER INTENT ===
Budget:    ${budget:,.0f} USD
Horizon:   {horizon}
Risk:      {risk_tolerance}

=== ASSETS TO COMPARE ===
{assets_text}

Return JSON with this structure instead of the standard format:
{{
  "ranking": [
    {{
      "rank": 1,
      "ticker": "TICKER",
      "action": "BUY" | "HOLD" | "AVOID",
      "score": 0.0-10.0,
      "reasoning": "why this ranks here"
    }}
  ],
  "recommended_allocation": {{
    "TICKER": percentage_of_budget
  }},
  "overall_reasoning": "summary of the comparison",
  "risk_flags": ["cross-cutting risks that apply to multiple assets"]
}}

Respond ONLY with the JSON object.
"""),
])


# ── HELPER: FORMAT PROJECTION TEXT ────────────────────────────────────────────
# Small utility that converts a BudgetProjection object into a readable
# string for injection into the prompt. Lives here because it's
# prompt-formatting logic, not business logic.

def format_projection(projection) -> str:
    """Convert a BudgetProjection into a readable prompt string."""
    if projection is None:
        return "No projection available (insufficient historical data)."

    return (
        f"Initial: ${projection.initial_investment:,.0f} | "
        f"After {projection.horizon_years} years: "
        f"Low ${projection.projected_value_low:,.0f} / "
        f"Mid ${projection.projected_value_mid:,.0f} / "
        f"High ${projection.projected_value_high:,.0f} | "
        f"Assumed annual return: {projection.assumed_annual_return_pct:.1f}%"
    )


def format_horizon(horizon_min: int, horizon_max: int) -> str:
    """Format the horizon for display in the prompt."""
    if horizon_min == horizon_max:
        return f"{horizon_min} years"
    return f"{horizon_min}–{horizon_max} years (user did not specify)"


def format_assets_for_comparison(snapshots: list) -> str:
    """
    Format a list of MarketSnapshot objects into a readable
    block for the comparison prompt.
    """
    blocks = []
    for i, s in enumerate(snapshots, 1):
        block = f"""
Asset {i}: {s.ticker} — {s.company_name or 'Unknown'}
  Sector: {s.sector or 'N/A'} | Industry: {s.industry or 'N/A'}
  Price: ${s.current_price or 'N/A'} | Market cap: ${s.market_cap or 'N/A'}
  P/E: {s.pe_ratio or 'N/A'} | Forward P/E: {s.forward_pe or 'N/A'}
  Beta: {s.beta or 'N/A'} | Dividend yield: {s.dividend_yield or 'N/A'}%
  52w high: ${s.fifty_two_week_high or 'N/A'} | 52w low: ${s.fifty_two_week_low or 'N/A'}
  Analyst target: ${s.analyst_target_price or 'N/A'}"""
        blocks.append(block)
    return "\n".join(blocks)