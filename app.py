import os
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
import threading
import atexit
import sys
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, func, or_, inspect, text, update, and_, event
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.exc import IntegrityError, OperationalError
from validade import hoje, vencimento, ler_referencia, situacao_validade, UFS, VerificadorInterno
import faixa_geografica as faixa

TIPOS_POSTO = ("Refeição", "Refeição/Pernoite", "Abastecimento", "Abastecimento/Refeição/Pernoite", "Abastecimento/Refeição")

def agora_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-chave-alterar")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///rotogramas.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


def configurar_sqlite(connection, record):
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


with app.app_context():
    if db.engine.dialect.name == "sqlite":
        event.listen(db.engine, "connect", configurar_sqlite)


class Cerca(db.Model):
    __tablename__ = "cercas"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, index=True)
    cidade = db.Column(db.String(100), nullable=True)
    estado = db.Column(db.String(2), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    tipo = db.Column(db.String(80), nullable=False, default="")
    velocidade = db.Column(db.Numeric(7, 2), nullable=True)
    descricao = db.Column(db.Text, nullable=True)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=agora_utc)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=agora_utc, onupdate=agora_utc)

    excluido_em = db.Column(db.DateTime, nullable=True)
    motivo_inativacao = db.Column(db.String(30), nullable=True)
    versao = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    __mapper_args__ = {"version_id_col": versao}


class Posto(db.Model):
    __tablename__ = "postos"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, index=True)
    tipo = db.Column(db.String(80), nullable=True)
    endereco = db.Column(db.String(255), nullable=True)
    cidade = db.Column(db.String(100), nullable=True)
    estado = db.Column(db.String(2), nullable=True)
    descricao = db.Column(db.Text, nullable=True)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=agora_utc)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=agora_utc, onupdate=agora_utc)

    excluido_em = db.Column(db.DateTime, nullable=True)
    motivo_inativacao = db.Column(db.String(30), nullable=True)
    versao = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    __mapper_args__ = {"version_id_col": versao}
    data_referencia = db.Column(db.Date, nullable=True)
    data_vencimento = db.Column(db.Date, nullable=True, index=True)


class Rotograma(db.Model):
    __tablename__ = "rotogramas"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False, index=True)
    origem = db.Column(db.String(180), nullable=True)
    destino = db.Column(db.String(180), nullable=True)
    origem_uf = db.Column(db.String(2), nullable=True)
    destino_uf = db.Column(db.String(2), nullable=True)
    origem_latitude = db.Column(db.Float, nullable=True)
    origem_longitude = db.Column(db.Float, nullable=True)
    destino_latitude = db.Column(db.Float, nullable=True)
    destino_longitude = db.Column(db.Float, nullable=True)
    faixa_ativa = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    faixa_raio_km = db.Column(db.Float, nullable=True)
    descricao = db.Column(db.Text, nullable=True)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=agora_utc)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=agora_utc, onupdate=agora_utc)

    excluido_em = db.Column(db.DateTime, nullable=True)
    motivo_inativacao = db.Column(db.String(30), nullable=True)
    versao = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    __mapper_args__ = {"version_id_col": versao}
    data_referencia = db.Column(db.Date, nullable=True)
    data_vencimento = db.Column(db.Date, nullable=True, index=True)


class RotogramaCerca(db.Model):
    __tablename__ = "rotograma_cercas"
    id = db.Column(db.Integer, primary_key=True)
    rotograma_id = db.Column(db.Integer, db.ForeignKey("rotogramas.id"), nullable=False)
    cerca_id = db.Column(db.Integer, db.ForeignKey("cercas.id"), nullable=False)
    vinculado_em = db.Column(db.DateTime, nullable=False, default=agora_utc)
    rotograma = db.relationship("Rotograma", backref=db.backref("cercas_vinculadas", cascade="all, delete-orphan"))
    cerca = db.relationship("Cerca")
    __table_args__ = (UniqueConstraint("rotograma_id", "cerca_id", name="uq_rotograma_cerca"),)


class RotogramaPosto(db.Model):
    __tablename__ = "rotograma_postos"
    id = db.Column(db.Integer, primary_key=True)
    rotograma_id = db.Column(db.Integer, db.ForeignKey("rotogramas.id"), nullable=False)
    posto_id = db.Column(db.Integer, db.ForeignKey("postos.id"), nullable=False)
    vinculado_em = db.Column(db.DateTime, nullable=False, default=agora_utc)
    rotograma = db.relationship("Rotograma", backref=db.backref("postos_vinculados", cascade="all, delete-orphan"))
    posto = db.relationship("Posto")
    __table_args__ = (UniqueConstraint("rotograma_id", "posto_id", name="uq_rotograma_posto"),)


class HistoricoAlteracao(db.Model):
    __tablename__ = "historico_alteracoes"
    id = db.Column(db.Integer, primary_key=True)
    tipo_item = db.Column(db.String(30), nullable=False)  # cerca, posto, rotograma, vinculo_cerca, vinculo_posto
    item_id = db.Column(db.Integer, nullable=True)
    item_nome = db.Column(db.String(180), nullable=False)
    campo = db.Column(db.String(80), nullable=False)
    valor_anterior = db.Column(db.Text, nullable=True)
    valor_novo = db.Column(db.Text, nullable=True)
    tipo_operacao = db.Column(db.String(30), nullable=False, default="edicao")
    data_alteracao = db.Column(db.DateTime, nullable=False, default=agora_utc, index=True)


class Pendencia(db.Model):
    __tablename__ = "pendencias"
    id = db.Column(db.Integer, primary_key=True)
    rotograma_id = db.Column(db.Integer, db.ForeignKey("rotogramas.id"), nullable=False, index=True)
    historico_id = db.Column(db.Integer, db.ForeignKey("historico_alteracoes.id"), nullable=False, index=True)
    tipo = db.Column(db.String(40), nullable=False, default="alteracao_cadastral")
    descricao = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="aberta", index=True)
    criada_em = db.Column(db.DateTime, nullable=False, default=agora_utc)
    concluida_em = db.Column(db.DateTime, nullable=True)
    rotograma = db.relationship("Rotograma")
    historico = db.relationship("HistoricoAlteracao")



class ControleRotina(db.Model):
    __tablename__ = "controle_rotinas"
    nome = db.Column(db.String(60), primary_key=True)
    ultima_execucao = db.Column(db.DateTime, nullable=True)
    bloqueado_ate = db.Column(db.DateTime, nullable=True)
    token = db.Column(db.String(64), nullable=True)


