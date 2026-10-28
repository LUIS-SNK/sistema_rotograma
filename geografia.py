"""Análise geográfica auxiliar com fila persistente e decisões humanas."""
import os
import json
import hashlib
import secrets
import atexit
from datetime import timedelta
from flask import Blueprint, request, render_template, flash, redirect, url_for, abort, g
from sqlalchemy import event, update, or_, inspect
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.exc import IntegrityError
from validade import VerificadorInterno
from ors_client import ClienteORS, ErroORS, validar_ponto, distancia_trajeto, normalizar

UF_NOMES=dict(zip(('AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO'),('Acre','Alagoas','Amapá','Amazonas','Bahia','Ceará','Distrito Federal','Espírito Santo','Goiás','Maranhão','Mato Grosso','Mato Grosso do Sul','Minas Gerais','Pará','Paraíba','Paraná','Pernambuco','Piauí','Rio de Janeiro','Rio Grande do Norte','Rio Grande do Sul','Rondônia','Roraima','Santa Catarina','São Paulo','Sergipe','Tocantins')))


def instalar(sistema):
    global S,app,db,Geocodificacao,Trajeto,Tarefa,Analise,Cota
    S=sistema;app=S.app;db=S.db
    app.config.setdefault('ORS_ENABLED',os.getenv('ORS_ENABLED')=='1')
    app.config.setdefault('ORS_API_KEY',os.getenv('ORS_API_KEY',''))
    app.config.setdefault('ORS_RAIO_KM',float(os.getenv('ORS_RAIO_KM','10')))
    app.config.setdefault('ORS_CACHE_DIAS',int(os.getenv('ORS_CACHE_DIAS','30')))
    if not 0<float(app.config['ORS_RAIO_KM'])<=100:raise ValueError('ORS_RAIO_KM deve estar entre 0 e 100.')
    class Geocodificacao(db.Model):
        __tablename__='geocodificacoes'
        id=db.Column(db.Integer,primary_key=True)
        chave=db.Column(db.String(64),nullable=False,unique=True)
        consulta=db.Column(db.String(250),nullable=False)
        uf=db.Column(db.String(2),nullable=True)
        candidatos=db.Column(db.JSON,nullable=False,default=list)
        coordenadas=db.Column(db.JSON,nullable=True)
        status=db.Column(db.String(30),nullable=False,default='aguardando')
        fonte=db.Column(db.String(40),nullable=False,default='ORS Pelias')
        usuario_id=db.Column(db.Integer,db.ForeignKey('usuarios.id'),nullable=True)
        criado_em=db.Column(db.DateTime,nullable=False,default=S.agora_utc)
        versao=db.Column(db.Integer,nullable=False,default=1,server_default='1')
        __mapper_args__={'version_id_col':versao}
    class Trajeto(db.Model):
        __tablename__='trajetos_cache'
        id=db.Column(db.Integer,primary_key=True)
        chave=db.Column(db.String(64),nullable=False,index=True)
        geometria=db.Column(db.JSON,nullable=False)
        assinatura=db.Column(db.String(64),nullable=False)
        origem=db.Column(db.JSON,nullable=False)
        destino=db.Column(db.JSON,nullable=False)
        perfil=db.Column(db.String(40),nullable=False,default='driving-hgv')
        credito=db.Column(db.String(250),nullable=False)
        calculado_em=db.Column(db.DateTime,nullable=False,default=S.agora_utc)
        valido_ate=db.Column(db.DateTime,nullable=False)
    class Tarefa(db.Model):
        __tablename__='tarefas_geograficas'
        id=db.Column(db.Integer,primary_key=True)
        chave=db.Column(db.String(64),nullable=False,unique=True)
        cerca_id=db.Column(db.Integer,db.ForeignKey('cercas.id'),nullable=False,index=True)
        rotograma_id=db.Column(db.Integer,db.ForeignKey('rotogramas.id'),nullable=False,index=True)
        assinatura=db.Column(db.String(64),nullable=False)
        status=db.Column(db.String(35),nullable=False,default='pendente',index=True)
        tentativas=db.Column(db.Integer,nullable=False,default=0)
        mensagem=db.Column(db.String(500),nullable=True)
        proxima_tentativa=db.Column(db.DateTime,nullable=True,default=S.agora_utc)
        localizacao_id=db.Column(db.Integer,db.ForeignKey('geocodificacoes.id'),nullable=True)
        trajeto_id=db.Column(db.Integer,db.ForeignKey('trajetos_cache.id'),nullable=True)
        criado_em=db.Column(db.DateTime,nullable=False,default=S.agora_utc)
        atualizado_em=db.Column(db.DateTime,nullable=False,default=S.agora_utc,onupdate=S.agora_utc)
        versao=db.Column(db.Integer,nullable=False,default=1,server_default='1')
        __mapper_args__={'version_id_col':versao}
        cerca=db.relationship(S.Cerca)
        rotograma=db.relationship(S.Rotograma)
    class Analise(db.Model):
        __tablename__='analises_cercas'
        id=db.Column(db.Integer,primary_key=True)
        cerca_id=db.Column(db.Integer,db.ForeignKey('cercas.id'),nullable=False)
        rotograma_id=db.Column(db.Integer,db.ForeignKey('rotogramas.id'),nullable=False)
        tarefa_id=db.Column(db.Integer,db.ForeignKey('tarefas_geograficas.id'),nullable=False)
        trajeto_id=db.Column(db.Integer,db.ForeignKey('trajetos_cache.id'),nullable=False)
        contexto=db.Column(db.String(64),nullable=False)
        distancia_m=db.Column(db.Float,nullable=False)
        raio_m=db.Column(db.Float,nullable=False)
        precisao=db.Column(db.String(50),nullable=False)
        status=db.Column(db.String(30),nullable=False,default='pendente',index=True)
        usuario_id=db.Column(db.Integer,db.ForeignKey('usuarios.id'),nullable=True)
        decidida_em=db.Column(db.DateTime,nullable=True)
        justificativa=db.Column(db.String(500),nullable=True)
        criado_em=db.Column(db.DateTime,nullable=False,default=S.agora_utc)
        versao=db.Column(db.Integer,nullable=False,default=1,server_default='1')
        __mapper_args__={'version_id_col':versao}
        __table_args__=(db.UniqueConstraint('cerca_id','rotograma_id',name='uq_analise_cerca_rotograma'),)
        cerca=db.relationship(S.Cerca)
        rotograma=db.relationship(S.Rotograma)
        trajeto=db.relationship(Trajeto)
        tarefa=db.relationship(Tarefa)
        usuario=db.relationship(S.Usuario)
    class Cota(db.Model):
        __tablename__='cotas_ors'
        endpoint=db.Column(db.String(30),primary_key=True)
        inicio=db.Column(db.DateTime,nullable=False,default=S.agora_utc)
        usadas=db.Column(db.Integer,nullable=False,default=0)
        proxima=db.Column(db.DateTime,nullable=False,default=S.agora_utc)
        restante_api=db.Column(db.Integer,nullable=True)
        reset_api=db.Column(db.DateTime,nullable=True)
    S.Geocodificacao=Geocodificacao;S.TrajetoCache=Trajeto;S.TarefaGeografica=Tarefa;S.AnaliseCerca=Analise
    event.listen(db.session.session_factory.class_,'after_flush',capturar_alteracoes)
    event.listen(db.session.session_factory.class_,'before_commit',preparar_fila)
    event.listen(db.session.session_factory.class_,'after_rollback',lambda sess:sess.info.pop('geo_alteracoes',None))
    app.register_blueprint(bp)
    app.context_processor(lambda:{'geo_raio_km':app.config['ORS_RAIO_KM'],'geo_configurada':bool(app.config['ORS_ENABLED'] and app.config['ORS_API_KEY'])})
    app.cli.command('processar-geografia')(comando_processar)


