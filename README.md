FinTrac: Multi-Modal Financial Intelligence Engine

FinTrac is an algorithmic trading & risk management system designed to bridge the gap between technical analysis and fundamental economic reality. Unlike standard automated systems that trade solely on price momentum, FinTrac integrates Macroeconomic Indicators (Yield Curves) and Natural Language Processing (SEC 10-K Sentiment) to validate trading decisions.

Key Features

1. The "AI Veto" (Risk Management)

Standard momentum algorithms often execute buy orders during asset bubbles immediately preceding a correction. FinTrac employs a local Small Language Model (FinBERT) to analyze corporate 10-K filings.

Logic: If Technicals = BUY but AI Sentiment = NEGATIVE, the trade is Vetoed.

Result: In backtesting scenarios, this mechanism prevented entry into deteriorating positions (e.g., Ford, FedEx) despite deceptive price rallies.

2. Personalized Risk Engine

Financial strategy requires personalization. FinTrac calculates a dynamic Trade Score (0-100) based on the user's real-time liquidity.

Aggressive Profile: Prioritizes momentum and sentiment signals.

Conservative Profile: Penalizes trades heavily during periods of credit stress, such as widening High-Yield Bond spreads.

3. Macro-Proxy Architecture

FinTrac engineers economic indicators from market relationships rather than relying solely on expensive external data feeds:

Labor Confidence: Derived from the ratio of Consumer Discretionary (XLY) versus Consumer Staples (XLP).

Credit Stress: Derived from High-Yield Bond ETF volatility.

Technical Stack

Core: Python 3.10, Pandas, NumPy

Machine Learning: PyTorch, HuggingFace Transformers (FinBERT)

Data Store: SQLite, YFinance

Visualization: Matplotlib, Seaborn

Deployment: Docker (Containerized Jupyter Environment)

Project Structure

FinTrac_V1/
├── data/                   # SQLite database and raw CSV files
├── model/                  # Local FinBERT weights (Excluded from version control)
├── notebooks/              # Interactive Analysis and Backtesting
│   └── FinTrac_Analysis.ipynb
├── src/                    # Source code modules
│   ├── user_init.py        # User transaction data generation
│   ├── macro_init.py       # Macroeconomic data fetching (FRED)
│   ├── sector_init.py      # Sector and market data (YFinance)
│   └── sec_init.py         # SEC EDGAR report crawling and NLP
├── Dockerfile              # Container configuration
├── requirements.txt        # Python dependencies
└── README.md               # Project documentation


Installation and Setup

Local Environment

Clone the repository:

git clone [https://github.com/yourusername/FinTrac_V1.git](https://github.com/yourusername/FinTrac_V1.git)
cd FinTrac_V1


Install dependencies:
It is recommended to use a virtual environment or Conda environment for dependency management.

pip install -r requirements.txt


Initialize Data:
Run the initialization scripts in the src directory to populate the local SQLite database.

python src/macro_init.py
python src/sector_init.py
python src/user_init.py


Docker Environment

Build the container:

docker build -t fintrac .


Run the container:

docker run -p 8888:8888 fintrac


Developer Notes

Current Version: 1.0

Data Sources: Data is fetched via public APIs (FRED, Yahoo Finance, SEC EDGAR). Rate limits may apply.

Model Weights: The NLP model uses pre-trained FinBERT weights. Ensure adequate disk space is available for model caching.

Future Roadmap

Event-Driven Probability Engine

Objective: To quantify the impact of exogenous shocks (e.g., executive controversies, regulatory bans) that technical indicators often miss.

Implementation: Development of a continuous training pipeline where a small language model ingests real-time news and correlates specific event types with subsequent price deviations.

Outcome: The system will output a "Probability Adjustment Factor." For example, if technicals are bullish on an EV stock, but news breaks regarding a country-wide ban, the model assigns a high probability of bearish reversal, overriding the technical signal.

Advanced Semantic Reasoning

Integration of fine-tuned Llama-3 models to parse complex financial nuances beyond simple sentiment scoring.

Real-Time Liquidity Integration

Expansion of user risk profiles to include real-time bank API integration for live liquidity tracking.
