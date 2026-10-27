import os
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, func, or_, inspect, text

TIPOS_POSTO = ("Refeição", "Refeição/Pernoite", "Abastecimento", "Abastecimento/Refeição/Pernoite", "Abastecimento/Refeição")

load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-chave-alterar")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///rotogramas.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


class Cerca(db.Model):
    __tablename__ = "cercas"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, index=True)
    tipo = db.Column(db.String(80), nullable=False, default="")
    velocidade = db.Column(db.Numeric(7, 2), nullable=True)
    descricao = db.Column(db.Text, nullable=True)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


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
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Rotograma(db.Model):
    __tablename__ = "rotogramas"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False, index=True)
    origem = db.Column(db.String(180), nullable=True)
    destino = db.Column(db.String(180), nullable=True)
    descricao = db.Column(db.Text, nullable=True)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class RotogramaCerca(db.Model):
    __tablename__ = "rotograma_cercas"
    id = db.Column(db.Integer, primary_key=True)
    rotograma_id = db.Column(db.Integer, db.ForeignKey("rotogramas.id"), nullable=False)
    cerca_id = db.Column(db.Integer, db.ForeignKey("cercas.id"), nullable=False)
    vinculado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    rotograma = db.relationship("Rotograma", backref=db.backref("cercas_vinculadas", cascade="all, delete-orphan"))
    cerca = db.relationship("Cerca")
    __table_args__ = (UniqueConstraint("rotograma_id", "cerca_id", name="uq_rotograma_cerca"),)


class RotogramaPosto(db.Model):
    __tablename__ = "rotograma_postos"
    id = db.Column(db.Integer, primary_key=True)
    rotograma_id = db.Column(db.Integer, db.ForeignKey("rotogramas.id"), nullable=False)
    posto_id = db.Column(db.Integer, db.ForeignKey("postos.id"), nullable=False)
    vinculado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
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
    data_alteracao = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class Pendencia(db.Model):
    __tablename__ = "pendencias"
    id = db.Column(db.Integer, primary_key=True)
    rotograma_id = db.Column(db.Integer, db.ForeignKey("rotogramas.id"), nullable=False, index=True)
    historico_id = db.Column(db.Integer, db.ForeignKey("historico_alteracoes.id"), nullable=False, index=True)
    tipo = db.Column(db.String(40), nullable=False, default="alteracao_cadastral")
    descricao = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="aberta", index=True)
    criada_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    concluida_em = db.Column(db.DateTime, nullable=True)
    rotograma = db.relationship("Rotograma")
    historico = db.relationship("HistoricoAlteracao")



def normalizar_nome(nome):
    nome = " ".join(nome.split()).casefold()
    return "".join(c for c in unicodedata.normalize("NFKD", nome) if not unicodedata.combining(c))


def ordenar_por_nome(itens):
    return sorted(itens, key=lambda item: (normalizar_nome(item.nome), item.id))


def filtrar_status(query, modelo):
    status = request.args.get("status", "")
    if status in ("ativo", "inativo"):
        query = query.filter(modelo.ativo.is_(status == "ativo"))
    return query


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
    return {"tipos_posto": TIPOS_POSTO}


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
    if erro:
        flash(erro, "erro")
        return render_template(template, **{tipo: item}), status


def atualizar_estrutura():
    """Migração aditiva, compatível com SQLite e MySQL; preserva postos existentes."""
    db.create_all()
    with db.engine.begin() as connection:
        if "tipo" not in {coluna["name"] for coluna in inspect(connection).get_columns("postos")}:
            connection.execute(text("ALTER TABLE postos ADD COLUMN tipo VARCHAR(80) NULL"))


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


