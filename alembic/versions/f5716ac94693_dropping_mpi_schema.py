"""dropping mpi schema

Revision ID: f5716ac94693
Revises: 0c90faa0378f
Create Date: 2024-09-25 15:47:22.497271

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = 'f5716ac94693'
down_revision: Union[str, None] = '0c90faa0378f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('idx_blocking_value_patient_key_value', table_name='mpi_blocking_value')
    op.drop_table('mpi_blocking_value')
    op.drop_table('mpi_patient')
    op.drop_table('mpi_person')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('mpi_person',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('internal_id', sa.CHAR(length=32), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('mpi_patient',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('person_id', sa.INTEGER(), nullable=False),
    sa.Column('data', sqlite.JSON(), nullable=False),
    sa.Column('external_person_id', sa.VARCHAR(length=255), nullable=True),
    sa.Column('external_person_source', sa.VARCHAR(length=100), nullable=True),
    sa.ForeignKeyConstraint(['person_id'], ['mpi_person.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('mpi_blocking_value',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('patient_id', sa.INTEGER(), nullable=False),
    sa.Column('blockingkey', sa.INTEGER(), nullable=False),
    sa.Column('value', sa.VARCHAR(length=50), nullable=False),
    sa.ForeignKeyConstraint(['patient_id'], ['mpi_patient.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_blocking_value_patient_key_value', 'mpi_blocking_value', ['patient_id', 'blockingkey', 'value'], unique=False)
    # ### end Alembic commands ###
