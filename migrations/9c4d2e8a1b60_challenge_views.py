import sqlalchemy as sa

revision = "9c4d2e8a1b60"
down_revision = "7b3e9c1f5a20"
branch_labels = None
depends_on = None


def upgrade(op=None):
    op.create_table(
        "warden_challenge_views",
        sa.Column("account", sa.String(length=16), nullable=False),
        sa.Column("challenge_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["challenge_id"], ["challenges.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("account", "challenge_id"),
    )


def downgrade(op=None):
    op.drop_table("warden_challenge_views")
