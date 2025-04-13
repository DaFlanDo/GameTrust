"""Update Message model and add indexes

Revision ID: 985e876ccd66
Revises: c75dbfc915b2
Create Date: 2025-04-12 17:10:52.675583

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '985e876ccd66'
down_revision = 'c75dbfc915b2'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('message', schema=None) as batch_op:
        batch_op.create_index('idx_message_created', ['created_at'], unique=False)
        batch_op.create_index('idx_message_users', ['sender_id', 'receiver_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('message', schema=None) as batch_op:
        batch_op.drop_index('idx_message_users')
        batch_op.drop_index('idx_message_created')

    # ### end Alembic commands ###
