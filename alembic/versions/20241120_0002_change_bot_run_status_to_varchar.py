"""Change bot_run.status from enum to VARCHAR.

Revision ID: 20241120_0002
Revises: 20241112_0001
Create Date: 2024-11-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

# revision identifiers, used by Alembic.
revision = "20241120_0002"
down_revision = "20241112_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Change bot_run.status from enum to VARCHAR."""
    # Step 1: Remove the default value that depends on the enum
    op.execute(sa.text("ALTER TABLE bot_run ALTER COLUMN status DROP DEFAULT"))
    
    # Step 2: Convert existing enum values to strings
    op.execute(sa.text("""
        ALTER TABLE bot_run 
        ALTER COLUMN status TYPE VARCHAR(32) 
        USING status::text
    """))
    
    # Step 3: Set new default as VARCHAR string
    op.execute(sa.text("ALTER TABLE bot_run ALTER COLUMN status SET DEFAULT 'running'"))
    
    # Step 4: Drop the enum type (no longer has dependencies)
    op.execute(sa.text("DROP TYPE IF EXISTS bot_run_status"))


def downgrade() -> None:
    """Revert bot_run.status back to enum."""
    # Step 1: Remove VARCHAR default
    op.execute(sa.text("ALTER TABLE bot_run ALTER COLUMN status DROP DEFAULT"))
    
    # Step 2: Recreate the enum type
    bot_run_status_enum = sa.Enum(
        "running",
        "stopped",
        "failed",
        name="bot_run_status",
    )
    bot_run_status_enum.create(op.get_bind(), checkfirst=True)
    
    # Step 3: Convert column back to enum
    op.execute(sa.text("""
        ALTER TABLE bot_run 
        ALTER COLUMN status TYPE bot_run_status 
        USING status::bot_run_status
    """))
    
    # Step 4: Set enum default
    op.execute(sa.text("ALTER TABLE bot_run ALTER COLUMN status SET DEFAULT 'running'::bot_run_status"))

