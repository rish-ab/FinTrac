#!/usr/bin/env python3
# =============================================================
# scripts/build_dataset.py
#
# Build a comprehensive prediction dataset for testing
# Creates predictions, evaluates them, and runs attribution
# =============================================================

import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from sqlalchemy import select, update
from src.db.session import AsyncSessionFactory
from src.db.v3_models import PredictionRecord
from src.engine.prediction_evaluator import run_prediction_evaluator
from src.engine.attribution_engine import run_attribution_analysis
from src.ingestion.event_ingester import ingest_latest_news


# Test stocks across different sectors
TEST_STOCKS = [
    # Technology
    {'ticker': 'AAPL', 'budget': 10000, 'horizon': 1},
    {'ticker': 'GOOGL', 'budget': 8000, 'horizon': 2},
    {'ticker': 'META', 'budget': 12000, 'horizon': 1},
    {'ticker': 'AMD', 'budget': 7000, 'horizon': 2},
    {'ticker': 'ORCL', 'budget': 9000, 'horizon': 3},
    
    # Healthcare
    {'ticker': 'PFE', 'budget': 6000, 'horizon': 2},
    {'ticker': 'UNH', 'budget': 15000, 'horizon': 3},
    {'ticker': 'ABBV', 'budget': 8000, 'horizon': 2},
    
    # Finance
    {'ticker': 'BAC', 'budget': 5000, 'horizon': 1},
    {'ticker': 'WFC', 'budget': 7000, 'horizon': 2},
    {'ticker': 'GS', 'budget': 10000, 'horizon': 3},
    
    # Energy
    {'ticker': 'CVX', 'budget': 12000, 'horizon': 2},
    {'ticker': 'COP', 'budget': 8000, 'horizon': 1},
    
    # Consumer
    {'ticker': 'WMT', 'budget': 9000, 'horizon': 2},
    {'ticker': 'HD', 'budget': 11000, 'horizon': 3},
    {'ticker': 'MCD', 'budget': 7000, 'horizon': 1},
    
    # Industrial
    {'ticker': 'BA', 'budget': 8000, 'horizon': 2},
    {'ticker': 'CAT', 'budget': 10000, 'horizon': 3},
    
    # Communication
    {'ticker': 'DIS', 'budget': 9000, 'horizon': 2},
    {'ticker': 'CMCSA', 'budget': 6000, 'horizon': 1},
]


async def create_prediction(ticker: str, budget: int, horizon: int) -> bool:
    """Create a prediction via API."""
    url = "http://localhost:8000/api/v1/analysis/evaluate"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                url,
                json={
                    "ticker": ticker,
                    "budget": budget,
                    "horizon_years": horizon,
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                verdict = data.get('ai_verdict', 'UNKNOWN')
                print(f"✅ {ticker:6s} → {verdict:10s} (horizon: {horizon}y)")
                return True
            else:
                error = response.json().get('detail', 'Unknown error')
                print(f"❌ {ticker:6s} → Failed: {error}")
                return False
        
        except Exception as e:
            print(f"❌ {ticker:6s} → Error: {str(e)[:50]}")
            return False


async def force_evaluate_all():
    """Force all pending predictions to be ready for evaluation."""
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            update(PredictionRecord)
            .where(PredictionRecord.evaluation_status == 'PENDING')
            .values(evaluation_due_at=datetime.utcnow())
        )
        await db.commit()
        
        count = result.rowcount
        print(f"\n⏰ Forced {count} predictions to be ready for evaluation")
        return count


async def main():
    print("="*70)
    print("🏗️  BUILDING COMPREHENSIVE PREDICTION DATASET")
    print("="*70)
    
    # Step 1: Ingest latest news
    print("\n📰 Step 1: Fetching latest market news...")
    news_count = await ingest_latest_news(max_articles=30)
    print(f"   Ingested {news_count} news articles")
    
    # Step 2: Create predictions
    print(f"\n🎯 Step 2: Creating predictions for {len(TEST_STOCKS)} stocks...")
    print("-"*70)
    
    success_count = 0
    for stock in TEST_STOCKS:
        success = await create_prediction(**stock)
        if success:
            success_count += 1
        await asyncio.sleep(0.5)  # Rate limiting
    
    print("-"*70)
    print(f"   Created {success_count}/{len(TEST_STOCKS)} predictions")
    
    # Wait for async prediction recording
    await asyncio.sleep(3)
    
    # Step 3: Force evaluate
    print("\n⚡ Step 3: Force-evaluating all predictions...")
    eval_count = await force_evaluate_all()
    
    # Step 4: Run evaluator
    print("\n🔍 Step 4: Running prediction evaluator...")
    await run_prediction_evaluator()
    
    # Step 5: Run attribution
    print("\n🔗 Step 5: Running attribution analysis...")
    attribution_stats = await run_attribution_analysis()
    
    # Step 6: Summary statistics
    print("\n" + "="*70)
    print("📊 DATASET BUILD COMPLETE")
    print("="*70)
    
    async with AsyncSessionFactory() as db:
        # Count predictions
        total_preds = await db.execute(
            select(PredictionRecord)
        )
        total = len(list(total_preds.scalars().all()))
        
        # Count evaluated
        eval_preds = await db.execute(
            select(PredictionRecord).where(
                PredictionRecord.evaluation_status == 'EVALUATED'
            )
        )
        evaluated = len(list(eval_preds.scalars().all()))
    
    print(f"Total predictions:     {total}")
    print(f"Evaluated:             {evaluated}")
    print(f"Predictions analyzed:  {attribution_stats['predictions_analyzed']}")
    print(f"Attributions created:  {attribution_stats['attributions_created']}")
    print(f"Avg per prediction:    {attribution_stats['avg_attributions_per_prediction']:.1f}")
    print("="*70)
    
    print("\n✨ Dataset ready for analysis! Run these queries to explore:")
    print("\n   # View accuracy by sector:")
    print("   docker exec -it fintrac_mariadb mariadb -u root -p")
    print("   SELECT sector, COUNT(*) as total, ")
    print("          SUM(po.is_direction_correct) as correct")
    print("   FROM prediction_record pr")
    print("   JOIN prediction_outcome po ON pr.id = po.prediction_id")
    print("   GROUP BY sector;")


if __name__ == "__main__":
    asyncio.run(main())