def digest(objeto):
    return hashlib.sha256(json.dumps(objeto,sort_keys=True,ensure_ascii=True,separators=(',',':'),default=str).encode()).hexdigest()


def assinatura(c,r):
    return digest([c.cidade,c.estado,c.latitude,c.longitude,r.origem,r.destino,r.origem_uf,r.destino_uf,
                   r.origem_latitude,r.origem_longitude,r.destino_latitude,r.destino_longitude,'driving-hgv',float(app.config['ORS_RAIO_KM'])])


def disponiveis(c,r):
    return c.ativo and not c.excluido_em and r.ativo and not r.excluido_em and c.geo_habilitada


def capturar_alteracoes(sess,ctx):
    campos={'Cerca':('cidade','estado','latitude','longitude','ativo','excluido_em','geo_habilitada'),
            'Rotograma':('origem','destino','origem_uf','destino_uf','origem_latitude','origem_longitude','destino_latitude','destino_longitude','ativo','excluido_em')}
    for obj in list(sess.new)+list(sess.dirty):
        nome=type(obj).__name__
        if nome in campos and (obj in sess.new or any(inspect(obj).attrs[c].history.has_changes() for c in campos[nome])):
            sess.info.setdefault('geo_alteracoes',set()).add((nome,obj.id))


def preparar_fila(sess):
    if sess.info.get('geo_preparando'):return
    sess.info['geo_preparando']=True
    try:
        sess.flush()
        alvos=sess.info.pop('geo_alteracoes',set())
        if not alvos:return
        with sess.no_autoflush:
            if any(tipo=='Rotograma' for tipo,_ in alvos):cercas=sess.query(S.Cerca).filter_by(geo_habilitada=True).all()
            else:cercas=[sess.get(S.Cerca,item_id) for tipo,item_id in alvos if tipo=='Cerca']
            enfileirar(sess,[c for c in cercas if c])
    finally:sess.info.pop('geo_preparando',None)


