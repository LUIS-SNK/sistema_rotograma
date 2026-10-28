"""Integração ORS, análises humanas e acesso individual. Aditiva."""
from alembic import op
import sqlalchemy as sa
revision="20261028_02"
down_revision="20261028_01"
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind()
    meta=sa.MetaData()
    sa.Table('cercas',meta,sa.Column("id",sa.Integer(),primary_key=True))
    sa.Table('postos',meta,sa.Column("id",sa.Integer(),primary_key=True))
    sa.Table('rotogramas',meta,sa.Column("id",sa.Integer(),primary_key=True))
    sa.Table('historico_alteracoes',meta,sa.Column("id",sa.Integer(),primary_key=True))
    sa.Table('rotograma_cercas',meta,sa.Column("id",sa.Integer(),primary_key=True))
    sa.Table('rotograma_postos',meta,sa.Column("id",sa.Integer(),primary_key=True))
    sa.Table('pendencias',meta,sa.Column("id",sa.Integer(),primary_key=True))
    sa.Table('controle_rotinas',meta,sa.Column("id",sa.Integer(),primary_key=True))
    sa.Table('cotas_ors',meta,
        sa.Column('endpoint',sa.String(length=30),primary_key=True,nullable=False),
        sa.Column('inicio',sa.DateTime(),primary_key=False,nullable=False),
        sa.Column('usadas',sa.Integer(),primary_key=False,nullable=False),
        sa.Column('proxima',sa.DateTime(),primary_key=False,nullable=False),
        sa.Column('restante_api',sa.Integer(),primary_key=False,nullable=True),
        sa.Column('reset_api',sa.DateTime(),primary_key=False,nullable=True),
    )
    sa.Table('falhas_login',meta,
        sa.Column('chave',sa.String(length=64),primary_key=True,nullable=False),
        sa.Column('tentativas',sa.Integer(),primary_key=False,nullable=False),
        sa.Column('inicio',sa.DateTime(),primary_key=False,nullable=False),
        sa.Column('bloqueado_ate',sa.DateTime(),primary_key=False,nullable=True),
    )
    sa.Table('trajetos_cache',meta,
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('chave',sa.String(length=64),primary_key=False,nullable=False),
        sa.Column('geometria',sa.JSON(),primary_key=False,nullable=False),
        sa.Column('assinatura',sa.String(length=64),primary_key=False,nullable=False),
        sa.Column('origem',sa.JSON(),primary_key=False,nullable=False),
        sa.Column('destino',sa.JSON(),primary_key=False,nullable=False),
        sa.Column('perfil',sa.String(length=40),primary_key=False,nullable=False),
        sa.Column('credito',sa.String(length=250),primary_key=False,nullable=False),
        sa.Column('calculado_em',sa.DateTime(),primary_key=False,nullable=False),
        sa.Column('valido_ate',sa.DateTime(),primary_key=False,nullable=False),
    )
    sa.Table('usuarios',meta,
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('login',sa.String(length=80),primary_key=False,nullable=False),
        sa.Column('nome',sa.String(length=120),primary_key=False,nullable=False),
        sa.Column('senha_hash',sa.String(length=255),primary_key=False,nullable=False),
        sa.Column('ativo',sa.Boolean(),primary_key=False,nullable=False),
        sa.Column('admin',sa.Boolean(),primary_key=False,nullable=False),
        sa.Column('criado_em',sa.DateTime(),primary_key=False,nullable=False),
        sa.Column('versao',sa.Integer(),primary_key=False,nullable=False,server_default='1'),
        sa.UniqueConstraint('login',name=None),
    )
    sa.Table('geocodificacoes',meta,
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('chave',sa.String(length=64),primary_key=False,nullable=False),
        sa.Column('consulta',sa.String(length=250),primary_key=False,nullable=False),
        sa.Column('uf',sa.String(length=2),primary_key=False,nullable=True),
        sa.Column('candidatos',sa.JSON(),primary_key=False,nullable=False),
        sa.Column('coordenadas',sa.JSON(),primary_key=False,nullable=True),
        sa.Column('status',sa.String(length=30),primary_key=False,nullable=False),
        sa.Column('fonte',sa.String(length=40),primary_key=False,nullable=False),
        sa.Column('usuario_id',sa.Integer(),sa.ForeignKey('usuarios.id'),primary_key=False,nullable=True),
        sa.Column('criado_em',sa.DateTime(),primary_key=False,nullable=False),
        sa.Column('versao',sa.Integer(),primary_key=False,nullable=False,server_default='1'),
        sa.UniqueConstraint('chave',name=None),
    )
    sa.Table('tarefas_geograficas',meta,
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('chave',sa.String(length=64),primary_key=False,nullable=False),
        sa.Column('cerca_id',sa.Integer(),sa.ForeignKey('cercas.id'),primary_key=False,nullable=False),
        sa.Column('rotograma_id',sa.Integer(),sa.ForeignKey('rotogramas.id'),primary_key=False,nullable=False),
        sa.Column('assinatura',sa.String(length=64),primary_key=False,nullable=False),
        sa.Column('status',sa.String(length=35),primary_key=False,nullable=False),
        sa.Column('tentativas',sa.Integer(),primary_key=False,nullable=False),
        sa.Column('mensagem',sa.String(length=500),primary_key=False,nullable=True),
        sa.Column('proxima_tentativa',sa.DateTime(),primary_key=False,nullable=True),
        sa.Column('localizacao_id',sa.Integer(),sa.ForeignKey('geocodificacoes.id'),primary_key=False,nullable=True),
        sa.Column('trajeto_id',sa.Integer(),sa.ForeignKey('trajetos_cache.id'),primary_key=False,nullable=True),
        sa.Column('criado_em',sa.DateTime(),primary_key=False,nullable=False),
        sa.Column('atualizado_em',sa.DateTime(),primary_key=False,nullable=False),
        sa.Column('versao',sa.Integer(),primary_key=False,nullable=False,server_default='1'),
        sa.UniqueConstraint('chave',name=None),
    )
    sa.Table('analises_cercas',meta,
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('cerca_id',sa.Integer(),sa.ForeignKey('cercas.id'),primary_key=False,nullable=False),
        sa.Column('rotograma_id',sa.Integer(),sa.ForeignKey('rotogramas.id'),primary_key=False,nullable=False),
        sa.Column('tarefa_id',sa.Integer(),sa.ForeignKey('tarefas_geograficas.id'),primary_key=False,nullable=False),
        sa.Column('trajeto_id',sa.Integer(),sa.ForeignKey('trajetos_cache.id'),primary_key=False,nullable=False),
        sa.Column('contexto',sa.String(length=64),primary_key=False,nullable=False),
        sa.Column('distancia_m',sa.Float(),primary_key=False,nullable=False),
        sa.Column('raio_m',sa.Float(),primary_key=False,nullable=False),
        sa.Column('precisao',sa.String(length=50),primary_key=False,nullable=False),
        sa.Column('status',sa.String(length=30),primary_key=False,nullable=False),
        sa.Column('usuario_id',sa.Integer(),sa.ForeignKey('usuarios.id'),primary_key=False,nullable=True),
        sa.Column('decidida_em',sa.DateTime(),primary_key=False,nullable=True),
        sa.Column('justificativa',sa.String(length=500),primary_key=False,nullable=True),
        sa.Column('criado_em',sa.DateTime(),primary_key=False,nullable=False),
        sa.Column('versao',sa.Integer(),primary_key=False,nullable=False,server_default='1'),
        sa.UniqueConstraint('cerca_id','rotograma_id',name='uq_analise_cerca_rotograma'),
    )
    for nome in ['cotas_ors', 'falhas_login', 'trajetos_cache', 'usuarios', 'geocodificacoes', 'tarefas_geograficas', 'analises_cercas']:
        meta.tables[nome].create(bind,checkfirst=True)
    if 'latitude' not in {c["name"] for c in sa.inspect(bind).get_columns('cercas')}:
        op.add_column('cercas',sa.Column('latitude',sa.Float(),nullable=True))
    if 'longitude' not in {c["name"] for c in sa.inspect(bind).get_columns('cercas')}:
        op.add_column('cercas',sa.Column('longitude',sa.Float(),nullable=True))
    if 'geo_habilitada' not in {c["name"] for c in sa.inspect(bind).get_columns('cercas')}:
        op.add_column('cercas',sa.Column('geo_habilitada',sa.Boolean(),nullable=False,server_default='0'))
    if 'origem_uf' not in {c["name"] for c in sa.inspect(bind).get_columns('rotogramas')}:
        op.add_column('rotogramas',sa.Column('origem_uf',sa.String(length=2),nullable=True))
    if 'destino_uf' not in {c["name"] for c in sa.inspect(bind).get_columns('rotogramas')}:
        op.add_column('rotogramas',sa.Column('destino_uf',sa.String(length=2),nullable=True))
    if 'origem_latitude' not in {c["name"] for c in sa.inspect(bind).get_columns('rotogramas')}:
        op.add_column('rotogramas',sa.Column('origem_latitude',sa.Float(),nullable=True))
    if 'origem_longitude' not in {c["name"] for c in sa.inspect(bind).get_columns('rotogramas')}:
        op.add_column('rotogramas',sa.Column('origem_longitude',sa.Float(),nullable=True))
    if 'destino_latitude' not in {c["name"] for c in sa.inspect(bind).get_columns('rotogramas')}:
        op.add_column('rotogramas',sa.Column('destino_latitude',sa.Float(),nullable=True))
    if 'destino_longitude' not in {c["name"] for c in sa.inspect(bind).get_columns('rotogramas')}:
        op.add_column('rotogramas',sa.Column('destino_longitude',sa.Float(),nullable=True))
    if 'usuario_id' not in {c["name"] for c in sa.inspect(bind).get_columns('historico_alteracoes')}:
        op.add_column('historico_alteracoes',sa.Column('usuario_id',sa.Integer(),nullable=True))
    if 'origem_operacao' not in {c["name"] for c in sa.inspect(bind).get_columns('historico_alteracoes')}:
        op.add_column('historico_alteracoes',sa.Column('origem_operacao',sa.String(length=20),nullable=True))

def downgrade():
    raise RuntimeError("Use um backup validado para restauração; a exclusão destrutiva de análises e autoria não é permitida.")
