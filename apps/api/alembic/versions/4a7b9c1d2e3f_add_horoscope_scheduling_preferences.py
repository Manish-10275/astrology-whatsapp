"""Add horoscope scheduling preferences to user_preferences.

Revision ID: 4a7b9c1d2e3f
Revises: 2c5e3354b756
Create Date: 2026-10-24 13:40:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '4a7b9c1d2e3f'
down_revision: Union[str, None] = '2c5e3354b756'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'user_preferences',
        sa.Column('daily_horoscope_opt_in', sa.Boolean(), nullable=False, server_default=sa.text('false'))
    )
    op.add_column(
        'user_preferences',
        sa.Column('horoscope_delivery_time', sa.String(length=5), nullable=False, server_default=sa.text("'07:00'"))
    )
    op.add_column(
        'user_preferences',
        sa.Column('last_horoscope_sent_date', sa.Date(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('user_preferences', 'last_horoscope_sent_date')
    op.drop_column('user_preferences', 'horoscope_delivery_time')
    op.drop_column('user_preferences', 'daily_horoscope_opt_in')