@app.route("/")
def dashboard():
    return render_template(
        "dashboard.html",
        cercas=Cerca.query.count(),
        postos=Posto.query.count(),
        rotogramas=Rotograma.query.count(),
        pendencias=Pendencia.query.filter_by(status="aberta").count(),
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
    itens = buscar_texto(query.all(), busca, ("nome", "tipo", "descricao"))
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
        cerca = Cerca(nome=nome, tipo=request.form.get("tipo", "").strip(),
                      velocidade=velocidade, descricao=request.form.get("descricao", "").strip(),
                      ativo=bool_form(request.form.get("ativo")))
        db.session.add(cerca)
        db.session.flush()
        for campo, valor in [("nome", nome), ("tipo", cerca.tipo), ("velocidade", velocidade),
                             ("descricao", cerca.descricao), ("ativo", cerca.ativo)]:
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
    return render_template("postos.html", postos=ordenar_por_nome(itens), busca=busca,
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
        db.session.add(posto)
        db.session.flush()
        for campo in ("nome", "tipo", "endereco", "cidade", "estado", "descricao", "ativo"):
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
    return render_template("rotogramas.html", rotogramas=ordenar_por_nome(itens), busca=busca)


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
                              ativo=bool_form(request.form.get("ativo")))
        db.session.add(rotograma)
        db.session.flush()
        for campo in ("nome", "origem", "destino", "descricao", "ativo"):
            registrar_historico("rotograma", rotograma.id, rotograma.nome, campo, None, getattr(rotograma, campo), "cadastro")
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
    cercas_disponiveis = Cerca.query.filter(Cerca.ativo.is_(True), ~Cerca.id.in_(cercas_ids)).order_by(Cerca.nome).all() if cercas_ids else Cerca.query.filter_by(ativo=True).order_by(Cerca.nome).all()
    postos_disponiveis = Posto.query.filter(Posto.ativo.is_(True), ~Posto.id.in_(postos_ids)).order_by(Posto.nome).all() if postos_ids else Posto.query.filter_by(ativo=True).order_by(Posto.nome).all()
    cercas_disponiveis = ordenar_por_nome(cercas_disponiveis)
    postos_disponiveis = ordenar_por_nome(postos_disponiveis)
    pendencias = Pendencia.query.filter_by(rotograma_id=item_id).order_by(Pendencia.criada_em.desc()).limit(10).all()
    return render_template("detalhe_rotograma.html", rotograma=rotograma,
                           cercas_vinculadas=cercas_vinculadas, postos_vinculados=postos_vinculados,
                           cercas_disponiveis=cercas_disponiveis, postos_disponiveis=postos_disponiveis,
                           pendencias=pendencias)


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
    cerca = db.get_or_404(Cerca, request.form.get("cerca_id", type=int))
    if not cerca.ativo:
        flash("Não é possível vincular uma cerca inativa.", "erro")
        return redirect(url_for("detalhe_rotograma", item_id=item_id))
    existente = RotogramaCerca.query.filter_by(rotograma_id=item_id, cerca_id=cerca.id).first()
    if existente:
        flash("Essa cerca já está vinculada ao rotograma.", "erro")
        return redirect(url_for("detalhe_rotograma", item_id=item_id))
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
    posto = db.get_or_404(Posto, request.form.get("posto_id", type=int))
    if not posto.ativo:
        flash("Não é possível vincular um posto inativo.", "erro")
        return redirect(url_for("detalhe_rotograma", item_id=item_id))
    if RotogramaPosto.query.filter_by(rotograma_id=item_id, posto_id=posto.id).first():
        flash("Esse posto já está vinculado ao rotograma.", "erro")
        return redirect(url_for("detalhe_rotograma", item_id=item_id))
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
    query = Pendencia.query
    if status != "todas":
        query = query.filter_by(status=status)
    pendencias = query.order_by(Pendencia.criada_em.desc()).all()
    return render_template("pendencias.html", pendencias=pendencias, status= status)


@app.route("/pendencias/<int:item_id>/concluir", methods=["POST"])
def concluir_pendencia(item_id):
    pendencia = db.get_or_404(Pendencia, item_id)
    if pendencia.status == "aberta":
        pendencia.status = "concluida"
        pendencia.concluida_em = datetime.utcnow()
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


if __name__ == "__main__":
    with app.app_context():
        atualizar_estrutura()
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1")
