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
# V3 ADDITIONS:
# {calibration_context}  — Phase 5: self-calibration bias warnings
# {active_improvements}  — Phase 6: learned prompt patches from
#                          the prompt evolution engine
# =============================================================

from langchain_core.prompts import ChatPromptTemplate


# ── SYSTEM PROMPT ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are FinTrac, a financial analyst AI.
You ONLY output a single JSON object. No other text, no markdown, no explanations.

REQUIRED OUTPUT — copy this structure exactly:
{{
  "action": "BUY",
  "confidence": 0.75,
  "reasoning": "explanation here",
  "risk_flags": ["risk 1", "risk 2"],
  "alternatives": [{{"ticker": "CVX", "reason": "why"}}],
  "data_gaps": []
}}

action must be exactly one of: BUY, HOLD, AVOID
confidence must be a float between 0.0 and 1.0
reasoning must reference the data provided, max 150 words
Do NOT include any fields other than these six.
Do NOT wrap in markdown code fences.

IMPORTANT: If calibration warnings or learned improvement rules are provided
below, you MUST follow them strictly. These rules come from analyzing your
own past prediction accuracy. They exist because you have been wrong in
specific, measurable ways. Ignoring them will produce the same errors.
"""


# ── INVESTMENT EVALUATION PROMPT ───────────────────────────────────────────────

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

{calibration_context}

{active_improvements}

{rag_context}

REMINDER — your entire response must be ONLY this JSON structure, nothing else:
{{"action": "BUY|HOLD|AVOID", "confidence": 0.0-1.0, "reasoning": "...", "risk_flags": [...], "alternatives": [...], "data_gaps": [...]}}
"""),
])


# ── COMPARISON PROMPT ──────────────────────────────────────────────────────────

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


# ── HELPERS ───────────────────────────────────────────────────────────────────

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