def normalizar_nome(nome):
    nome = " ".join(nome.split()).casefold()
    return "".join(c for c in unicodedata.normalize("NFKD", nome) if not unicodedata.combining(c))


def ordenar_por_nome(itens):
    return sorted(itens, key=lambda item: (normalizar_nome(item.nome), item.id))


def filtrar_status(query, modelo):
    status = request.args.get("status", "")
    if status == "excluido":
        return query.filter(modelo.excluido_em.is_not(None))
    query = query.filter(modelo.excluido_em.is_(None))
    if status == "ativo":
        query = query.filter(modelo.ativo.is_(True))
        if modelo is Posto:
            query = query.filter(or_(Posto.data_vencimento.is_(None), Posto.data_vencimento > hoje()))
    elif status == "inativo":
        condicao = modelo.ativo.is_(False)
        if modelo is Posto:
            condicao = or_(condicao, Posto.data_vencimento <= hoje())
        query = query.filter(condicao)
    elif status in ("manual", "vencimento"):
        condicao = and_(modelo.motivo_inativacao == status, modelo.ativo.is_(False))
        if status == "vencimento" and modelo is Posto:
            condicao = or_(condicao, and_(Posto.ativo.is_(True), Posto.data_vencimento <= hoje()))
        query = query.filter(condicao)
    return query


def filtrar_validade(itens):
    filtro = request.args.get("validade", "")
    return [item for item in itens if not filtro or situacao_validade(item) == filtro]


def buscar_texto(itens, busca, campos):
    termos = normalizar_nome(busca).split()
    return [item for item in itens if all(
        termo in normalizar_nome(" ".join(str(getattr(item, campo) or "") for campo in campos))
        for termo in termos)]


def filtrar_rotograma(query, modelo, vinculo, chave):
    valor = request.args.get("rotograma", "")
    relacionamento = getattr(vinculo, chave)
    if valor == "sem_vinculo":
        return query.filter(~modelo.id.in_(db.session.query(relacionamento)))
    if valor:
        try:
            rotograma_id = int(valor)
        except ValueError:
            return query.filter(False)
        return query.filter(modelo.id.in_(db.session.query(relacionamento).filter(vinculo.rotograma_id == rotograma_id)))
    return query


@app.context_processor
def opcoes_cadastro():
    return {"tipos_posto": TIPOS_POSTO, "ufs_oficiais": UFS,
            "validade_item": situacao_validade, "situacao_item": situacao_item,
            "problemas_rotograma": problemas_rotograma, "hoje_local": hoje(),
            "data_br": lambda d: d.strftime("%d/%m/%Y") if d else "Não informada"}


@app.before_request
def validar_cadastros():
    if request.method != "POST":
        return
    rotas = {
        "nova_cerca": (Cerca, "cerca", "form_cerca.html"),
        "editar_cerca": (Cerca, "cerca", "form_cerca.html"),
        "novo_posto": (Posto, "posto", "form_posto.html"),
        "editar_posto": (Posto, "posto", "form_posto.html"),
        "novo_rotograma": (Rotograma, "rotograma", "form_rotograma.html"),
        "editar_rotograma": (Rotograma, "rotograma", "form_rotograma.html"),
    }
    if request.endpoint not in rotas:
        return
    modelo, tipo, template = rotas[request.endpoint]
    item_id = (request.view_args or {}).get("item_id")
    item = db.get_or_404(modelo, item_id) if item_id else None
    nome = request.form.get("nome", "")
    limite = modelo.__table__.c.nome.type.length
    erro = None
    status = 400
    if not nome.strip() or len(nome.strip()) > limite:
        erro = f"Informe um nome de até {limite} caracteres."
    else:
        chave = normalizar_nome(nome)
        existente = next((obj for obj in modelo.query.all()
                          if obj.id != item_id and normalizar_nome(obj.nome) == chave), None)
        if existente:
            estado = "ativo" if existente.ativo else "inativo"
            erro = f"Já existe um cadastro com esse nome: {existente.nome} (ID {existente.id}, {estado})."
            status = 409
    if not erro and tipo == "posto":
        tipo_enviado = request.form.get("tipo", "").strip()
        # Postos antigos podem continuar sem classificação até o usuário escolher um tipo.
        if tipo_enviado not in TIPOS_POSTO and not (item and not item.tipo and not tipo_enviado):
            erro = "Selecione um tipo de posto válido."
    if not erro and item:
        if item.excluido_em:
            abort(409, description="Este registro foi excluído e está disponível somente para consulta.")
        conferir_versao(item)
    if not erro and tipo in ("posto", "rotograma"):
        try:
            referencia = ler_referencia(request.form.get("data_referencia", ""), obrigatoria=item is None or bool(item.data_referencia))
            if tipo == "posto" and item and item.motivo_inativacao == "vencimento" and bool_form(request.form.get("ativo")) and (not referencia or vencimento(referencia) <= hoje()):
                raise ValueError("Regularize a validade antes de reativar o posto.")
        except ValueError as exc:
            erro = str(exc)
    if not erro and tipo == "cerca":
        cidade = request.form.get("cidade", "").strip()
        uf = request.form.get("estado", "").strip().upper()
        if ((item is None or bool(item.cidade) or bool(item.estado) or cidade or uf) and (not cidade or uf not in UFS)) or len(cidade) > 100:
            erro = "Informe a cidade (até 100 caracteres) e selecione uma UF oficial."
    if not erro and tipo in ('cerca', 'rotograma'):
        try:
            dados_geograficos(tipo, request.form)
        except (ValueError, TypeError) as exc:
            erro = str(exc)
    if erro:
        flash(erro, "erro")
        return render_template(template, **{tipo: item}), status


def atualizar_estrutura():
    """Aplica somente revisões controladas; não remove dados existentes."""
    from alembic import command
    from alembic.config import Config
    configuracao = Config()
    configuracao.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    with db.engine.connect() as connection:
        revisao = MigrationContext.configure(connection).get_current_revision()
        tem_tabelas = bool(inspect(connection).get_table_names())
    if revisao != ScriptDirectory.from_config(configuracao).get_current_head() and tem_tabelas and db.engine.dialect.name == "sqlite" and os.getenv('BACKUP_ANTES_MIGRACAO', '1') != '0':
        import sqlite3
        origem = Path(db.engine.url.database)
        if origem.is_file():
            pasta_backup = origem.parent / "backups"
            pasta_backup.mkdir(exist_ok=True)
            destino = pasta_backup / ("antes-migracao-" + agora_utc().strftime("%Y%m%d-%H%M%S-%f") + ".db")
            with sqlite3.connect(origem.as_uri() + "?mode=ro", uri=True) as fonte, sqlite3.connect(destino) as copia:
                fonte.backup(copia)
            app.logger.info("Backup anterior à migração: %s", destino)
    with db.engine.begin() as connection:
        configuracao.attributes["connection"] = connection
        command.upgrade(configuracao, "head")


