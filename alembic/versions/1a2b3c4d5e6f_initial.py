"""initial

Revision ID: 1a2b3c4d5e6f
Revises: 
Create Date: 2026-06-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '1a2b3c4d5e6f'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    # 2. Create assets table
    op.create_table(
        'assets',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default="active"),
        sa.Column('first_seen', sa.DateTime(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('tags', postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column('metadata', postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('type', 'value', name='uq_asset_type_value')
    )
    op.create_index(op.f('ix_assets_type'), 'assets', ['type'], unique=False)
    op.create_index(op.f('ix_assets_value'), 'assets', ['value'], unique=False)

    # 3. Create asset_relationships table
    op.create_table(
        'asset_relationships',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('target_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['source_id'], ['assets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_id'], ['assets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_id', 'target_id', 'type', name='uq_relationship_source_target_type')
    )


def downgrade() -> None:
    op.drop_table('asset_relationships')
    op.drop_index(op.f('ix_assets_value'), table_name='assets')
    op.drop_index(op.f('ix_assets_type'), table_name='assets')
    op.drop_table('assets')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
