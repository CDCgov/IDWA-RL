"""external person id should be nullable

Revision ID: 64ed9566f189
Revises: bfbd015ca466
Create Date: 2024-09-18 20:22:07.510203

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '64ed9566f189'
down_revision: Union[str, None] = 'bfbd015ca466'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('ix_mpi_blocking_value_value', table_name='mpi_blocking_value')
    op.drop_column('mpi_patient', 'external_person_source')
    op.drop_column('mpi_patient', 'external_person_id')
    op.add_column('mpi_patient', sa.Column('external_person_id', sa.String(length=255), nullable=True))
    op.add_column('mpi_patient', sa.Column('external_person_source', sa.String(length=100), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('mpi_patient', 'external_person_source')
    op.drop_column('mpi_patient', 'external_person_id')
    op.add_column('mpi_patient', sa.Column('external_person_id', sa.String(length=255), nullable=False))
    op.add_column('mpi_patient', sa.Column('external_person_source', sa.String(length=100), nullable=False))
    op.create_index('ix_mpi_blocking_value_value', 'mpi_blocking_value', ['value'], unique=False)
    # ### end Alembic commands ###