def enfileirar(sess,cercas):
    rotas=sess.query(S.Rotograma).all()
    chaves={t.chave for t in sess.new if isinstance(t,Tarefa)}
    for c in cercas:
        for r in rotas:
            fp=assinatura(c,r)
            atuais=sess.query(Tarefa).filter_by(cerca_id=c.id,rotograma_id=r.id).all()
            for antigo in atuais:
                if antigo.assinatura!=fp or not disponiveis(c,r):
                    if antigo.status not in ('obsoleta','cancelada'):antigo.status='obsoleta' if disponiveis(c,r) else 'cancelada';antigo.proxima_tentativa=None
            analise=sess.query(Analise).filter_by(cerca_id=c.id,rotograma_id=r.id).first()
            if analise and (not disponiveis(c,r) or analise.tarefa.assinatura!=fp):
                if analise.status=='pendente':analise.status='obsoleta' if disponiveis(c,r) else 'cancelada'
            if not disponiveis(c,r):continue
            chave=digest([c.id,r.id,fp]);atual=next((t for t in atuais if t.chave==chave),None)
            if atual:
                if atual.status in ('obsoleta','cancelada'):
                    atual.status='pendente';atual.proxima_tentativa=S.agora_utc();atual.tentativas=0
                continue
            if chave not in chaves:
                sess.add(Tarefa(chave=chave,cerca_id=c.id,rotograma_id=r.id,assinatura=fp,status='pendente',tentativas=0,proxima_tentativa=S.agora_utc()))
                chaves.add(chave)


class Aguardar(Exception):
    def __init__(self,status,mensagem,espera=60,localizacao_id=None):
        super().__init__(mensagem);self.status=status;self.espera=espera;self.localizacao_id=localizacao_id


