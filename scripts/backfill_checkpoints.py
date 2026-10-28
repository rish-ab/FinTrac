#!/usr/bin/env python3
# =============================================================
# scripts/backfill_checkpoints.py
#
# Create 1m checkpoint predictions for existing long-horizon
# predictions (see prediction_evaluator.make_checkpoint_prediction),
# then evaluate any that are already due and re-run calibration.
# Safe to re-run: predictions that already have a checkpoint are skipped.
#
# Usage: python scripts/backfill_checkpoints.py
# =============================================================

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.session import engine
from src.engine.calibration_engine import run_calibration_engine
from src.engine.prediction_evaluator import (
    backfill_checkpoint_predictions, run_prediction_evaluator,
)


async def main():
    created = await backfill_checkpoint_predictions()
    print(f"Checkpoints created: {created}")

    print("Evaluating due predictions (fetches historical prices)...")
    await run_prediction_evaluator()

    result = await run_calibration_engine()
    print("\n" + "=" * 60)
    print("Calibration result")
    print("=" * 60)
    for key, value in result.items():
        print(f"{key}: {value}")

    # Close pooled connections while the event loop is still running
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