@app.cli.command("atualizar-banco")
def atualizar_banco():
    atualizar_estrutura()
    print("Estrutura do banco atualizada.")


def texto(valor):
    if valor is None or valor == "":
        return "Não informado"
    return str(valor)


def registrar_historico(tipo_item, item_id, item_nome, campo, anterior, novo, operacao="edicao"):
    registro = HistoricoAlteracao(
        tipo_item=tipo_item,
        item_id=item_id,
        item_nome=item_nome,
        campo=campo,
        valor_anterior=texto(anterior),
        valor_novo=texto(novo),
        tipo_operacao=operacao,
    )
    db.session.add(registro)
    db.session.flush()
    return registro


def rotogramas_vinculados(tipo_item, item_id):
    if tipo_item == "cerca":
        return [v.rotograma for v in RotogramaCerca.query.filter_by(cerca_id=item_id).all()]
    if tipo_item == "posto":
        return [v.rotograma for v in RotogramaPosto.query.filter_by(posto_id=item_id).all()]
    return []


def criar_pendencias(registro, rotogramas, tipo="alteracao_cadastral"):
    # Uma pendência por alteração histórica e por rotograma afetado.
    vistos = set()
    for rotograma in rotogramas:
        if rotograma and rotograma.id not in vistos:
            db.session.add(Pendencia(
                rotograma_id=rotograma.id,
                historico_id=registro.id,
                tipo=tipo,
                descricao=f"{registro.item_nome}: {registro.campo.replace('_', ' ')} alterado",
            ))
            vistos.add(rotograma.id)


def salvar_alteracoes_cadastro(objeto, tipo_item, campos, dados, gerar_pendencias=True):
    campos = dict(campos)
    if tipo_item in ('cerca', 'rotograma'):
        geograficos = dados_geograficos(tipo_item, dados)
        for chave, valor in geograficos.items():
            campos[chave] = lambda v, convertido=valor: convertido
    if tipo_item in ("posto", "rotograma"):
        campos["data_referencia"] = lambda v: ler_referencia(v, obrigatoria=bool(objeto.data_referencia))
        campos["data_vencimento"] = lambda v: vencimento(ler_referencia(dados.get("data_referencia", "")))
    ativo_novo = bool_form(dados.get("ativo"))
    motivo = None if ativo_novo else (objeto.motivo_inativacao or "manual")
    if objeto.ativo and not ativo_novo:
        motivo = "manual"
    if tipo_item == "posto":
        fim = vencimento(ler_referencia(dados.get("data_referencia", "")))
        if ativo_novo and fim and fim <= hoje():
            campos["ativo"] = lambda v: False
            motivo = "vencimento"
    campos["motivo_inativacao"] = lambda v: motivo
    alteracoes = []
    for campo, conversor in campos.items():
        valor_anterior = getattr(objeto, campo)
        try:
            valor_novo = conversor(dados.get(campo, ""))
        except (ValueError, InvalidOperation):
            raise ValueError(f"Valor inválido para o campo {campo.replace('_', ' ')}.")
        if isinstance(valor_anterior, Decimal) and valor_novo is not None:
            mudou = valor_anterior != valor_novo
        else:
            mudou = valor_anterior != valor_novo
        if mudou:
            setattr(objeto, campo, valor_novo)
            alteracoes.append((campo, valor_anterior, valor_novo))
    if not alteracoes:
        return 0

    db.session.flush()
    for campo, anterior, novo in alteracoes:
        registro = registrar_historico(
            tipo_item, objeto.id, objeto.nome, campo, anterior, novo, "edicao"
        )
        if gerar_pendencias and tipo_item in ("cerca", "posto"):
            criar_pendencias(registro, rotogramas_vinculados(tipo_item, objeto.id))
    return len(alteracoes)


def bool_form(valor):
    return valor == "on"


def dados_geograficos(tipo, dados):
    resultado = {}
    if tipo == 'cerca':
        if 'latitude' in dados or 'longitude' in dados:
            resultado['latitude'], resultado['longitude'] = faixa.coordenadas_form(dados)
    else:
        for prefixo in ('origem_', 'destino_'):
            if prefixo+'latitude' in dados or prefixo+'longitude' in dados:
                resultado[prefixo+'latitude'], resultado[prefixo+'longitude'] = faixa.coordenadas_form(dados, prefixo)
            if prefixo+'uf' in dados:
                uf = dados.get(prefixo+'uf', '').strip().upper()
                if uf and uf not in UFS:
                    raise ValueError('Selecione uma UF oficial para origem e destino.')
                resultado[prefixo+'uf'] = uf or None
        if 'faixa_ativa' in dados or 'faixa_raio_km' in dados:
            resultado['faixa_ativa'] = bool_form(dados.get('faixa_ativa'))
            valor = dados.get('faixa_raio_km', '').strip()
            resultado['faixa_raio_km'] = faixa.raio(valor) if valor else None
    return resultado


@app.route("/")
def dashboard():
    return render_template(
        "dashboard.html",
        cercas=Cerca.query.filter_by(excluido_em=None).count(),
        postos=Posto.query.filter_by(excluido_em=None).count(),
        rotogramas=Rotograma.query.filter_by(excluido_em=None).count(),
        pendencias=Pendencia.query.filter(Pendencia.status == 'aberta', Pendencia.tipo != 'sugestao_municipal').count(),
        alertas=coletar_alertas(),
        rotina=db.session.get(ControleRotina, "vencimentos"),
        ultimas=HistoricoAlteracao.query.order_by(HistoricoAlteracao.data_alteracao.desc()).limit(8).all(),
    )


