# FinTrac V2.0: Enterprise Financial Data Lake & AI Advisor

**FinTrac** is a localized, multi-modal algorithmic trading and financial risk platform. It acts as an autonomous backend engine that merges macroeconomic data, technical momentum, and Natural Language Processing (NLP) to provide personalized, risk-adjusted trade analyses.

Version 2.0 represents a complete architectural overhaul, transitioning from a static research environment into a robust, REST-driven local backend powered by a dual-database architecture and an integrated RAG (Retrieval-Augmented Generation) pipeline.

---

##  Technology Stack & Architecture

FinTrac prioritizes privacy, cost-efficiency, and local execution.

* **Core Backend:** Python 3.11
* **OLTP Database (State & Identity):** MariaDB (via SQLAlchemy). 
  * *Why:* Provides rigid ACID compliance, foreign key enforcement, and concurrency control for user transaction ledgers.
* **OLAP Engine (Time-Series Math):** DuckDB reading local `.parquet` files.
  * *Why:* Columnar processing allows for lightning-fast vectorized operations (e.g., 200-day moving averages) without locking the transactional user database.
* **Vector Store:** ChromaDB (Local).
  * *Why:* Persists embeddings locally, eliminating the need for paid cloud vector databases while maintaining strict data privacy.
* **AI & NLP Layer:** * **LangChain:** Orchestrates the multi-agent reasoning flow.
  * **Ollama (Local LLM):** Powers the Advisor Agent and `nomic-embed-text` embeddings, keeping sensitive financial queries completely offline.
  * **FinBERT (Local HuggingFace):** Dedicated sequence classification for SEC 10-K sentiment analysis.

---

##  Project Structure Overview

```text
FinTrac_V2/
├── data/                       # Local data lake (Parquet, ChromaDB, SQLite/MariaDB)
├── docs/                       # Architecture diagrams and deep-dive writeups
├── migrations/                 # Alembic database migration scripts
├── model/                      # Local FinBERT weights
├── scripts/                    # Utility scripts for backfilling and reconciliation
├── src/                        
│   ├── api/                    # REST API routes and Pydantic schemas
│   ├── db/                     # SQLAlchemy models and connection sessions
│   ├── ingestion/              # Data fetchers (YFinance, SEC EDGAR, FRED)
│   ├── agent/                  # LangChain RAG pipeline and Ollama tools
│   ├── ml/                     # FinBERT sentiment and intent parsing
│   └── engine/                 # Core risk calculus and orchestration
└── docker-compose.yml          # Container orchestration
