"""policy chunk metadata: 12 approved fields

Revision ID: 8fff7931553c
Revises: 71b988470cbd
Create Date: 2026-09-14 23:26:43.078302

REVIEWED & REWRITTEN by hand (2026-09-14):
autogenerate misread chunk_no->chunk_id as drop+add, which on a table with 18
live rows would fail (NOT NULL without value) and discard the LAW/HB ids.
Fixed with a real rename that PRESERVES values. policy_documents.authority was
added NOT NULL on a populated table the same way — fixed via nullable add,
in-migration backfill of the two known corpus rows, then SET NOT NULL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8fff7931553c'
down_revision: Union[str, Sequence[str], None] = '71b988470cbd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JTKSM_URL = ("https://jtksm.mohr.gov.my/sites/default/files/2023-11/"
             "Akta%20Kerja%201955%20%28Akta%20265%29.pdf")


def upgrade() -> None:
    """Upgrade schema."""
    # ── policy_chunks: RENAME chunk_no -> chunk_id (value-preserving) ──
    op.drop_constraint('policy_chunks_chunk_no_key', 'policy_chunks', type_='unique')
    op.alter_column('policy_chunks', 'chunk_no', new_column_name='chunk_id')
    op.create_unique_constraint('policy_chunks_chunk_id_key', 'policy_chunks', ['chunk_id'])

    # ── policy_chunks: the 9 new metadata columns (loader backfills values) ──
    op.add_column('policy_chunks', sa.Column('source_type', sa.Text(), nullable=True))
    op.add_column('policy_chunks', sa.Column('subtopic', sa.Text(), nullable=True))
    op.add_column('policy_chunks', sa.Column('section', sa.Text(), nullable=True))
    op.add_column('policy_chunks', sa.Column('jurisdiction', postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column('policy_chunks', sa.Column('effective_from', sa.Date(), nullable=True))
    op.add_column('policy_chunks', sa.Column('effective_to', sa.Date(), nullable=True))
    op.add_column('policy_chunks', sa.Column('version', sa.Text(), nullable=True))
    op.add_column('policy_chunks', sa.Column('authority', sa.Text(), nullable=True))
    op.add_column('policy_chunks', sa.Column('source_url', sa.Text(), nullable=True))

    # topic becomes nullable per model (copy-tolerant; loader always fills)
    op.alter_column('policy_chunks', 'topic',
                    existing_type=sa.TEXT(), nullable=True)

    # ── policy_documents: authority NOT NULL via add -> backfill -> enforce ──
    op.add_column('policy_documents', sa.Column('authority', sa.Text(), nullable=True))
    op.add_column('policy_documents', sa.Column('effective_to', sa.Date(), nullable=True))
    op.add_column('policy_documents', sa.Column('source_url', sa.Text(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE policy_documents SET "
            "  authority = CASE WHEN source_type = 'law' "
            "                   THEN 'JTKSM (Malaysia)' "
            "                   ELSE 'WorkRight Labs Sdn. Bhd.' END, "
            "  source_url = CASE WHEN source_type = 'law' "
            "                      THEN :url ELSE NULL END "
            "WHERE authority IS NULL"
        ).bindparams(url=JTKSM_URL)
    )
    op.alter_column('policy_documents', 'authority',
                    existing_type=sa.TEXT(), nullable=False)


def downgrade() -> None:
    """Downgrade schema (clean mirror of upgrade)."""
    op.alter_column('policy_documents', 'authority',
                    existing_type=sa.TEXT(), nullable=True)
    op.drop_column('policy_documents', 'source_url')
    op.drop_column('policy_documents', 'effective_to')
    op.drop_column('policy_documents', 'authority')

    op.alter_column('policy_chunks', 'topic',
                    existing_type=sa.TEXT(), nullable=False)
    for col in ('source_url', 'authority', 'version', 'effective_to',
                'effective_from', 'jurisdiction', 'section', 'subtopic',
                'source_type'):
        op.drop_column('policy_chunks', col)

    op.drop_constraint('policy_chunks_chunk_id_key', 'policy_chunks', type_='unique')
    op.alter_column('policy_chunks', 'chunk_id', new_column_name='chunk_no')
    op.create_unique_constraint('policy_chunks_chunk_no_key', 'policy_chunks', ['chunk_no'])