@app.route("/cercas")
def listar_cercas():
    busca = request.args.get("q", "").strip()
    query = filtrar_status(Cerca.query, Cerca)
    query = filtrar_rotograma(query, Cerca, RotogramaCerca, "cerca_id")
    tipo = request.args.get("tipo", "")
    if tipo:
        query = query.filter(Cerca.tipo == tipo)
    itens = buscar_texto(query.all(), busca, ("nome", "tipo", "descricao", "cidade", "estado"))
    cidade = normalizar_nome(request.args.get("cidade", ""))
    uf = request.args.get("uf", "").upper()
    itens = [c for c in itens if (not cidade or cidade in normalizar_nome(c.cidade or "")) and (not uf or c.estado == uf)]
    tipos = sorted({c.tipo for c in Cerca.query.all() if c.tipo}, key=normalizar_nome)
    return render_template("cercas.html", cercas=ordenar_por_nome(itens), busca=busca,
                           rotogramas_filtro=ordenar_por_nome(Rotograma.query.all()), tipos_cerca=tipos)


@app.route("/cercas/nova", methods=["GET", "POST"])
def nova_cerca():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("Informe o nome da cerca.", "erro")
            return render_template("form_cerca.html", cerca=None)
        velocidade_raw = request.form.get("velocidade", "").strip()
        try:
            velocidade = Decimal(velocidade_raw.replace(",", ".")) if velocidade_raw else None
            if velocidade is not None and velocidade < 0:
                raise InvalidOperation
        except InvalidOperation:
            flash("Informe uma velocidade válida.", "erro")
            return render_template("form_cerca.html", cerca=None)
        cerca = Cerca(nome=nome, cidade=request.form.get("cidade", "").strip(), estado=request.form.get("estado", "").strip().upper(), tipo=request.form.get("tipo", "").strip(),
                      velocidade=velocidade, descricao=request.form.get("descricao", "").strip(),
                      ativo=bool_form(request.form.get("ativo")), **dados_geograficos('cerca', request.form))
        cerca.motivo_inativacao = None if cerca.ativo else "manual"
        db.session.add(cerca)
        db.session.flush()
        for campo, valor in [("cidade", cerca.cidade), ("estado", cerca.estado), ("nome", nome), ("tipo", cerca.tipo), ("velocidade", velocidade),
                             ("descricao", cerca.descricao), ("ativo", cerca.ativo), ('latitude', cerca.latitude), ('longitude', cerca.longitude)]:
            registrar_historico("cerca", cerca.id, cerca.nome, campo, None, valor, "cadastro")
        db.session.commit()
        flash("Cerca cadastrada com sucesso.", "sucesso")
        return redirect(url_for("listar_cercas"))
    return render_template("form_cerca.html", cerca=None)


@app.route("/cercas/<int:item_id>/editar", methods=["GET", "POST"])
def editar_cerca(item_id):
    cerca = db.get_or_404(Cerca, item_id)
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("Informe o nome da cerca.", "erro")
            return render_template("form_cerca.html", cerca=cerca)
        try:
            campos = {
                "nome": lambda v: v.strip(),
                "cidade": lambda v: v.strip() or None,
                "estado": lambda v: v.strip().upper() or None,
                "tipo": lambda v: v.strip(),
                "velocidade": lambda v: Decimal(v.replace(",", ".")) if v.strip() else None,
                "descricao": lambda v: v.strip(),
                "ativo": lambda v: bool_form(v),
            }
            dados = request.form.to_dict()
            salvar_alteracoes_cadastro(cerca, "cerca", campos, dados)
            db.session.commit()
            flash("Cerca atualizada. As pendências aplicáveis foram geradas.", "sucesso")
            return redirect(url_for("listar_cercas"))
        except (ValueError, InvalidOperation) as exc:
            db.session.rollback()
            flash(str(exc) or "Velocidade inválida.", "erro")
    return render_template("form_cerca.html", cerca=cerca)


@app.route("/postos")
def listar_postos():
    busca = request.args.get("q", "").strip()
    query = filtrar_status(Posto.query, Posto)
    query = filtrar_rotograma(query, Posto, RotogramaPosto, "posto_id")
    tipo = request.args.get("tipo", "")
    if tipo == "sem_tipo":
        query = query.filter(or_(Posto.tipo.is_(None), Posto.tipo == ""))
    elif tipo:
        query = query.filter(Posto.tipo == tipo)
    uf = request.args.get("uf", "").strip().upper()
    if uf:
        query = query.filter(func.upper(Posto.estado) == uf)
    itens = buscar_texto(query.all(), busca, ("nome", "cidade", "endereco", "descricao"))
    cidade = normalizar_nome(request.args.get("cidade", ""))
    if cidade:
        itens = [p for p in itens if cidade in normalizar_nome(p.cidade or "")]
    ufs = sorted({p.estado.upper() for p in Posto.query.all() if p.estado})
    return render_template("postos.html", postos=ordenar_por_nome(filtrar_validade(itens)), busca=busca,
                           rotogramas_filtro=ordenar_por_nome(Rotograma.query.all()), ufs=ufs)


@app.route("/postos/novo", methods=["GET", "POST"])
def novo_posto():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("Informe o nome do posto.", "erro")
            return render_template("form_posto.html", posto=None)
        posto = Posto(nome=nome, tipo=request.form.get("tipo", "").strip(), endereco=request.form.get("endereco", "").strip(),
                      cidade=request.form.get("cidade", "").strip(),
                      estado=request.form.get("estado", "").strip().upper()[:2],
                      descricao=request.form.get("descricao", "").strip(),
                      ativo=bool_form(request.form.get("ativo")))
        preparar_novo(posto)
        db.session.add(posto)
        db.session.flush()
        for campo in ("nome", "tipo", "endereco", "cidade", "estado", "descricao", "ativo", "data_referencia", "data_vencimento", "motivo_inativacao"):
            registrar_historico("posto", posto.id, posto.nome, campo, None, getattr(posto, campo), "cadastro")
        db.session.commit()
        flash("Posto cadastrado com sucesso.", "sucesso")
        return redirect(url_for("listar_postos"))
    return render_template("form_posto.html", posto=None)


@app.route("/postos/<int:item_id>/editar", methods=["GET", "POST"])
def editar_posto(item_id):
    posto = db.get_or_404(Posto, item_id)
    if request.method == "POST":
        if not request.form.get("nome", "").strip():
            flash("Informe o nome do posto.", "erro")
            return render_template("form_posto.html", posto=posto)
        campos = {
            "nome": lambda v: v.strip(),
            "tipo": lambda v: v.strip() or None,
            "endereco": lambda v: v.strip(),
            "cidade": lambda v: v.strip(),
            "estado": lambda v: v.strip().upper()[:2],
            "descricao": lambda v: v.strip(),
            "ativo": lambda v: bool_form(v),
        }
        salvar_alteracoes_cadastro(posto, "posto", campos, request.form.to_dict())
        db.session.commit()
        flash("Posto atualizado. As pendências aplicáveis foram geradas.", "sucesso")
        return redirect(url_for("listar_postos"))
    return render_template("form_posto.html", posto=posto)


