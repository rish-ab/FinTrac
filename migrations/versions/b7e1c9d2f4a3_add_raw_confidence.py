"""add_raw_confidence

Stores the model's confidence BEFORE calibration correction so the
calibration engine no longer learns from its own adjusted output.
Also makes prediction_outcome.absolute_error nullable — it is
undefined when no predicted_return_pct was recorded.

Revision ID: b7e1c9d2f4a3
Revises: a1b2c3d4e5f6
Create Date: 2026-10-23 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b7e1c9d2f4a3'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('prediction_record',
        sa.Column('raw_confidence', sa.Float(), nullable=True))

    op.alter_column('prediction_outcome', 'absolute_error',
        existing_type=sa.Float(), nullable=True)

    # 0.0 was written as a placeholder when no return was predicted
    op.execute(
        "UPDATE prediction_outcome po "
        "JOIN prediction_record pr ON pr.id = po.prediction_id "
        "SET po.absolute_error = NULL "
        "WHERE pr.predicted_return_pct IS NULL"
    )


def downgrade() -> None:
    op.execute("UPDATE prediction_outcome SET absolute_error = 0.0 WHERE absolute_error IS NULL")
    op.alter_column('prediction_outcome', 'absolute_error',
        existing_type=sa.Float(), nullable=False)
    op.drop_column('prediction_record', 'raw_confidence')
