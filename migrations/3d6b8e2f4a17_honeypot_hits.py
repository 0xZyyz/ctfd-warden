import sqlalchemy as sa

revision = "3d6b8e2f4a17"
down_revision = "7b3e9c1f5a20"
branch_labels = None
depends_on = None


def upgrade(op=None):
    op.create_table(
        "warden_honeypot_hits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("challenge_id", sa.Integer(), nullable=True),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("flag", sa.String(length=255), nullable=False),
        sa.Column("ip", sa.String(length=46), nullable=True),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["challenge_id"], ["challenges.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade(op=None):
    op.drop_table("warden_honeypot_hits")