def reservar(endpoint):
    if not app.config['ORS_ENABLED'] or not app.config['ORS_API_KEY']:
        raise Aguardar('aguardando_configuracao','Integração aguardando configuração da chave ORS_API_KEY e ORS_ENABLED.',60)
    agora=S.agora_utc();c=db.session.get(Cota,endpoint)
    if c is None:c=Cota(endpoint=endpoint,inicio=agora,usadas=0,proxima=agora);db.session.add(c);db.session.flush()
    if agora-c.inicio>=timedelta(hours=24):c.inicio=agora;c.usadas=0
    limite=max(1,int(os.getenv('ORS_LIMITE_DIA_'+endpoint.upper(),'1000' if endpoint=='directions' else '500')))
    if c.usadas>=limite:raise Aguardar('aguardando_cota','Orçamento diário local atingido. A fila será retomada.',max(60,(c.inicio+timedelta(hours=24)-agora).total_seconds()))
    if c.proxima>agora:raise Aguardar('aguardando_cota','Aguardando intervalo entre consultas.',max(1,(c.proxima-agora).total_seconds()))
    if c.restante_api==0 and c.reset_api and c.reset_api>agora:
        raise Aguardar('aguardando_cota','Cota da API esgotada.',max(60,(c.reset_api-agora).total_seconds()))
    c.usadas+=1;c.proxima=agora+timedelta(seconds=max(2,float(os.getenv('ORS_INTERVALO_REQUISICOES','2.1'))))
    db.session.commit()


def registrar_headers(endpoint,headers):
    if not headers:return
    c=db.session.get(Cota,endpoint)
    if c is None:return
    try:
        valor=headers.get('x-ratelimit-remaining')
        if valor is not None:c.restante_api=max(0,int(valor))
        reset=headers.get('x-ratelimit-reset')
        if reset:
            from datetime import datetime,timezone
            c.reset_api=datetime.fromtimestamp(float(reset),timezone.utc).replace(tzinfo=None)
        db.session.commit()
    except (ValueError,TypeError,OverflowError):db.session.rollback()


def cliente():
    fabrica=app.config.get('ORS_CLIENT_FACTORY')
    return fabrica() if fabrica else ClienteORS(app.config['ORS_API_KEY'],reservar,registrar_headers)


def localizar(texto,uf='',coordenadas=None):
    if coordenadas is not None:return list(validar_ponto(coordenadas))
    if not texto or not texto.strip():raise Aguardar('revisar_localizacao','Origem, destino ou cidade não informados. Revise o cadastro.',None)
    chave=digest([normalizar(texto),uf,'Brasil','ORS Pelias'])
    local=Geocodificacao.query.filter_by(chave=chave).first()
    if local and local.status in ('confirmada','automatica') and local.coordenadas:return list(validar_ponto(local.coordenadas))
    if local:raise Aguardar('revisar_localizacao','Confirme a localização sugerida antes de continuar.',None,local.id)
    candidatos=cliente().geocodificar(texto,uf)
    local=Geocodificacao(chave=chave,consulta=texto,uf=uf or None,candidatos=candidatos,status='revisar',fonte='ORS Pelias')
    # Sem UF estruturada, a confirmação humana é obrigatória para os textos livres.
    if len(candidatos)==1 and uf:
        p=candidatos[0];estado=normalizar(p.get('uf','')).replace('br-','')
        if p.get('confianca',0)>=.9 and (estado==uf.casefold() or normalizar(p.get('regiao',''))==normalizar(UF_NOMES.get(uf,''))):
            local.coordenadas=list(validar_ponto(p['coordenadas']));local.status='automatica'
    db.session.add(local);db.session.commit()
    if local.status=='automatica':return list(validar_ponto(local.coordenadas))
    raise Aguardar('revisar_localizacao','Confirme a localização sugerida antes de continuar.',None,local.id)