@app.route("/rotogramas")
def listar_rotogramas():
    busca = request.args.get("q", "").strip()
    query = filtrar_status(Rotograma.query, Rotograma)
    pendencias = request.args.get("pendencias", "")
    abertos = db.session.query(Pendencia.rotograma_id).filter(Pendencia.status == "aberta")
    if pendencias == "com":
        query = query.filter(Rotograma.id.in_(abertos))
    elif pendencias == "sem":
        query = query.filter(~Rotograma.id.in_(abertos))
    itens = buscar_texto(query.all(), busca, ("nome", "origem", "destino", "descricao"))
    composicao = request.args.get("composicao", "")
    if composicao in ("com", "sem"):
        itens = [r for r in itens if bool(problemas_rotograma(r)) == (composicao == "com")]
    return render_template("rotogramas.html", rotogramas=ordenar_por_nome(filtrar_validade(itens)), busca=busca)


@app.route("/rotogramas/novo", methods=["GET", "POST"])
def novo_rotograma():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("Informe o nome do rotograma.", "erro")
            return render_template("form_rotograma.html", rotograma=None)
        rotograma = Rotograma(nome=nome, origem=request.form.get("origem", "").strip(),
                              destino=request.form.get("destino", "").strip(),
                              descricao=request.form.get("descricao", "").strip(),
                              ativo=bool_form(request.form.get("ativo")), **dados_geograficos('rotograma', request.form))
        preparar_novo(rotograma)
        db.session.add(rotograma)
        db.session.flush()
        for campo in ("nome", "origem", "destino", "descricao", "ativo", "data_referencia", "data_vencimento", "motivo_inativacao"):
            registrar_historico("rotograma", rotograma.id, rotograma.nome, campo, None, getattr(rotograma, campo), "cadastro")
        for campo in dados_geograficos('rotograma', request.form):
            registrar_historico('rotograma', rotograma.id, rotograma.nome, campo, None, getattr(rotograma, campo), 'cadastro')
        db.session.commit()
        flash("Rotograma cadastrado com sucesso.", "sucesso")
        return redirect(url_for("detalhe_rotograma", item_id=rotograma.id))
    return render_template("form_rotograma.html", rotograma=None)


@app.route("/rotogramas/<int:item_id>")
def detalhe_rotograma(item_id):
    rotograma = db.get_or_404(Rotograma, item_id)
    cercas_vinculadas = RotogramaCerca.query.filter_by(rotograma_id=item_id).all()
    postos_vinculados = RotogramaPosto.query.filter_by(rotograma_id=item_id).all()
    cercas_vinculadas.sort(key=lambda v: (normalizar_nome(v.cerca.nome), v.cerca_id))
    postos_vinculados.sort(key=lambda v: (normalizar_nome(v.posto.nome), v.posto_id))
    cercas_ids = [v.cerca_id for v in cercas_vinculadas]
    postos_ids = [v.posto_id for v in postos_vinculados]
    cercas_disponiveis = Cerca.query.filter(Cerca.ativo.is_(True), Cerca.excluido_em.is_(None), ~Cerca.id.in_(cercas_ids)).order_by(Cerca.nome).all() if cercas_ids else Cerca.query.filter_by(ativo=True, excluido_em=None).order_by(Cerca.nome).all()
    postos_disponiveis = Posto.query.filter(Posto.ativo.is_(True), Posto.excluido_em.is_(None), or_(Posto.data_vencimento.is_(None), Posto.data_vencimento > hoje()), ~Posto.id.in_(postos_ids)).order_by(Posto.nome).all() if postos_ids else Posto.query.filter(Posto.ativo.is_(True), Posto.excluido_em.is_(None), or_(Posto.data_vencimento.is_(None), Posto.data_vencimento > hoje())).order_by(Posto.nome).all()
    cercas_disponiveis = ordenar_por_nome(cercas_disponiveis)
    postos_disponiveis = ordenar_por_nome(postos_disponiveis)
    pendencias = Pendencia.query.filter(Pendencia.rotograma_id == item_id, Pendencia.tipo != 'sugestao_municipal').order_by(Pendencia.criada_em.desc()).limit(10).all()
    return render_template("detalhe_rotograma.html", rotograma=rotograma,
                           cercas_vinculadas=cercas_vinculadas, postos_vinculados=postos_vinculados,
                           cercas_disponiveis=cercas_disponiveis, postos_disponiveis=postos_disponiveis,
                           pendencias=pendencias, faixa_info=sugestoes_municipais.dados_faixa(rotograma))


@app.route("/rotogramas/<int:item_id>/editar", methods=["GET", "POST"])
def editar_rotograma(item_id):
    rotograma = db.get_or_404(Rotograma, item_id)
    if request.method == "POST":
        if not request.form.get("nome", "").strip():
            flash("Informe o nome do rotograma.", "erro")
            return render_template("form_rotograma.html", rotograma=rotograma)
        campos = {
            "nome": lambda v: v.strip(),
            "origem": lambda v: v.strip(),
            "destino": lambda v: v.strip(),
            "descricao": lambda v: v.strip(),
            "ativo": lambda v: bool_form(v),
        }
        salvar_alteracoes_cadastro(rotograma, "rotograma", campos, request.form.to_dict(), gerar_pendencias=False)
        db.session.commit()
        flash("Rotograma atualizado.", "sucesso")
        return redirect(url_for("detalhe_rotograma", item_id=item_id))
    return render_template("form_rotograma.html", rotograma=rotograma)


