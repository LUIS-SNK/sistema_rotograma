"""Acesso individual e autoria. Sem usuário ou senha padrão."""
import os
import re
import secrets
from datetime import timedelta
from pathlib import Path
from hashlib import sha256
import click
from flask import Blueprint, request, session, g, redirect, url_for, render_template, flash, abort, has_request_context
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.security import generate_password_hash, check_password_hash


def instalar(sistema):
    global S,app,db,Usuario,FalhaLogin
    S=sistema;app=S.app;db=S.db
    class Usuario(db.Model):
        __tablename__='usuarios'
        id=db.Column(db.Integer,primary_key=True)
        login=db.Column(db.String(80),nullable=False,unique=True)
        nome=db.Column(db.String(120),nullable=False)
        senha_hash=db.Column(db.String(255),nullable=False)
        ativo=db.Column(db.Boolean,nullable=False,default=True)
        admin=db.Column(db.Boolean,nullable=False,default=False)
        criado_em=db.Column(db.DateTime,nullable=False,default=S.agora_utc)
        versao=db.Column(db.Integer,nullable=False,default=1,server_default='1')
        __mapper_args__={'version_id_col':versao}
    class FalhaLogin(db.Model):
        __tablename__='falhas_login'
        chave=db.Column(db.String(64),primary_key=True)
        tentativas=db.Column(db.Integer,nullable=False,default=0)
        inicio=db.Column(db.DateTime,nullable=False,default=S.agora_utc)
        bloqueado_ate=db.Column(db.DateTime,nullable=True)
    S.Usuario=Usuario
    if not os.getenv('SECRET_KEY') or os.getenv('SECRET_KEY') in ('dev-chave-alterar','SUBSTITUA-POR-UMA-CHAVE-ALEATORIA','troque-esta-chave-por-uma-chave-segura'):
        if app.config['SQLALCHEMY_DATABASE_URI'].endswith(':memory:'):
            app.secret_key=secrets.token_hex(32)
        else:
            pasta=Path(app.instance_path);pasta.mkdir(exist_ok=True)
            arquivo=pasta/'secret.key'
            if not arquivo.exists():
                try:
                    with arquivo.open('x',encoding='ascii') as f:f.write(secrets.token_hex(32))
                except FileExistsError:pass
            app.secret_key=arquivo.read_text(encoding='ascii').strip()
    app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE')=='1',PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
    CSRFProtect(app)
    app.before_request_funcs.setdefault(None,[]).insert(0,proteger)
    app.context_processor(lambda:{'usuario_atual':getattr(g,'usuario',None)})
    app.register_blueprint(bp)
    app.cli.command('criar-usuario')(comando_usuario)
    app.cli.command('preparar-acesso')(primeiro_acesso)
    app.errorhandler(CSRFError)(lambda erro:(render_template('conflito.html',mensagem='Formulário expirado ou inválido. Recarregue a página e tente novamente.'),400))


def proteger():
    g.usuario=None
    if app.config.get('TESTING') and app.config.get('LOGIN_DISABLED'):
        return
    usuario=db.session.get(Usuario,session.get('usuario_id')) if session.get('usuario_id') else None
    if usuario and usuario.ativo and usuario.versao==session.get('usuario_versao'):
        g.usuario=usuario
    elif session.get('usuario_id'):
        session.clear()
    if request.endpoint in ('acesso.login','static') or request.endpoint is None:return
    if not g.usuario:
        if request.method!='GET':abort(401,description='Entre no sistema antes de executar esta ação.')
        return redirect(url_for('acesso.login',next=request.full_path if request.query_string else request.path))


def exigir_admin():
    if not getattr(g,'usuario',None) or not g.usuario.admin:abort(403)


def validar_usuario(login,nome,senha):
    login=login.strip().casefold();nome=nome.strip()
    if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{2,79}',login):raise ValueError('Use um login de 3 a 80 letras, números, pontos, hífens ou sublinhados.')
    if not nome or len(nome)>120:raise ValueError('Informe um nome de até 120 caracteres.')
    if len(senha)<10 or len(senha)>200:raise ValueError('A senha deve ter de 10 a 200 caracteres.')
    return login,nome


def registrar_usuario(login,nome,senha,admin=False):
    login,nome=validar_usuario(login,nome,senha)
    if Usuario.query.filter_by(login=login).first():raise ValueError('Esse login já existe.')
    u=Usuario(login=login,nome=nome,senha_hash=generate_password_hash(senha),ativo=True,admin=admin)
    db.session.add(u);db.session.flush()
    S.registrar_historico('usuario',u.id,u.nome,'conta',None,'Administrador' if admin else 'Usuário','cadastro_usuario')
    db.session.commit();return u