def obter_trajeto(r):
    origem=localizar(r.origem,r.origem_uf or '',[r.origem_longitude,r.origem_latitude] if r.origem_latitude is not None else None)
    destino=localizar(r.destino,r.destino_uf or '',[r.destino_longitude,r.destino_latitude] if r.destino_latitude is not None else None)
    origem=list(validar_ponto(origem));destino=list(validar_ponto(destino))
    chave=digest([origem,destino,'driving-hgv'])
    trajeto=Trajeto.query.filter(Trajeto.chave==chave,Trajeto.valido_ate>S.agora_utc()).order_by(Trajeto.calculado_em.desc(),Trajeto.id.desc()).first()
    if trajeto:return trajeto
    dados=cliente().trajeto(origem,destino)
    linha=dados['linha']
    if len(linha)<2:raise ErroORS('Trajeto sem segmentos válidos.')
    linha=[list(validar_ponto(p)) for p in linha]
    trajeto=Trajeto(chave=chave,geometria=linha,assinatura=digest(linha),origem=origem,destino=destino,perfil='driving-hgv',credito=dados['credito'],
                    valido_ate=S.agora_utc()+timedelta(days=max(1,int(app.config['ORS_CACHE_DIAS']))))
    db.session.add(trajeto);db.session.commit();return trajeto


def auditar(item,anterior,novo,operacao):
    return S.registrar_historico('analise_cerca',item.id,f'{item.cerca.nome} | Rotograma: {item.rotograma.nome}','analise_geografica',anterior,novo,operacao)


def executar_tarefa(item_id):
    tarefa=db.session.get(Tarefa,item_id)
    if not tarefa:return
    c,r=tarefa.cerca,tarefa.rotograma;fp=tarefa.assinatura
    if not disponiveis(c,r) or assinatura(c,r)!=fp:
        tarefa.status='obsoleta';tarefa.proxima_tentativa=None;db.session.commit();return
    try:
        ponto=localizar(c.cidade or '',c.estado or '',[c.longitude,c.latitude] if c.latitude is not None else None)
        trajeto=obter_trajeto(r)
        distancia=distancia_trajeto(ponto,trajeto.geometria)
        raio=float(app.config['ORS_RAIO_KM'])*1000
        contexto=digest([fp,trajeto.assinatura,ponto,raio])
        # Consultas de rede podem levar tempo; revalida os dados antes de gravar.
        db.session.expire_all();tarefa=db.session.get(Tarefa,item_id);c,r=tarefa.cerca,tarefa.rotograma
        if not disponiveis(c,r) or assinatura(c,r)!=fp:
            tarefa.status='obsoleta';tarefa.proxima_tentativa=None;db.session.commit();return
        a=Analise.query.filter_by(cerca_id=c.id,rotograma_id=r.id).first()
        vinculado=S.RotogramaCerca.query.filter_by(cerca_id=c.id,rotograma_id=r.id).first() is not None
        if distancia<=raio:
            if a is None:
                a=Analise(cerca_id=c.id,rotograma_id=r.id,tarefa_id=tarefa.id,trajeto_id=trajeto.id,contexto=contexto,distancia_m=distancia,raio_m=raio,
                          precisao='Coordenadas informadas' if c.latitude is not None else 'Localização aproximada da cidade',status='ja_vinculada' if vinculado else 'pendente')
                db.session.add(a);db.session.flush();auditar(a,None,a.status,'sugestao_geografica')
            elif a.contexto!=contexto or a.status in ('obsoleta','cancelada','sem_correspondencia'):
                anterior=a.status;a.contexto=contexto;a.distancia_m=distancia;a.raio_m=raio;a.trajeto_id=trajeto.id;a.tarefa_id=tarefa.id
                a.precisao='Coordenadas informadas' if c.latitude is not None else 'Localização aproximada da cidade'
                a.status='ja_vinculada' if vinculado else 'pendente';a.usuario_id=None;a.decidida_em=None;a.justificativa=None
                auditar(a,anterior,a.status,'reavaliacao_geografica')
            elif a.status=='pendente':
                a.trajeto_id=trajeto.id;a.tarefa_id=tarefa.id
                if vinculado:
                    anterior=a.status;a.status='ja_vinculada';auditar(a,anterior,a.status,'vinculo_existente')
        elif a and a.status=='pendente':
            anterior=a.status;a.status='sem_correspondencia';auditar(a,anterior,a.status,'reavaliacao_geografica')
        tarefa.status='concluida';tarefa.trajeto_id=trajeto.id;tarefa.proxima_tentativa=None;tarefa.localizacao_id=None;tarefa.mensagem=f'Comparação concluída. Distância aproximada: {distancia/1000:.2f} km.'
        db.session.commit()
    except Aguardar as exc:
        db.session.rollback();tarefa=db.session.get(Tarefa,item_id)
        if tarefa.status in ('obsoleta','cancelada'):return
        tarefa.status=exc.status;tarefa.mensagem=str(exc);tarefa.localizacao_id=exc.localizacao_id
        tarefa.proxima_tentativa=S.agora_utc()+timedelta(seconds=exc.espera) if exc.espera is not None else None
        db.session.commit()
    except ErroORS as exc:
        db.session.rollback();tarefa=db.session.get(Tarefa,item_id)
        if tarefa.status in ('obsoleta','cancelada'):return
        tarefa.mensagem=str(exc)
        if exc.codigo in (401,403,429):
            tarefa.status='aguardando_cota' if exc.codigo==429 else 'aguardando_configuracao'
            tarefa.proxima_tentativa=S.agora_utc()+timedelta(seconds=exc.espera)
        else:
            tarefa.tentativas+=1;tarefa.status='erro' if tarefa.tentativas>=5 else 'aguardando_api'
            tarefa.proxima_tentativa=None if tarefa.status=='erro' else S.agora_utc()+timedelta(seconds=min(3600,60*2**(tarefa.tentativas-1)))
        db.session.commit()


