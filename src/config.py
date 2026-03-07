import os
from pathlib import Path

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    OLLAMA_MODEL: str = "mistral"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"

    class Config:
        env_file = ".env"

settings = Settings()

# Base Directory Resolution
# Assumes this file is in FinTrac_V1_0/src/
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

class Config:
    """Central configuration object for the FinTrac backend."""
    
    # Database Paths
    USER_DB_PATH = DATA_DIR / "users.sqlite"
    MARKET_DB_PATH = DATA_DIR / "market_data.duckdb"
    
    # API Keys (Loaded from environment variables, fallback to None)
    FRED_API_KEY = os.getenv("FRED_API_KEY")
    SEC_API_KEY = os.getenv("SEC_API_KEY")
    
    # Application Constants
    DEFAULT_RISK_PROFILE = "Medium"
    MARKET_BENCHMARK_TICKER = "SPY"
    
    @staticmethod
    def check_api_keys():
        """Utility to warn if running in production without keys."""
        missing = []
        if not Config.FRED_API_KEY: missing.append("FRED_API_KEY")
        if not Config.SEC_API_KEY: missing.append("SEC_API_KEY")
        if missing:
            print(f"Warning: Missing API keys for {', '.join(missing)}. Some ingestion features may fail.")