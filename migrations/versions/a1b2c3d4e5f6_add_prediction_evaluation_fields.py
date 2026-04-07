"""add_prediction_evaluation_fields

Revision ID: a1b2c3d4e5f6
Revises: cd627a44fdd6
Create Date: 2026-04-05 17:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'cd627a44fdd6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add evaluation tracking fields to prediction_record
    op.add_column('prediction_record', 
        sa.Column('evaluation_status', sa.String(20), nullable=False, server_default='PENDING'))
    op.add_column('prediction_record',
        sa.Column('evaluation_due_at', sa.DateTime(), nullable=True))
    
    # Add index for efficient evaluation queries
    op.create_index('ix_prediction_evaluation_due', 'prediction_record', ['evaluation_due_at'], unique=False)


def downgrade() -> None:
    # Remove index
    op.drop_index('ix_prediction_evaluation_due', table_name='prediction_record')
    
    # Remove columns
    op.drop_column('prediction_record', 'evaluation_due_at')
    op.drop_column('prediction_record', 'evaluation_status')