@app.route("/rotogramas/<int:item_id>/vincular-cerca", methods=["POST"])
def vincular_cerca(item_id):
    rotograma = db.get_or_404(Rotograma, item_id)
    conferir_versao(rotograma)
    if rotograma.excluido_em:
        abort(409, description="Rotograma excluído: composição preservada para consulta.")
    rotograma.atualizado_em = agora_utc()
    cerca = db.get_or_404(Cerca, request.form.get("cerca_id", type=int))
    if cerca.excluido_em or not cerca.ativo:
        flash("Não é possível vincular uma cerca inativa.", "erro")
        return redirect(url_for("detalhe_rotograma", item_id=item_id))
    existente = RotogramaCerca.query.filter_by(rotograma_id=item_id, cerca_id=cerca.id).first()
    if existente:
        flash("Essa cerca já está vinculada ao rotograma.", "erro")
        return redirect(url_for("detalhe_rotograma", item_id=item_id))
    cerca.versao += 1
    db.session.add(RotogramaCerca(rotograma_id=item_id, cerca_id=cerca.id))
    db.session.flush()
    registro = registrar_historico("vinculo_cerca", cerca.id, cerca.nome, "vinculo_cerca",
                                   "não vinculado", f"vinculado ao rotograma #{rotograma.id} - {rotograma.nome}", "inclusao_vinculo")
    registro.item_nome = f"{cerca.nome} | Rotograma: {rotograma.nome}"
    db.session.add(Pendencia(rotograma_id=item_id, historico=registro, tipo="alteracao_vinculo",
                             descricao=f"Cerca '{cerca.nome}' adicionada à composição"))
    db.session.commit()
    flash("Cerca vinculada. Foi criada uma pendência de verificação.", "sucesso")
    return redirect(url_for("detalhe_rotograma", item_id=item_id))


@app.route("/rotogramas/<int:item_id>/desvincular-cerca/<int:cerca_id>", methods=["POST"])
def desvincular_cerca(item_id, cerca_id):
    rotograma = db.get_or_404(Rotograma, item_id)
    conferir_versao(rotograma)
    if rotograma.excluido_em:
        abort(409, description="Rotograma excluído: composição preservada para consulta.")
    rotograma.atualizado_em = agora_utc()
    vinculo = RotogramaCerca.query.filter_by(rotograma_id=item_id, cerca_id=cerca_id).first_or_404()
    nome = vinculo.cerca.nome
    registro = registrar_historico("vinculo_cerca", cerca_id, f"{nome} | Rotograma: {rotograma.nome}",
                                   "vinculo_cerca", f"vinculado ao rotograma #{rotograma.id}", "desvinculado",
                                   "remocao_vinculo")
    db.session.delete(vinculo)
    db.session.flush()
    db.session.add(Pendencia(rotograma_id=item_id, historico=registro, tipo="alteracao_vinculo",
                             descricao=f"Cerca '{nome}' removida da composição"))
    db.session.commit()
    flash("Vínculo removido e registrado no histórico.", "sucesso")
    return redirect(url_for("detalhe_rotograma", item_id=item_id))


@app.route("/rotogramas/<int:item_id>/vincular-posto", methods=["POST"])
def vincular_posto(item_id):
    rotograma = db.get_or_404(Rotograma, item_id)
    conferir_versao(rotograma)
    if rotograma.excluido_em:
        abort(409, description="Rotograma excluído: composição preservada para consulta.")
    rotograma.atualizado_em = agora_utc()
    posto = db.get_or_404(Posto, request.form.get("posto_id", type=int))
    if posto.excluido_em or not posto.ativo or situacao_validade(posto) == "vencido":
        flash("Não é possível vincular um posto inativo.", "erro")
        return redirect(url_for("detalhe_rotograma", item_id=item_id))
    if RotogramaPosto.query.filter_by(rotograma_id=item_id, posto_id=posto.id).first():
        flash("Esse posto já está vinculado ao rotograma.", "erro")
        return redirect(url_for("detalhe_rotograma", item_id=item_id))
    posto.versao += 1
    db.session.add(RotogramaPosto(rotograma_id=item_id, posto_id=posto.id))
    db.session.flush()
    registro = registrar_historico("vinculo_posto", posto.id, f"{posto.nome} | Rotograma: {rotograma.nome}",
                                   "vinculo_posto", "não vinculado",
                                   f"vinculado ao rotograma #{rotograma.id} - {rotograma.nome}", "inclusao_vinculo")
    db.session.add(Pendencia(rotograma_id=item_id, historico=registro, tipo="alteracao_vinculo",
                             descricao=f"Posto '{posto.nome}' adicionado à composição"))
    db.session.commit()
    flash("Posto vinculado. Foi criada uma pendência de verificação.", "sucesso")
    return redirect(url_for("detalhe_rotograma", item_id=item_id))


@app.route("/rotogramas/<int:item_id>/desvincular-posto/<int:posto_id>", methods=["POST"])
def desvincular_posto(item_id, posto_id):
    rotograma = db.get_or_404(Rotograma, item_id)
    conferir_versao(rotograma)
    if rotograma.excluido_em:
        abort(409, description="Rotograma excluído: composição preservada para consulta.")
    rotograma.atualizado_em = agora_utc()
    vinculo = RotogramaPosto.query.filter_by(rotograma_id=item_id, posto_id=posto_id).first_or_404()
    nome = vinculo.posto.nome
    registro = registrar_historico("vinculo_posto", posto_id, f"{nome} | Rotograma: {rotograma.nome}",
                                   "vinculo_posto", f"vinculado ao rotograma #{rotograma.id}", "desvinculado",
                                   "remocao_vinculo")
    db.session.delete(vinculo)
    db.session.flush()
    db.session.add(Pendencia(rotograma_id=item_id, historico=registro, tipo="alteracao_vinculo",
                             descricao=f"Posto '{nome}' removido da composição"))
    db.session.commit()
    flash("Vínculo removido e registrado no histórico.", "sucesso")
    return redirect(url_for("detalhe_rotograma", item_id=item_id))


@app.route("/pendencias")
def listar_pendencias():
    status = request.args.get("status", "aberta")
    if status not in ("aberta", "concluida", "todas"):
        status = "aberta"
    query = Pendencia.query.filter(Pendencia.tipo != 'sugestao_municipal')
    if status != "todas":
        query = query.filter_by(status=status)
    pendencias = query.order_by(Pendencia.criada_em.desc()).all()
    return render_template("pendencias.html", pendencias=pendencias, status= status)


@app.route("/pendencias/<int:item_id>/concluir", methods=["POST"])
def concluir_pendencia(item_id):
    pendencia = db.get_or_404(Pendencia, item_id)
    if pendencia.tipo == 'sugestao_municipal':
        abort(400, description='Use Vincular ou Dispensar na sugestão municipal, informando o responsável.')
    if pendencia.status == "aberta":
        pendencia.status = "concluida"
        pendencia.concluida_em = agora_utc()
        db.session.commit()
        flash("Verificação registrada. Pendência concluída.", "sucesso")
    else:
        flash("Essa pendência já foi concluída.", "info")
    return redirect(request.referrer or url_for("listar_pendencias"))