def processar_fila():
    agora=S.agora_utc();token=secrets.token_hex(16)
    controle=db.session.get(S.ControleRotina,'geografia')
    if controle is None:
        db.session.add(S.ControleRotina(nome='geografia'))
        try:db.session.commit()
        except IntegrityError:db.session.rollback()
    adquirido=db.session.execute(update(S.ControleRotina).where(S.ControleRotina.nome=='geografia',or_(S.ControleRotina.bloqueado_ate.is_(None),S.ControleRotina.bloqueado_ate<agora)).values(token=token,bloqueado_ate=agora+timedelta(minutes=5))).rowcount
    db.session.commit()
    if not adquirido:return 0
    try:
        enfileirar(db.session,S.Cerca.query.filter_by(geo_habilitada=True).all());db.session.commit()
        # Um vínculo criado por outro fluxo encerra a sugestão sem duplicá-lo.
        for a in Analise.query.filter_by(status='pendente').all():
            if S.RotogramaCerca.query.filter_by(rotograma_id=a.rotograma_id,cerca_id=a.cerca_id).first():a.status='ja_vinculada'
        db.session.commit()
        ids=[t.id for t in Tarefa.query.filter(Tarefa.status.in_(['pendente','aguardando_api','aguardando_cota','aguardando_configuracao']),Tarefa.proxima_tentativa<=S.agora_utc()).order_by(Tarefa.proxima_tentativa,Tarefa.id).limit(4).all()]
        for item_id in ids:
            try:executar_tarefa(item_id)
            except StaleDataError:db.session.rollback()
            except Exception:
                db.session.rollback();t=db.session.get(Tarefa,item_id)
                if t and t.status not in ('obsoleta','cancelada'):
                    t.tentativas+=1;t.status='erro' if t.tentativas>=5 else 'aguardando_api';t.mensagem='Falha interna na análise. O cadastro e os vínculos foram preservados.'
                    t.proxima_tentativa=None if t.status=='erro' else S.agora_utc()+timedelta(minutes=2);db.session.commit()
        db.session.execute(update(S.ControleRotina).where(S.ControleRotina.nome=='geografia',S.ControleRotina.token==token).values(ultima_execucao=S.agora_utc()));db.session.commit()
        return len(ids)
    finally:
        db.session.rollback();db.session.execute(update(S.ControleRotina).where(S.ControleRotina.nome=='geografia',S.ControleRotina.token==token).values(token=None,bloqueado_ate=None));db.session.commit()


