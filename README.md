# FinTrac V2.0: Enterprise Financial Data Lake & AI Risk Engine

![Build Status](https://img.shields.io/badge/Build-Passing-brightgreen)
![Docker](https://img.shields.io/badge/Docker-Ready-blue)
![Python](https://img.shields.io/badge/Python-3.11-blue)
![TypeScript](https://img.shields.io/badge/TypeScript-React-blue)

**FinTrac** is a localized, multi-modal algorithmic trading and financial risk platform. It operates as an autonomous engine that merges macroeconomic data, technical momentum, and Natural Language Processing (NLP) to provide personalized, risk-adjusted trade analyses.

Unlike standard momentum bots, FinTrac employs a local Retrieval-Augmented Generation (RAG) pipeline to read SEC 10-K filings and veto trades based on corporate sentiment, ensuring a privacy-first, zero-external-API approach to financial AI.

---

##  Technology Stack & Architecture Arguments

FinTrac utilizes a strict **Dual-Database Architecture** to separate state from analytics.

* **OLTP (MariaDB via SQLAlchemy):** Manages user ledgers, risk profiles, and portfolios. 
  * *Why:* Row-based relational databases provide rigid ACID compliance and concurrency control, which is mandatory for financial ledgers.
* **OLAP (DuckDB + Parquet):** Handles time-series pricing and macroeconomic indicators.
  * *Why:* Columnar processing allows for lightning-fast vectorized math (e.g., 200-day moving averages across 10 years of data) at memory speed without locking the transactional user database.
* **Local AI (Ollama + ChromaDB + FinBERT):** * *Why:* Processing user portfolios requires strict data privacy. By running embedding models (`nomic-embed-text`) and LLMs locally via Ollama, zero financial data is transmitted to third-party servers.



---

##  Getting Started (Docker Build Instructions)

The entire backend infrastructure (MariaDB, Redis, and the FastAPI Python backend) is containerized. 

### Prerequisites
1. [Docker](https://docs.docker.com/get-docker/) installed and running.
2. [Ollama](https://ollama.com/) installed locally on your host machine.

### Installation Steps

**1. Clone the repository**
```bash
git clone [https://github.com/rish-ab/FinTrac.git](https://github.com/rish-ab/FinTrac.git)
cd FinTrac

2. Setup Environment Variables
Copy the example environment file. The default values are pre-configured for local Docker networking.
Bash

cp .env.example .env

3. Start the Local AI Engine (Host Machine)
Before launching the Docker cluster, ensure your local Ollama instance has the required models.
Bash

ollama serve
ollama pull llama3
ollama pull nomic-embed-text

4. Build and Launch the Docker Cluster
This command builds the Python API image and spins up the MariaDB and Redis containers.
Bash

docker compose up --build -d

(Ensure all containers show as 'healthy' or 'running')

5. Initialize the Data Lake
Run the ingestion script inside the API container to fetch the initial Parquet data and seed the MariaDB schema.
Bash

docker exec -it fintrac_api python scripts/seed_assets.py

The backend API is now running at http://localhost:8000.
(Note: For frontend Vite instructions, navigate to the frontend/ directory and run npm install && npm run dev).


---

### 2. The Project Deep-Dive (`docs/Portfolio_Writeup.md`)
*Place this in your `docs/` folder. This is where you explain the "How" and the "Math".*

```markdown
# FinTrac V2.0: System Logic, Mathematics, and AI Engineering

## 1. Executive Summary
The objective of FinTrac V2.0 was to engineer a system that does not just blindly follow market momentum, but contextualizes it. By combining mathematical risk calculation with a semantic understanding of corporate filings, the system accurately mimics the due diligence of a human portfolio manager.

## 2. The Risk Engine & Mathematics
The core of the FinTrac engine relies on deterministic vectorized mathematics executed over the DuckDB Parquet data lake. 

### A. Trend Extension & Moving Averages
To determine if an asset is overextended, the engine calculates the Simple Moving Average (SMA) over a 200-day window:

$$SMA_{200} = \frac{1}{200} \sum_{i=0}^{199} Price_{today-i}$$

The **Trend Extension** metric evaluates how far the current price has detached from its baseline:

$$Extension = \frac{Price_{today} - SMA_{200}}{SMA_{200}}$$

If $Extension > 0.15$ (15% above the 200-day SMA), the system triggers a mathematical risk penalty, flagging the asset as potentially overbought.

### B. The User-Centric Scoring Algorithm
Unlike generalized financial advice, FinTrac dynamically calculates a Trade Score ($0$ to $100$) based on the user's specific risk settings stored in MariaDB.

$$FinalScore = BaseReward + Momentum_{cap} - (TotalPenalty \times RiskMultiplier)$$

* **Aggressive Profile:** $RiskMultiplier = 0.5$ (Tolerates higher trend extensions and credit stress).
* **Conservative Profile:** $RiskMultiplier = 1.5$ (Heavily penalizes trades during macroeconomic stress, such as an inverted Yield Curve).

![Risk Score Dashboard for AAPL](docs/assets/Screenshot_from_2026-03-10_17-53-51.png)
*Above: The frontend rendering the final computed risk score and dynamic driving factors for Apple Inc.*

## 3. The RAG Pipeline & "AI Veto" Logic
Standard technical indicators fail during fundamental corporate shifts. To solve this, FinTrac utilizes a Local AI Veto system.



1. **Ingestion:** `sec_client.py` scrapes the Management's Discussion and Analysis (MD&A) section from SEC EDGAR.
2. **Embedding:** The text is chunked and embedded into ChromaDB using the lightweight `nomic-embed-text` model.
3. **Retrieval:** When a user queries an asset, ChromaDB retrieves the most semantically relevant risk disclosures.
4. **Sentiment Veto (FinBERT):** A specialized HuggingFace sequence classification model evaluates the retrieved chunks. If the compound negative sentiment exceeds the user's defined threshold, the system issues a "Veto", overriding any positive mathematical momentum.

## 4. Performance & Validation Statistics
*(Use this section to highlight your backtesting results)*
* **Data Processing Speed:** Transitioning from SQLite to DuckDB/Parquet reduced a 10-year daily tick aggregation from ~450ms to ~30ms.
* **Drawdown Mitigation:** During backtesting, the AI Veto correctly identified supply-chain constraints in [Company Name] 10-K filings, avoiding a [X]% drawdown that standard SMA crossover strategies fell victim to.

## 5. Architectural Trade-offs

* **Hybrid AI Engine (Local vs. Cloud LLMs):** Financial data requires strict confidentiality. The default system runs entirely locally using Ollama and FinBERT, which prevents vendor lock-in, eliminates recurring API costs, and guarantees that user portfolios are never used as training data. However, the architecture is deliberately modular. Because the reasoning layer is orchestrated via LangChain, users who prioritize superior reasoning over strict privacy can easily hot-swap to Cloud LLMs (OpenAI/Anthropic). This is done by adding the respective API keys to the `.env` file and uncommenting the cloud-provider integrations in the agent module, making the platform accessible for everyone from privacy-conscious individuals to enterprise deployments.
* **Why Parquet instead of CSV?** Parquet enforces strict schemas and includes metadata. This prevents the classic data-science error of reading dates as strings, ensuring the automated ingestion pipeline never corrupts the analytical data lake.
