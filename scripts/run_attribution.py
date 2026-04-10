#!/usr/bin/env python3
# =============================================================
# scripts/run_attribution.py
#
# Manual attribution analysis trigger for testing
# Usage: python scripts/run_attribution.py
# =============================================================

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.attribution_engine import run_attribution_analysis


async def main():
    print("🔍 Running attribution analysis...")
    stats = await run_attribution_analysis()
    
    print("\n" + "="*60)
    print("📊 Attribution Analysis Results")
    print("="*60)
    print(f"Predictions analyzed: {stats['predictions_analyzed']}")
    print(f"Attributions created: {stats['attributions_created']}")
    print(f"Avg per prediction:   {stats['avg_attributions_per_prediction']:.1f}")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
