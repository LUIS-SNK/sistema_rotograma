"""Validade, exclusao logica, localizacao e controle concorrente. Migração aditiva."""
from alembic import op
import sqlalchemy as sa
revision = "20261028_01"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    meta = sa.MetaData()
    sa.Table('cercas', meta,
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('nome', sa.String(length=120), primary_key=False, nullable=False),
        sa.Column('cidade', sa.String(length=100), primary_key=False, nullable=True),
        sa.Column('estado', sa.String(length=2), primary_key=False, nullable=True),
        sa.Column('tipo', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('velocidade', sa.Numeric(precision=7, scale=2), primary_key=False, nullable=True),
        sa.Column('descricao', sa.Text(), primary_key=False, nullable=True),
        sa.Column('ativo', sa.Boolean(), primary_key=False, nullable=False),
        sa.Column('criado_em', sa.DateTime(), primary_key=False, nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), primary_key=False, nullable=False),
        sa.Column('excluido_em', sa.DateTime(), primary_key=False, nullable=True),
        sa.Column('motivo_inativacao', sa.String(length=30), primary_key=False, nullable=True),
        sa.Column('versao', sa.Integer(), primary_key=False, nullable=False, server_default='1'),
    )
    sa.Table('controle_rotinas', meta,
        sa.Column('nome', sa.String(length=60), primary_key=True, nullable=False),
        sa.Column('ultima_execucao', sa.DateTime(), primary_key=False, nullable=True),
        sa.Column('bloqueado_ate', sa.DateTime(), primary_key=False, nullable=True),
        sa.Column('token', sa.String(length=64), primary_key=False, nullable=True),
    )
    sa.Table('historico_alteracoes', meta,
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('tipo_item', sa.String(length=30), primary_key=False, nullable=False),
        sa.Column('item_id', sa.Integer(), primary_key=False, nullable=True),
        sa.Column('item_nome', sa.String(length=180), primary_key=False, nullable=False),
        sa.Column('campo', sa.String(length=80), primary_key=False, nullable=False),
        sa.Column('valor_anterior', sa.Text(), primary_key=False, nullable=True),
        sa.Column('valor_novo', sa.Text(), primary_key=False, nullable=True),
        sa.Column('tipo_operacao', sa.String(length=30), primary_key=False, nullable=False),
        sa.Column('data_alteracao', sa.DateTime(), primary_key=False, nullable=False),
    )
    sa.Table('postos', meta,
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('nome', sa.String(length=120), primary_key=False, nullable=False),
        sa.Column('tipo', sa.String(length=80), primary_key=False, nullable=True),
        sa.Column('endereco', sa.String(length=255), primary_key=False, nullable=True),
        sa.Column('cidade', sa.String(length=100), primary_key=False, nullable=True),
        sa.Column('estado', sa.String(length=2), primary_key=False, nullable=True),
        sa.Column('descricao', sa.Text(), primary_key=False, nullable=True),
        sa.Column('ativo', sa.Boolean(), primary_key=False, nullable=False),
        sa.Column('criado_em', sa.DateTime(), primary_key=False, nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), primary_key=False, nullable=False),
        sa.Column('excluido_em', sa.DateTime(), primary_key=False, nullable=True),
        sa.Column('motivo_inativacao', sa.String(length=30), primary_key=False, nullable=True),
        sa.Column('versao', sa.Integer(), primary_key=False, nullable=False, server_default='1'),
        sa.Column('data_referencia', sa.Date(), primary_key=False, nullable=True),
        sa.Column('data_vencimento', sa.Date(), primary_key=False, nullable=True),
    )
    sa.Table('rotogramas', meta,
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('nome', sa.String(length=150), primary_key=False, nullable=False),
        sa.Column('origem', sa.String(length=180), primary_key=False, nullable=True),
        sa.Column('destino', sa.String(length=180), primary_key=False, nullable=True),
        sa.Column('descricao', sa.Text(), primary_key=False, nullable=True),
        sa.Column('ativo', sa.Boolean(), primary_key=False, nullable=False),
        sa.Column('criado_em', sa.DateTime(), primary_key=False, nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), primary_key=False, nullable=False),
        sa.Column('excluido_em', sa.DateTime(), primary_key=False, nullable=True),
        sa.Column('motivo_inativacao', sa.String(length=30), primary_key=False, nullable=True),
        sa.Column('versao', sa.Integer(), primary_key=False, nullable=False, server_default='1'),
        sa.Column('data_referencia', sa.Date(), primary_key=False, nullable=True),
        sa.Column('data_vencimento', sa.Date(), primary_key=False, nullable=True),
    )
    sa.Table('pendencias', meta,
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('rotograma_id', sa.Integer(), sa.ForeignKey('rotogramas.id'), primary_key=False, nullable=False),
        sa.Column('historico_id', sa.Integer(), sa.ForeignKey('historico_alteracoes.id'), primary_key=False, nullable=False),
        sa.Column('tipo', sa.String(length=40), primary_key=False, nullable=False),
        sa.Column('descricao', sa.String(length=255), primary_key=False, nullable=False),
        sa.Column('status', sa.String(length=20), primary_key=False, nullable=False),
        sa.Column('criada_em', sa.DateTime(), primary_key=False, nullable=False),
        sa.Column('concluida_em', sa.DateTime(), primary_key=False, nullable=True),
    )
    sa.Table('rotograma_cercas', meta,
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('rotograma_id', sa.Integer(), sa.ForeignKey('rotogramas.id'), primary_key=False, nullable=False),
        sa.Column('cerca_id', sa.Integer(), sa.ForeignKey('cercas.id'), primary_key=False, nullable=False),
        sa.Column('vinculado_em', sa.DateTime(), primary_key=False, nullable=False),
        sa.UniqueConstraint('rotograma_id','cerca_id', name='uq_rotograma_cerca'),
    )
    sa.Table('rotograma_postos', meta,
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('rotograma_id', sa.Integer(), sa.ForeignKey('rotogramas.id'), primary_key=False, nullable=False),
        sa.Column('posto_id', sa.Integer(), sa.ForeignKey('postos.id'), primary_key=False, nullable=False),
        sa.Column('vinculado_em', sa.DateTime(), primary_key=False, nullable=False),
        sa.UniqueConstraint('rotograma_id','posto_id', name='uq_rotograma_posto'),
    )
    for table in meta.sorted_tables:
        if not sa.inspect(bind).has_table(table.name):
            table.create(bind)
        else:
            existentes = {c["name"] for c in sa.inspect(bind).get_columns(table.name)}
            for column in table.columns:
                if column.name not in existentes:
                    op.add_column(table.name, sa.Column(column.name, column.type, nullable=column.nullable, server_default=column.server_default))
    for nome in ("postos", "rotogramas"):
        indices = {indice["name"] for indice in sa.inspect(bind).get_indexes(nome)}
        indice = "ix_" + nome + "_data_vencimento"
        if indice not in indices:
            op.create_index(indice, nome, ["data_vencimento"])
    for nome in ("cercas", "postos", "rotogramas"):
        bind.execute(sa.text("UPDATE " + nome + " SET motivo_inativacao = :motivo WHERE ativo = :ativo AND motivo_inativacao IS NULL"), {"motivo": "manual", "ativo": False})

def downgrade():
    raise RuntimeError("Restaure um backup validado; esta revisão preserva dados e não oferece downgrade destrutivo.")
