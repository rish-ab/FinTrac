# FinTrac: Multi-Modal Financial Intelligence Engine

![Python](https://img.shields.io/badge/Python-3.10-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-blue)
![Status](https://img.shields.io/badge/Status-Portfolio_v1.0-orange)

**FinTrac** is an algorithmic trading & risk management system that bridges the gap between technical analysis and fundamental reality. Unlike standard bots that trade solely on price momentum, FinTrac integrates **Macroeconomic Indicators** (Yield Curves) and **Natural Language Processing** (SEC 10-K Sentiment) to vet trades before they happen.

---

## 🚀 Key Features

### 1. The "AI Veto" (Risk Management)
Standard momentum algorithms often buy into "bubbles" right before a crash. FinTrac employs a local **Small Language Model (FinBERT)** to read corporate 10-K filings.
* **Logic:** If Technicals = `BUY` but AI Sentiment = `NEGATIVE`, the trade is **Vetoed**.
* **Result:** In backtests, this prevented entry into failing tickers (e.g., Ford, FedEx) despite deceptive price rallies.

### 2. Personalized Risk Engine
Financial advice cannot be "one size fits all." FinTrac calculates a dynamic **Trade Score (0-100)** based on the user's real-time liquidity.
* **Aggressive Profile:** Prioritizes Momentum + Sentiment.
* **Conservative Profile:** Heavily penalizes trades during "Credit Stress" events (e.g., widening High-Yield Bond spreads).

### 3. Macro-Proxy Architecture
Instead of relying on expensive external feeds, FinTrac engineers economic indicators from market relationships:
* **Labor Confidence:** Derived from the ratio of *Consumer Discretionary (XLY)* vs. *Staples (XLP)*.
* **Credit Stress:** Derived from High-Yield Bond ETF volatility.

---

## 🛠️ Tech Stack

* **Core:** Python 3.10, Pandas, NumPy
* **Machine Learning:** PyTorch, HuggingFace Transformers (FinBERT)
* **Data Store:** SQLite, YFinance
* **Visualization:** Matplotlib, Seaborn
* **Deployment:** Docker (Containerized Jupyter Environment)

---

## 📂 Project Structure

```text
FinTrac_V1/
├── data/                   # SQLite database & raw CSVs
├── model/                  # Local FinBERT weights (Git-ignored)
├── notebooks/              # Interactive Analysis & Backtesting
│   └── FinTrac_Analysis.ipynb 
├── src/                    # Modular source code
│   ├── init_data.py          # Generates User Data

│   └── sentiment.py        # NLP Pipeline
├── Dockerfile              # Container configuration
├── requirements.txt        # Python dependencies
└── README.md               # Documentation


## Getting Started
