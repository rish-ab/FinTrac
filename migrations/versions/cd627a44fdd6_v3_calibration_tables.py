"""v3_calibration_tables

Revision ID: cd627a44fdd6
Revises: f464729f7673
Create Date: 2026-03-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'cd627a44fdd6'
down_revision: Union[str, None] = 'f464729f7673'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PREDICTION_RECORD - stores every AI prediction with full context
    op.create_table('prediction_record',
    sa.Column('id', mysql.CHAR(length=36), nullable=False),
    sa.Column('ticker', sa.String(length=20), nullable=False),
    sa.Column('prediction_timestamp', sa.DateTime(), nullable=False),
    sa.Column('prediction_horizon', sa.String(length=20), nullable=False),
    sa.Column('predicted_direction', sa.String(length=10), nullable=False),
    sa.Column('predicted_return_pct', sa.Float(), nullable=True),
    sa.Column('confidence_score', sa.Float(), nullable=False),
    sa.Column('analysis_context', sa.JSON(), nullable=False),
    sa.Column('prompt_version', sa.String(length=50), nullable=False),
    sa.Column('model_version', sa.String(length=50), nullable=False),
    sa.Column('sector', sa.String(length=100), nullable=True),
    sa.Column('asset_class', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prediction_record_prediction_timestamp'), 'prediction_record', ['prediction_timestamp'], unique=False)
    op.create_index(op.f('ix_prediction_record_sector'), 'prediction_record', ['sector'], unique=False)
    op.create_index(op.f('ix_prediction_record_asset_class'), 'prediction_record', ['asset_class'], unique=False)
    op.create_index('ix_prediction_ticker_timestamp', 'prediction_record', ['ticker', 'prediction_timestamp'], unique=False)
    op.create_index('ix_prediction_sector_timestamp', 'prediction_record', ['sector', 'prediction_timestamp'], unique=False)
    
    # PREDICTION_OUTCOME - evaluation results comparing prediction vs reality
    op.create_table('prediction_outcome',
    sa.Column('id', mysql.CHAR(length=36), nullable=False),
    sa.Column('prediction_id', mysql.CHAR(length=36), nullable=False),
    sa.Column('evaluation_timestamp', sa.DateTime(), nullable=False),
    sa.Column('actual_price_start', sa.Float(), nullable=False),
    sa.Column('actual_price_end', sa.Float(), nullable=False),
    sa.Column('actual_return_pct', sa.Float(), nullable=False),
    sa.Column('prediction_accuracy_score', sa.Float(), nullable=True),
    sa.Column('is_direction_correct', sa.Boolean(), nullable=False),
    sa.Column('absolute_error', sa.Float(), nullable=False),
    sa.Column('evaluation_status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['prediction_id'], ['prediction_record.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('prediction_id')
    )
    op.create_index(op.f('ix_prediction_outcome_evaluation_timestamp'), 'prediction_outcome', ['evaluation_timestamp'], unique=False)
    op.create_index(op.f('ix_prediction_outcome_evaluation_status'), 'prediction_outcome', ['evaluation_status'], unique=False)
    
    # MARKET_EVENT - news and events that might impact predictions
    op.create_table('market_event',
    sa.Column('id', mysql.CHAR(length=36), nullable=False),
    sa.Column('event_timestamp', sa.DateTime(), nullable=False),
    sa.Column('event_type', sa.String(length=50), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=200), nullable=True),
    sa.Column('affected_sectors', sa.JSON(), nullable=True),
    sa.Column('affected_tickers', sa.JSON(), nullable=True),
    sa.Column('sentiment_score', sa.Float(), nullable=True),
    sa.Column('embedding_vector', mysql.BLOB(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_market_event_event_timestamp'), 'market_event', ['event_timestamp'], unique=False)
    op.create_index(op.f('ix_market_event_event_type'), 'market_event', ['event_type'], unique=False)
    
    # PREDICTION_ATTRIBUTION - links market events to prediction performance
    op.create_table('prediction_attribution',
    sa.Column('id', mysql.CHAR(length=36), nullable=False),
    sa.Column('prediction_id', mysql.CHAR(length=36), nullable=False),
    sa.Column('outcome_id', mysql.CHAR(length=36), nullable=False),
    sa.Column('event_id', mysql.CHAR(length=36), nullable=False),
    sa.Column('attribution_score', sa.Float(), nullable=False),
    sa.Column('explanation', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['market_event.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['outcome_id'], ['prediction_outcome.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['prediction_id'], ['prediction_record.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prediction_attribution_prediction_id'), 'prediction_attribution', ['prediction_id'], unique=False)
    op.create_index(op.f('ix_prediction_attribution_outcome_id'), 'prediction_attribution', ['outcome_id'], unique=False)
    op.create_index(op.f('ix_prediction_attribution_event_id'), 'prediction_attribution', ['event_id'], unique=False)
    
    # CALIBRATION_PROFILE - tracks systematic biases by sector/asset class
    op.create_table('calibration_profile',
    sa.Column('id', mysql.CHAR(length=36), nullable=False),
    sa.Column('sector', sa.String(length=100), nullable=True),
    sa.Column('asset_class', sa.String(length=50), nullable=True),
    sa.Column('bias_type', sa.String(length=100), nullable=False),
    sa.Column('detected_at', sa.DateTime(), nullable=False),
    sa.Column('sample_size', sa.Integer(), nullable=False),
    sa.Column('bias_magnitude', sa.Float(), nullable=False),
    sa.Column('correction_factor', sa.Float(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('confidence_interval', sa.JSON(), nullable=True),
    sa.Column('last_updated', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_calibration_profile_sector'), 'calibration_profile', ['sector'], unique=False)
    op.create_index(op.f('ix_calibration_profile_asset_class'), 'calibration_profile', ['asset_class'], unique=False)
    op.create_index('ix_calibration_sector_active', 'calibration_profile', ['sector', 'active'], unique=False)
    op.create_index('ix_calibration_class_active', 'calibration_profile', ['asset_class', 'active'], unique=False)
    
    # MODEL_IMPROVEMENT_LOG - tracks prompt evolution and model changes
    op.create_table('model_improvement_log',
    sa.Column('id', mysql.CHAR(length=36), nullable=False),
    sa.Column('improvement_type', sa.String(length=50), nullable=False),
    sa.Column('detected_issue', sa.Text(), nullable=False),
    sa.Column('old_config', sa.JSON(), nullable=True),
    sa.Column('new_config', sa.JSON(), nullable=False),
    sa.Column('expected_improvement', sa.Text(), nullable=True),
    sa.Column('validation_metrics', sa.JSON(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('activated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_model_improvement_log_created_at'), 'model_improvement_log', ['created_at'], unique=False)
    op.create_index('ix_improvement_type_status', 'model_improvement_log', ['improvement_type', 'status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_improvement_type_status', table_name='model_improvement_log')
    op.drop_index(op.f('ix_model_improvement_log_created_at'), table_name='model_improvement_log')
    op.drop_table('model_improvement_log')
    op.drop_index('ix_calibration_class_active', table_name='calibration_profile')
    op.drop_index('ix_calibration_sector_active', table_name='calibration_profile')
    op.drop_index(op.f('ix_calibration_profile_asset_class'), table_name='calibration_profile')
    op.drop_index(op.f('ix_calibration_profile_sector'), table_name='calibration_profile')
    op.drop_table('calibration_profile')
    op.drop_index(op.f('ix_prediction_attribution_event_id'), table_name='prediction_attribution')
    op.drop_index(op.f('ix_prediction_attribution_outcome_id'), table_name='prediction_attribution')
    op.drop_index(op.f('ix_prediction_attribution_prediction_id'), table_name='prediction_attribution')
    op.drop_table('prediction_attribution')
    op.drop_index(op.f('ix_market_event_event_type'), table_name='market_event')
    op.drop_index(op.f('ix_market_event_event_timestamp'), table_name='market_event')
    op.drop_table('market_event')
    op.drop_index(op.f('ix_prediction_outcome_evaluation_status'), table_name='prediction_outcome')
    op.drop_index(op.f('ix_prediction_outcome_evaluation_timestamp'), table_name='prediction_outcome')
    op.drop_table('prediction_outcome')
    op.drop_index('ix_prediction_sector_timestamp', table_name='prediction_record')
    op.drop_index('ix_prediction_ticker_timestamp', table_name='prediction_record')
    op.drop_index(op.f('ix_prediction_record_asset_class'), table_name='prediction_record')
    op.drop_index(op.f('ix_prediction_record_sector'), table_name='prediction_record')
    op.drop_index(op.f('ix_prediction_record_prediction_timestamp'), table_name='prediction_record')
    op.drop_table('prediction_record')