bp=Blueprint('acesso',__name__)

@bp.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        nome=request.form.get('login','').strip().casefold()
        chave=sha256((nome+'|'+str(request.remote_addr)).encode()).hexdigest()
        agora=S.agora_utc();falha=db.session.get(FalhaLogin,chave)
        if falha and falha.bloqueado_ate and falha.bloqueado_ate>agora:
            flash('Muitas tentativas. Aguarde alguns minutos antes de tentar novamente.','erro')
            return render_template('login.html',sem_usuarios=not Usuario.query.first()),429
        u=Usuario.query.filter_by(login=nome).first()
        # Também verifica um hash inválido quando o login não existe.
        hash_validacao=u.senha_hash if u else generate_password_hash('credencial-inexistente')
        valido=check_password_hash(hash_validacao,request.form.get('senha',''))
        if not u or not u.ativo or not valido:
            if not falha:falha=FalhaLogin(chave=chave,tentativas=0,inicio=agora);db.session.add(falha)
            if agora-falha.inicio>timedelta(minutes=15):falha.tentativas=0;falha.inicio=agora
            falha.tentativas+=1
            if falha.tentativas>=5:falha.bloqueado_ate=agora+timedelta(minutes=5)
            db.session.commit();flash('Login ou senha inválidos.','erro')
            return render_template('login.html',sem_usuarios=not Usuario.query.first()),401
        if falha:db.session.delete(falha);db.session.commit()
        session.clear();session.permanent=True;session['usuario_id']=u.id;session['usuario_versao']=u.versao
        proximo=request.args.get('next','/')
        if not proximo.startswith('/') or proximo.startswith('//') or '\\' in proximo:proximo='/'
        return redirect(proximo)
    return render_template('login.html',sem_usuarios=not Usuario.query.first())

@bp.route('/sair',methods=['POST'])
def sair():
    session.clear();return redirect(url_for('acesso.login'))

@bp.route('/usuarios',methods=['GET','POST'])
def usuarios():
    exigir_admin()
    if request.method=='POST':
        try:
            registrar_usuario(request.form.get('login',''),request.form.get('nome',''),request.form.get('senha',''),request.form.get('admin')=='on')
            flash('Usuário criado.','sucesso');return redirect(url_for('acesso.usuarios'))
        except ValueError as e:flash(str(e),'erro')
    return render_template('usuarios.html',usuarios=Usuario.query.order_by(Usuario.nome).all())

@bp.route('/usuarios/<int:item_id>/alterar',methods=['POST'])
def alterar_usuario(item_id):
    exigir_admin();u=db.get_or_404(Usuario,item_id);S.conferir_versao(u)
    senha=request.form.get('nova_senha','')
    if senha:
        try:validar_usuario(u.login,u.nome,senha)
        except ValueError as exc:
            flash(str(exc),'erro');return redirect(url_for('acesso.usuarios'))
        u.senha_hash=generate_password_hash(senha)
        S.registrar_historico('usuario',u.id,u.nome,'senha','Hash anterior','Senha redefinida','redefinicao_senha')
    else:
        if u.id==g.usuario.id:abort(400,description='Não é possível desativar a própria conta.')
        if u.admin and u.ativo and Usuario.query.filter_by(admin=True,ativo=True).count()<=1:abort(409,description='Preserve ao menos um administrador ativo.')
        anterior=u.ativo;u.ativo=not u.ativo
        S.registrar_historico('usuario',u.id,u.nome,'ativo',anterior,u.ativo,'situacao_usuario')
    db.session.commit();flash('Conta atualizada. Sessões antigas deixam de ser válidas.','sucesso')
    return redirect(url_for('acesso.usuarios'))


def comando_usuario():
    S.atualizar_estrutura()
    try:
        registrar_usuario(click.prompt('Login'),click.prompt('Nome'),click.prompt('Senha',hide_input=True,confirmation_prompt=True),click.confirm('Administrador?',default=False))
        click.echo('Conta criada.')
    except ValueError as e:raise click.ClickException(str(e))


def primeiro_acesso():
    S.atualizar_estrutura()
    if Usuario.query.count():click.echo('Acesso já configurado.');return
    click.echo('Configure o primeiro administrador. Não existe senha padrão.')
    try:
        registrar_usuario(click.prompt('Login'),click.prompt('Nome'),click.prompt('Senha',hide_input=True,confirmation_prompt=True),True)
        click.echo('Administrador criado.')
    except ValueError as e:raise click.ClickException(str(e))
