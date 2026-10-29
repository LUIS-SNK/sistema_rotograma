"""Coordenadas opcionais e faixa direta com pontas arredondadas."""
from alembic import op
import sqlalchemy as sa

revision = '20261029_03'
down_revision = '20261029_02'
branch_labels = None
depends_on = None


def upgrade():
    alteracoes = {
        'cercas': [('latitude', sa.Float()), ('longitude', sa.Float())],
        'rotogramas': [('origem_uf', sa.String(2)), ('destino_uf', sa.String(2)),
            ('origem_latitude', sa.Float()), ('origem_longitude', sa.Float()),
            ('destino_latitude', sa.Float()), ('destino_longitude', sa.Float()),
            ('faixa_raio_km', sa.Float())]}
    inspetor = sa.inspect(op.get_bind())
    for tabela, campos in alteracoes.items():
        existentes = {c['name'] for c in inspetor.get_columns(tabela)}
        for nome, tipo in campos:
            if nome not in existentes:
                op.add_column(tabela, sa.Column(nome, tipo, nullable=True))
    if 'faixa_ativa' not in {c['name'] for c in inspetor.get_columns('rotogramas')}:
        op.add_column('rotogramas', sa.Column('faixa_ativa', sa.Boolean(), nullable=False, server_default='0'))


def downgrade():
    raise RuntimeError('Planeje a reversão para preservar coordenadas e histórico.')
