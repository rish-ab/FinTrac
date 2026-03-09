# =============================================================
# migrations/env.py
#
# Alembic's runtime environment. This file is what Alembic
# executes when you run any alembic command.
#
# TWO MODES:
# 1. offline — generates SQL scripts without a live DB connection.
#    Used for reviewing migrations before applying them.
# 2. online  — connects to the real DB and runs migrations live.
#    This is what "alembic upgrade head" uses.
#
# AUTOGENERATE:
# When you run "alembic revision --autogenerate -m 'description'",
# Alembic compares target_metadata (your models) against the actual
# DB schema and generates a migration script for the differences.
# This is why importing all your models here is critical — if a
# model isn't imported, Alembic doesn't know it exists and won't
# generate migrations for it.
# =============================================================

import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Add project root to path so src.* imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── IMPORT ALL MODELS ──────────────────────────────────────────────────────────
# Every model must be imported here for autogenerate to detect it.
# Importing Base is not enough — the models must actually be loaded
# into memory so their table metadata is registered on Base.metadata.

from src.db.models import (  # noqa: F401 — imports needed for side effects
    Base,
    UserIdentity,
    RiskSettings,
    Portfolio,
    AssetClassLookup,
    AssetMaster,
    AssetSubtypeBond,
    AssetSubtypeForex,
    MacroIndicatorMaster,
    Watchlist,
    OrderGroup,
    TransactionLedger,
    PositionJournal,
    AIRecommendationLog,
    RecommendationFeedback,
    ComparisonSession,
    AlertQueue,
    IngestionLog,
    ParquetManifest,
    DocumentRegistry,
)

from src.config import settings

# Alembic config object (reads alembic.ini)
config = context.config

# Override the sqlalchemy.url from alembic.ini with the real value
# from config.py — single source of truth
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Wire up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This is the metadata Alembic diffs against the real DB
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Generate SQL without a live DB connection.
    Useful for reviewing or sharing migration scripts.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url                     = url,
        target_metadata         = target_metadata,
        literal_binds           = True,
        dialect_opts            = {"paramstyle": "named"},
        compare_type            = True,   # detect column type changes
        compare_server_default  = True,   # detect default value changes
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Connect to the real DB and run migrations.
    This is what 'alembic upgrade head' uses.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix          = "sqlalchemy.",
        poolclass       = pool.NullPool,  # no pooling for one-off migration runs
    )
    with connectable.connect() as connection:
        context.configure(
            connection              = connection,
            target_metadata         = target_metadata,
            compare_type            = True,
            compare_server_default  = True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()