@app.route("/historico")
def listar_historico():
    tipo = request.args.get("tipo", "")
    busca = request.args.get("q", "").strip()
    query = HistoricoAlteracao.query
    if tipo:
        query = query.filter_by(tipo_item=tipo)
    if busca:
        query = query.filter(or_(HistoricoAlteracao.item_nome.ilike(f"%{busca}%"),
                                 HistoricoAlteracao.campo.ilike(f"%{busca}%"),
                                 HistoricoAlteracao.valor_novo.ilike(f"%{busca}%")))
    historicos = query.order_by(HistoricoAlteracao.data_alteracao.desc()).limit(300).all()
    return render_template("historico.html", historicos=historicos, tipo=tipo, busca=busca)


@app.errorhandler(500)
def erro_interno(error):
    db.session.rollback()
    return render_template("erro.html"), 500



def conferir_versao(item):
    versao = request.form.get("versao", type=int)
    if versao is None or versao != item.versao:
        abort(409, description="Este registro mudou desde que a tela foi aberta. Recarregue a página e revise os dados antes de salvar.")


def preparar_novo(item):
    item.data_referencia = ler_referencia(request.form.get("data_referencia", ""), obrigatoria=True)
    item.data_vencimento = vencimento(item.data_referencia)
    item.motivo_inativacao = None if item.ativo else "manual"
    if isinstance(item, Posto) and item.ativo and item.data_vencimento <= hoje():
        item.ativo = False
        item.motivo_inativacao = "vencimento"


def situacao_item(item):
    if item.excluido_em:
        return "Excluído"
    if isinstance(item, Posto) and situacao_validade(item) == "vencido" and (item.ativo or item.motivo_inativacao == "vencimento"):
        return "Inativo por vencimento"
    if not item.ativo:
        return "Inativo por vencimento" if item.motivo_inativacao == "vencimento" else "Inativo manualmente"
    return "Ativo"


def problemas_rotograma(rotograma):
    problemas = []
    for tipo, vinculos, atributo in (("cerca", rotograma.cercas_vinculadas, "cerca"), ("posto", rotograma.postos_vinculados, "posto")):
        for vinculo in vinculos:
            item = getattr(vinculo, atributo)
            motivo = situacao_item(item)
            if motivo != "Ativo":
                problemas.append({"tipo": tipo, "item": item, "motivo": motivo,
                                  "chave": f"composicao:{rotograma.id}:{tipo}:{item.id}",
                                  "rotograma": rotograma})
    return problemas


def coletar_alertas():
    alertas = []
    for tipo, modelo in (("posto", Posto), ("rotograma", Rotograma)):
        for item in modelo.query.filter(modelo.excluido_em.is_(None)).all():
            if not item.ativo and item.motivo_inativacao != "vencimento":
                continue
            situacao = situacao_validade(item)
            if situacao == "vigente":
                continue
            dias = (item.data_vencimento - hoje()).days if item.data_vencimento else None
            mensagem = {"sem_data": "Data de referência não informada", "proximo": "Próximo do vencimento", "vencido": "Validade vencida"}[situacao]
            alertas.append({"chave": f"validade:{tipo}:{item.id}", "categoria": "validade", "tipo": tipo,
                            "item": item, "mensagem": mensagem, "dias": dias, "situacao": situacao})
    for r in Rotograma.query.filter(Rotograma.excluido_em.is_(None)).all():
        for problema in problemas_rotograma(r):
            alertas.append(dict(problema, categoria="composicao", mensagem=problema["motivo"]))
    for grupo in sugestoes_municipais.alertas():
        cerca = grupo['cerca']
        alertas.append({'chave': f'notificacao:cerca:{cerca.id}', 'categoria': 'nova_cerca', 'tipo': 'cerca',
            'item': cerca, 'mensagem': f"Nova cerca: {grupo['quantidade']} rotograma(s) sugerido(s) para análise por relação geográfica.",
            'notificacao_cerca_id': cerca.id})
    return alertas


def obter_cadastro(tipo, item_id):
    modelo = {"cerca": Cerca, "posto": Posto, "rotograma": Rotograma}.get(tipo)
    if modelo is None:
        abort(404)
    return db.get_or_404(modelo, item_id)


def destino_cadastro(tipo, item_id):
    return url_for("detalhe_rotograma", item_id=item_id) if tipo == "rotograma" else url_for("detalhe_cadastro", tipo=tipo, item_id=item_id)


@app.route("/alertas")
def listar_alertas():
    categoria = request.args.get("categoria", "")
    alertas = [a for a in coletar_alertas() if not categoria or a["categoria"] == categoria]
    return render_template("alertas.html", alertas=alertas, categoria=categoria,
                           rotina=db.session.get(ControleRotina, "vencimentos"))


@app.route("/cadastros/<tipo>/<int:item_id>")
def detalhe_cadastro(tipo, item_id):
    item = obter_cadastro(tipo, item_id)
    if tipo == "rotograma":
        return redirect(destino_cadastro(tipo, item_id))
    return render_template("detalhe_cadastro.html", item=item, tipo=tipo,
                           rotogramas=rotogramas_vinculados(tipo, item_id))


@app.route("/cadastros/<tipo>/<int:item_id>/regularizar", methods=["GET", "POST"])
def regularizar_cadastro(tipo, item_id):
    if tipo not in ("posto", "rotograma"):
        abort(404)
    item = obter_cadastro(tipo, item_id)
    if item.excluido_em:
        abort(409, description="Registros excluídos não podem ser regularizados.")
    if request.method == "POST":
        conferir_versao(item)
        try:
            referencia = ler_referencia(request.form.get("data_referencia", ""), obrigatoria=True, regularizacao=True)
        except ValueError as exc:
            flash(str(exc), "erro")
            return render_template("regularizar.html", item=item, tipo=tipo), 400
        alteracoes = {"data_referencia": referencia, "data_vencimento": vencimento(referencia)}
        if item.motivo_inativacao == "vencimento":
            alteracoes.update(ativo=True, motivo_inativacao=None)
        mudou = False
        for campo, novo in alteracoes.items():
            anterior = getattr(item, campo)
            if anterior != novo:
                setattr(item, campo, novo)
                registro = registrar_historico(tipo, item.id, item.nome, campo, anterior, novo, "regularizacao")
                if tipo == "posto":
                    criar_pendencias(registro, rotogramas_vinculados(tipo, item.id))
                mudou = True
        if mudou:
            db.session.commit()
        flash("Validade regularizada. Inativações manuais foram respeitadas.", "sucesso")
        return redirect(destino_cadastro(tipo, item_id))
    return render_template("regularizar.html", item=item, tipo=tipo)