def iniciar():
    if app.config.get('TESTING') or os.getenv('DESATIVAR_VERIFICADOR')=='1':return
    if 'geografia_worker' not in app.extensions:
        app.extensions['geografia_worker']=VerificadorInterno(app,processar_fila,10)
        atexit.register(app.extensions['geografia_worker'].encerrar)
    app.extensions['geografia_worker'].iniciar()


def comando_processar():
    print('Tarefas verificadas:',processar_fila())


bp=Blueprint('geo',__name__)

@bp.route('/analises-cercas')
def listar():
    status=request.args.get('status','pendente')
    if status not in ('pendente','vinculada','dispensada','obsoleta','cancelada','sem_correspondencia','ja_vinculada','todas'):status='pendente'
    query=Analise.query
    if status!='todas':query=query.filter_by(status=status)
    return render_template('analises_cercas.html',analises=query.order_by(Analise.criado_em.desc()).all(),status=status,
                           tarefas=Tarefa.query.filter(~Tarefa.status.in_(['obsoleta','cancelada'])).order_by(Tarefa.atualizado_em.desc()).all(),
                           localizacoes=Geocodificacao.query.filter_by(status='revisar').all())

@bp.route('/analises-cercas/<int:item_id>')
def detalhe(item_id):
    a=db.get_or_404(Analise,item_id)
    return render_template('analise_cerca.html',a=a,atual=disponiveis(a.cerca,a.rotograma) and a.tarefa.assinatura==assinatura(a.cerca,a.rotograma) and a.trajeto.valido_ate>S.agora_utc())

@bp.route('/analises-cercas/<int:item_id>/decidir',methods=['POST'])
def decidir(item_id):
    a=db.get_or_404(Analise,item_id);S.conferir_versao(a)
    if a.status!='pendente':abort(409,description='Essa análise já foi concluída ou deixou de ser válida.')
    if not disponiveis(a.cerca,a.rotograma) or a.tarefa.assinatura!=assinatura(a.cerca,a.rotograma):abort(409,description='Os cadastros mudaram. Aguarde a reavaliação antes de decidir.')
    if a.trajeto.valido_ate<=S.agora_utc():
        a.tarefa.status='pendente';a.tarefa.proxima_tentativa=S.agora_utc();db.session.commit()
        abort(409,description='O trajeto precisa ser atualizado. A comparação entrou novamente na fila.')
    decisao=request.form.get('decisao')
    if decisao not in ('vincular','dispensar'):abort(400)
    justificativa=request.form.get('justificativa','').strip()
    if len(justificativa)>500:abort(400,description='A justificativa permite até 500 caracteres.')
    if request.form.get('confirmar')!='sim':abort(400,description='Confirme que revisou os dados aproximados.')
    if decisao=='vincular':
        # Versões dos dois cadastros garantem atomicidade com inativação/exclusão simultânea.
        a.cerca.versao+=1;a.rotograma.atualizado_em=S.agora_utc()
        existente=S.RotogramaCerca.query.filter_by(rotograma_id=a.rotograma_id,cerca_id=a.cerca_id).first()
        if not existente:
            db.session.add(S.RotogramaCerca(rotograma_id=a.rotograma_id,cerca_id=a.cerca_id));db.session.flush()
            h=S.registrar_historico('vinculo_cerca',a.cerca_id,f'{a.cerca.nome} | Rotograma: {a.rotograma.nome}','vinculo_cerca','não vinculado','Vínculo confirmado por análise geográfica','inclusao_vinculo')
            S.criar_pendencias(h,[a.rotograma],'alteracao_vinculo')
        a.status='vinculada'
    else:
        a.cerca.versao+=1;a.rotograma.atualizado_em=S.agora_utc();a.status='dispensada'
    a.usuario_id=g.usuario.id;a.decidida_em=S.agora_utc();a.justificativa=justificativa or None
    auditar(a,'pendente',f'{a.status}; justificativa: {justificativa or "não informada"}','decisao_analise')
    db.session.commit();flash('Análise concluída e decisão registrada no histórico.','sucesso')
    return redirect(url_for('geo.detalhe',item_id=a.id))

