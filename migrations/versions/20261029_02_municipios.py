"""Sugestões municipais dentro das pendências. Migração aditiva."""
from alembic import op
import sqlalchemy as sa

revision = '20261029_02'
down_revision = '20261028_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('fila_municipal',
        sa.Column('cerca_id', sa.Integer(), sa.ForeignKey('cercas.id'), primary_key=True),
        sa.Column('status', sa.String(40), nullable=False),
        sa.Column('mensagem', sa.String(500)),
        sa.Column('processada_em', sa.DateTime()),
        sa.Column('base_versao', sa.String(64)))
    op.create_table('sugestoes_municipais',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cerca_id', sa.Integer(), sa.ForeignKey('cercas.id'), nullable=False),
        sa.Column('rotograma_id', sa.Integer(), sa.ForeignKey('rotogramas.id'), nullable=False),
        sa.Column('pendencia_id', sa.Integer(), sa.ForeignKey('pendencias.id'), nullable=False, unique=True),
        sa.Column('municipio_origem', sa.String(150), nullable=False),
        sa.Column('motivo', sa.JSON(), nullable=False),
        sa.Column('decisao', sa.String(25)),
        sa.Column('responsavel', sa.String(120)),
        sa.Column('justificativa', sa.String(500)),
        sa.Column('decidida_em', sa.DateTime()),
        sa.Column('versao', sa.Integer(), nullable=False, server_default='1'),
        sa.UniqueConstraint('cerca_id', 'rotograma_id', name='uq_sugestao_municipal_par'))


def downgrade():
    raise RuntimeError('Reversão deve ser planejada para preservar as decisões e o histórico.')
