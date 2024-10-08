"""moving ExternalPerson to Patient table

Revision ID: bfbd015ca466
Revises: ad18f1d41fad
Create Date: 2024-09-18 20:10:30.193941

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bfbd015ca466'
down_revision: Union[str, None] = 'ad18f1d41fad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('mpi_external_person')
    op.create_index(op.f('ix_mpi_blocking_value_value'), 'mpi_blocking_value', ['value'], unique=False)
    op.add_column('mpi_patient', sa.Column('external_person_id', sa.String(length=255), nullable=False))
    op.add_column('mpi_patient', sa.Column('external_person_source', sa.String(length=100), nullable=False))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('mpi_patient', 'external_person_source')
    op.drop_column('mpi_patient', 'external_person_id')
    op.drop_index(op.f('ix_mpi_blocking_value_value'), table_name='mpi_blocking_value')
    op.create_table('mpi_external_person',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('person_id', sa.INTEGER(), nullable=False),
    sa.Column('external_id', sa.VARCHAR(length=255), nullable=False),
    sa.Column('source', sa.VARCHAR(length=255), nullable=False),
    sa.ForeignKeyConstraint(['person_id'], ['mpi_person.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###
