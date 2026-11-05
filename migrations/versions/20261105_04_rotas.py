"""Percurso aprovado, cache da API e controle de consultas."""
from alembic import op
import sqlalchemy as sa
revision='20261105_04'
down_revision='20261029_03'
branch_labels=None
depends_on=None

def upgrade():
    existentes={c['name'] for c in sa.inspect(op.get_bind()).get_columns('rotogramas')}
    if 'rota_por_estradas' not in existentes:
        op.add_column('rotogramas',sa.Column('rota_por_estradas',sa.Boolean(),nullable=False,server_default='0'))
    if 'rota_dados' not in existentes:
        op.add_column('rotogramas',sa.Column('rota_dados',sa.JSON(),nullable=True))
    op.create_table('roteirizacao_cache',sa.Column('chave',sa.String(64),primary_key=True),sa.Column('dados',sa.JSON(),nullable=False),sa.Column('criado_em',sa.DateTime(),nullable=False))
    op.create_table('roteirizacao_uso',sa.Column('periodo',sa.String(30),primary_key=True),sa.Column('quantidade',sa.Integer(),nullable=False))

def downgrade():
    raise RuntimeError('Planeje a reversão para preservar os percursos aprovados.')
