"""Добавлены balance и hold_balance для User

Revision ID: c75dbfc915b2
Revises: f8f582b92c78
Create Date: 2025-04-12 09:22:55.252223

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c75dbfc915b2'
down_revision = 'f8f582b92c78'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('lot', schema=None) as batch_op:
        batch_op.drop_column('balance')
        batch_op.drop_column('hold_balance')

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('balance', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('hold_balance', sa.Integer(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('hold_balance')
        batch_op.drop_column('balance')

    with op.batch_alter_table('lot', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hold_balance', sa.INTEGER(), nullable=True))
        batch_op.add_column(sa.Column('balance', sa.INTEGER(), nullable=True))

    # ### end Alembic commands ###