@bp.route('/analises-cercas/localizacoes/<int:item_id>',methods=['GET','POST'])
def confirmar_localizacao(item_id):
    local=db.get_or_404(Geocodificacao,item_id)
    if request.method=='POST':
        S.conferir_versao(local)
        if local.status!='revisar':abort(409,description='Esta localização já foi confirmada. Corrija coordenadas no cadastro para uma nova revisão.')
        if request.form.get('confirmar')!='sim':abort(400,description='Confirme a localização para continuar.')
        indice=request.form.get('candidato',type=int)
        if indice is not None and 0<=indice<len(local.candidatos):coord=local.candidatos[indice]['coordenadas']
        else:
            try:coord=validar_ponto([float(request.form.get('longitude','')),float(request.form.get('latitude',''))])
            except (ValueError,TypeError):abort(400,description='Selecione um candidato ou informe latitude e longitude válidas.')
        anterior=local.coordenadas;local.coordenadas=list(validar_ponto(coord));local.status='confirmada';local.usuario_id=g.usuario.id
        S.registrar_historico('localizacao',local.id,local.consulta,'coordenadas',anterior,coord,'confirmacao_localizacao')
        for tarefa in Tarefa.query.filter_by(localizacao_id=local.id,status='revisar_localizacao').all():tarefa.status='pendente';tarefa.proxima_tentativa=S.agora_utc();tarefa.localizacao_id=None
        db.session.commit();flash('Localização confirmada. Análises relacionadas voltarão à fila.','sucesso');return redirect(url_for('geo.listar'))
    return render_template('confirmar_localizacao.html',local=local,quantidade=Tarefa.query.filter_by(localizacao_id=local.id).count())

@bp.route('/analises-cercas/cercas/<int:item_id>/solicitar',methods=['POST'])
def solicitar(item_id):
    c=db.get_or_404(S.Cerca,item_id);S.conferir_versao(c)
    if not c.ativo or c.excluido_em:abort(409,description='Somente cercas ativas podem ser analisadas.')
    c.geo_habilitada=True
    S.registrar_historico('cerca',c.id,c.nome,'analise_geografica',None,'Solicitada','solicitacao_analise')
    enfileirar(db.session,[c]);db.session.commit()
    flash('Análise solicitada. Acompanhe o processamento na fila.','sucesso');return redirect(url_for('geo.listar'))

@bp.route('/analises-cercas/tarefas/<int:item_id>/repetir',methods=['POST'])
def repetir(item_id):
    t=db.get_or_404(Tarefa,item_id);S.conferir_versao(t)
    if not disponiveis(t.cerca,t.rotograma) or t.assinatura!=assinatura(t.cerca,t.rotograma):abort(409,description='Tarefa desatualizada. Revise os cadastros.')
    t.status='pendente';t.tentativas=0;t.proxima_tentativa=S.agora_utc();t.mensagem='Reprocessamento solicitado.'
    S.registrar_historico('analise_cerca',t.id,t.cerca.nome+' | '+t.rotograma.nome,'processamento',None,'Nova tentativa','reprocessamento_analise')
    db.session.commit();return redirect(url_for('geo.listar'))