@app.route("/cadastros/<tipo>/<int:item_id>/manter-inativo", methods=["POST"])
def manter_inativo(tipo, item_id):
    item = obter_cadastro(tipo, item_id)
    conferir_versao(item)
    if item.excluido_em:
        abort(409, description="Registro excluído.")
    for campo, novo in (("ativo", False), ("motivo_inativacao", "manual")):
        anterior = getattr(item, campo)
        if anterior != novo:
            setattr(item, campo, novo)
            registro = registrar_historico(tipo, item.id, item.nome, campo, anterior, novo, "inativacao_manual")
            if tipo != "rotograma":
                criar_pendencias(registro, rotogramas_vinculados(tipo, item.id))
    db.session.commit()
    flash("Registro mantido inativo por decisão manual. Vínculos preservados.", "sucesso")
    return redirect(destino_cadastro(tipo, item_id))


@app.route("/cadastros/<tipo>/<int:item_id>/excluir", methods=["GET", "POST"])
def excluir_cadastro(tipo, item_id):
    item = obter_cadastro(tipo, item_id)
    rotogramas = rotogramas_vinculados(tipo, item_id)
    if request.method == "POST":
        conferir_versao(item)
        if request.form.get("confirmar") != "sim":
            abort(400, description="Confirme a exclusão lógica.")
        if not item.excluido_em:
            item.excluido_em = agora_utc()
            ativo_anterior = item.ativo
            item.ativo = False
            if ativo_anterior:
                registrar_historico(tipo, item.id, item.nome, "ativo", ativo_anterior, False, "exclusao_logica")
            registro = registrar_historico(tipo, item.id, item.nome, "excluido_em", None, item.excluido_em, "exclusao_logica")
            if tipo != "rotograma":
                criar_pendencias(registro, rotogramas)
            db.session.commit()
        flash("Registro excluído das operações. Histórico e vínculos foram preservados.", "sucesso")
        return redirect(url_for({"cerca": "listar_cercas", "posto": "listar_postos", "rotograma": "listar_rotogramas"}[tipo]))
    return render_template("excluir.html", item=item, tipo=tipo, rotogramas=rotogramas)


def verificar_vencimentos(dia=None):
    """Uma concessão no banco coordena processos; versões evitam gravações repetidas."""
    dia = dia or hoje()
    agora = agora_utc()
    token = secrets.token_hex(16)
    controle = db.session.get(ControleRotina, "vencimentos")
    if controle is None:
        db.session.add(ControleRotina(nome="vencimentos"))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    adquirido = db.session.execute(update(ControleRotina).where(
        ControleRotina.nome == "vencimentos",
        or_(ControleRotina.bloqueado_ate.is_(None), ControleRotina.bloqueado_ate < agora)
    ).values(token=token, bloqueado_ate=agora + timedelta(minutes=10))).rowcount
    db.session.commit()
    if not adquirido:
        return 0
    total = 0
    try:
        ids = [p.id for p in Posto.query.filter(Posto.excluido_em.is_(None), Posto.ativo.is_(True), Posto.data_vencimento <= dia).all()]
        for item_id in ids:
            item = db.session.get(Posto, item_id, populate_existing=True)
            if not item or item.excluido_em or not item.ativo or not item.data_vencimento or item.data_vencimento > dia:
                continue
            try:
                anterior = item.motivo_inativacao
                item.ativo = False
                item.motivo_inativacao = "vencimento"
                registrar_historico("posto", item.id, item.nome, "ativo", True, False, "inativacao_automatica")
                registrar_historico("posto", item.id, item.nome, "motivo_inativacao", anterior,
                                    f"vencimento em {item.data_vencimento.isoformat()}", "inativacao_automatica")
                db.session.commit()
                total += 1
            except StaleDataError:
                db.session.rollback()
        db.session.execute(update(ControleRotina).where(ControleRotina.nome == "vencimentos", ControleRotina.token == token)
                           .values(ultima_execucao=agora_utc()))
        db.session.commit()
        return total
    finally:
        db.session.rollback()
        db.session.execute(update(ControleRotina).where(ControleRotina.nome == "vencimentos", ControleRotina.token == token)
                           .values(bloqueado_ate=None, token=None))
        db.session.commit()


@app.cli.command("verificar-validade")
def comando_validade():
    print(f"Postos inativados: {verificar_vencimentos()}")


def iniciar_verificador():
    if app.config.get("TESTING") or os.getenv("DESATIVAR_VERIFICADOR") == "1":
        return
    if "verificador" not in app.extensions:
        intervalo = max(1, int(os.getenv("INTERVALO_VERIFICACAO_SEGUNDOS", "900")))
        app.extensions["verificador"] = VerificadorInterno(app, verificar_vencimentos, intervalo)
        atexit.register(app.extensions["verificador"].encerrar)
    app.extensions["verificador"].iniciar()


@app.errorhandler(StaleDataError)
def conflito_versao(error):
    db.session.rollback()
    return render_template("conflito.html", mensagem="Outro usuário ou o verificador alterou este registro. Recarregue a página antes de tentar novamente."), 409


@app.errorhandler(409)
def conflito_http(error):
    db.session.rollback()
    return render_template("conflito.html", mensagem=error.description), 409


@app.errorhandler(IntegrityError)
def conflito_integridade(error):
    db.session.rollback()
    return render_template("conflito.html", mensagem="Não foi possível salvar: o registro ou vínculo já existe ou foi alterado por outra operação."), 409


@app.errorhandler(OperationalError)
def banco_ocupado(error):
    db.session.rollback()
    app.logger.exception("Banco indisponível ou ocupado")
    return render_template("conflito.html", mensagem="O banco está ocupado ou indisponível. Aguarde e tente novamente."), 503



def criar_aplicacao():
    with app.app_context():
        atualizar_estrutura()
        verificar_vencimentos()
    iniciar_verificador()
    return app


import sugestoes_municipais
sugestoes_municipais.instalar(sys.modules[__name__])

if __name__ == "__main__":
    criar_aplicacao()
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1", use_reloader=False)
