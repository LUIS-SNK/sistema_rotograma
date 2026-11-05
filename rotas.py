"""Rotas editáveis ORS. A chave e a validação do percurso ficam no servidor."""
import hashlib
import hmac
import json
import math
import os
import threading
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
import municipios
from flask import request, session, jsonify
from itsdangerous import URLSafeSerializer, BadSignature
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
import faixa_geografica as F

PERFIS = ('driving-hgv', 'driving-car')
_lock = threading.Lock()

def assinatura_extremos(dados):
    campos = ('origem','destino','origem_uf','destino_uf','origem_latitude','origem_longitude','destino_latitude','destino_longitude')
    valores = {}
    for c in campos:
        v = dados.get(c)
        if c.endswith(('latitude','longitude')):
            v = float(str(v).replace(',','.')) if v is not None and str(v).strip() else None
        else:
            v = str(v or '').strip()
        valores[c] = v
    return hashlib.sha256(json.dumps(valores,sort_keys=True).encode()).hexdigest()

def extremos_objeto(r):
    campos = ('origem','destino','origem_uf','destino_uf','origem_latitude','origem_longitude','destino_latitude','destino_longitude')
    return assinatura_extremos({c:getattr(r,c,None) for c in campos})

def rota_valida(r):
    d = getattr(r,'rota_dados',None)
    return d if d and d.get('extremos') == extremos_objeto(r) else None

def distancia_percurso(p, caminho):
    return min(F.distancia_segmento(p,a,b) for a,b in zip(caminho,caminho[1:]))

def comparacao(c,r,base,raio_padrao):
    rota = rota_valida(r)
    local = F.localizar(c.cidade,c.estado,c.latitude,c.longitude,base)
    if not rota or not local:
        return None
    largura = F.raio(r.faixa_raio_km if r.faixa_raio_km is not None else raio_padrao)
    distancia = distancia_percurso(local['ponto'],rota['caminho'])
    if distancia > largura+1e-8:
        return None
    contexto = [local['ponto'],rota['hash'],largura,'percurso-estradas-v1']
    return dict(distancia_km=round(distancia,6),raio_km=largura,ponto_cerca=local,
                origem=rota['origem'],destino=rota['destino'],referencia='rota',
                contexto=hashlib.sha256(json.dumps(contexto,sort_keys=True).encode()).hexdigest())

def instalar(S):
    global app, db, Cache, Uso, sistema
    sistema=S; app=S.app; db=S.db
    app.config.setdefault('ROTAS_ENABLED',os.getenv('ROTAS_ENABLED','1') == '1')
    app.config.setdefault('ORS_API_KEY',os.getenv('ORS_API_KEY',''))
    app.config.setdefault('ROTAS_LIMITE_DIA',int(os.getenv('ROTAS_LIMITE_DIA','500')))
    app.config.setdefault('ROTAS_LIMITE_MINUTO',int(os.getenv('ROTAS_LIMITE_MINUTO','10')))
    app.config.setdefault('MAX_CONTENT_LENGTH',8*1024*1024)

    class Cache(db.Model):
        __tablename__='roteirizacao_cache'
        chave=db.Column(db.String(64),primary_key=True)
        dados=db.Column(db.JSON,nullable=False)
        criado_em=db.Column(db.DateTime,nullable=False)

    class Uso(db.Model):
        __tablename__='roteirizacao_uso'
        periodo=db.Column(db.String(30),primary_key=True)
        quantidade=db.Column(db.Integer,nullable=False,default=0)

    app.add_url_rule('/api/rotas/calcular','calcular_rota',calcular,methods=['POST'])
    app.jinja_env.globals['token_rota']=token_rota
    app.jinja_env.globals['rota_editor']=editor

def serializador():
    return URLSafeSerializer(app.secret_key,salt='rota-aprovada-v1')

def token_rota(dados):
    return serializador().dumps(dados) if dados else ''

def editor(r):
    dados=rota_valida(r) if r else None
    if request.method=='POST':
        try:
            dados=serializador().loads(request.form.get('rota_token',''))
            if dados['extremos']!=assinatura_extremos(request.form):dados=None
        except (BadSignature,KeyError,TypeError,ValueError):dados=None
    return {'dados':dados,'disponivel':bool(app.config['ROTAS_ENABLED'] and app.config['ORS_API_KEY'])}


def formulario(dados):
    if 'rota_modo' not in dados:
        return {}
    modo=dados.get('rota_modo')
    if modo not in ('direta','estradas'):
        raise ValueError('Selecione uma forma de análise válida.')
    if modo == 'direta':
        return {'rota_por_estradas':False,'rota_dados':None}
    token=dados.get('rota_token','')
    if not token or len(token)>6_000_000:
        raise ValueError('Calcule a rota e aguarde a conclusão antes de salvar. Ou selecione a faixa reta.')
    try:
        rota=serializador().loads(token)
        if rota['extremos'] != assinatura_extremos(dados):
            raise ValueError('Origem ou destino alterado. Calcule novamente a rota antes de salvar.')
    except (BadSignature,KeyError,TypeError):
        raise ValueError('Percurso inválido. Calcule novamente a rota.') from None
    return {'rota_por_estradas':True,'rota_dados':rota}

def reservar():
    agora=datetime.now(timezone.utc)
    for periodo,limite in [('dia:'+agora.strftime('%Y%m%d'),app.config['ROTAS_LIMITE_DIA']),
                           ('min:'+agora.strftime('%Y%m%d%H%M'),app.config['ROTAS_LIMITE_MINUTO'])]:
        if not db.session.get(Uso,periodo):
            try:
                with db.session.begin_nested():
                    db.session.add(Uso(periodo=periodo,quantidade=0));db.session.flush()
            except IntegrityError:
                pass
        result=db.session.execute(update(Uso).where(Uso.periodo==periodo,Uso.quantidade<limite).values(quantidade=Uso.quantidade+1))
        if not result.rowcount:
            db.session.rollback()
            return False
    db.session.commit()
    return True

def geocodificar(m):
    query=urlencode({'text':m['nome']+', '+m['uf']+', Brasil','boundary.country':'BR','layers':'locality,localadmin','size':10})
    req=Request('https://api.openrouteservice.org/geocode/search?'+query,headers={'Authorization':app.config['ORS_API_KEY']})
    with urlopen(req,timeout=20) as res:
        bruto=res.read(1_000_001)
    if len(bruto)>1_000_000:raise ValueError('Resposta de localização muito grande.')
    candidatos=[];confirmados=[]
    for f in json.loads(bruto).get('features',[]):
        props=f.get('properties',{})
        if props.get('country_a')!='BRA' or props.get('region_a','').split('-')[-1]!=m['uf']:continue
        if municipios.normalizar(props.get('name',''))!=municipios.normalizar(m['nome']):continue
        ponto=F.ponto(f['geometry']['coordinates'])
        candidatos.append(ponto)
        if municipios.normalizar(props.get('localadmin',''))==municipios.normalizar(m['nome']):confirmados.append(ponto)
    locais=confirmados or candidatos
    unicos={tuple(p) for p in locais}
    if len(unicos)!=1:raise ValueError('Não foi possível identificar a cidade sem ambiguidade. Informe suas coordenadas.')
    return {'ponto':list(unicos.pop()),'precisao':'Localização aproximada da cidade (OpenRouteService)', 'municipio':m['nome']+'/'+m['uf']}

def localizar_extremo(texto,uf,lat,lon,base):
    if lat is not None or lon is not None:
        return F.localizar(texto,uf,lat,lon,base)
    m=F.municipio_texto(texto,uf,base)
    if not m:return None
    chave=hashlib.sha256(('geocidade-v1:'+m['codigo']).encode()).hexdigest()
    with _lock:
        cache=db.session.get(Cache,chave)
        if cache and cache.criado_em>datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(days=180):
            return cache.dados
        if not reservar():raise ValueError('Limite de consultas atingido. Aguarde para localizar as cidades.')
        local=geocodificar(m)
        if cache:
            cache.dados=local;cache.criado_em=datetime.now(timezone.utc).replace(tzinfo=None)
        else:db.session.add(Cache(chave=chave,dados=local,criado_em=datetime.now(timezone.utc).replace(tzinfo=None)))
        db.session.commit()
    return local

def consultar(pontos,perfil):
    corpo=json.dumps({'coordinates':pontos,'instructions':False,'elevation':False,'radiuses':[3000]*len(pontos)}).encode()
    requisicao=Request('https://api.openrouteservice.org/v2/directions/'+perfil+'/geojson',data=corpo,
                       headers={'Authorization':app.config['ORS_API_KEY'],'Content-Type':'application/json','Accept':'application/geo+json'})
    with urlopen(requisicao,timeout=25) as resposta:
        bruto=resposta.read(10_000_001)
    if len(bruto)>10_000_000:
        raise ValueError('O percurso retornado é muito grande. Divida o rotograma.')
    feature=json.loads(bruto)['features'][0]
    if feature['geometry']['type']!='LineString':
        raise ValueError('A API não retornou um percurso válido.')
    caminho=feature['geometry']['coordinates']
    if not 2<=len(caminho)<=100_000:
        raise ValueError('O percurso retornado é inválido ou muito grande.')
    caminho=[F.ponto(p[:2]) for p in caminho]
    indices=feature['properties']['way_points']
    if len(indices)!=len(pontos) or indices!=sorted(indices) or any(not isinstance(i,int) or not 0<=i<len(caminho) for i in indices):
        raise ValueError('Pontos de passagem inválidos no retorno da API.')
    if any(F.angular(p,caminho[i])*F.RAIO_TERRA_KM>5 for p,i in zip(pontos,indices)):
        raise ValueError('Um ponto está distante das vias encontradas. Ajuste sua localização.')
    distancia=float(feature['properties']['summary']['distance'])/1000
    if not math.isfinite(distancia) or distancia<=0:
        raise ValueError('Distância inválida no retorno da API.')
    return {'caminho':caminho,'indices':indices,'distancia_km':distancia}

def calcular():
    enviado=request.headers.get('X-CSRF-Token','')
    if not enviado or not hmac.compare_digest(enviado,session.get('_municipal_csrf','')):
        return jsonify(erro='Formulário expirado. Recarregue a página.'),400
    if not app.config['ROTAS_ENABLED'] or not app.config['ORS_API_KEY']:
        return jsonify(erro='O cálculo de rotas precisa de uma chave OpenRouteService configurada no servidor.'),503
    if request.content_length and request.content_length>32_000:
        return jsonify(erro='Muitos dados enviados ao cálculo de rota.'),413
    try:
        db.session.info['municipios_preparando']=True
        dados=request.get_json(silent=True)
        if not isinstance(dados,dict):raise ValueError('Dados de rota inválidos.')
        perfil=dados.get('perfil','driving-hgv')
        if perfil not in PERFIS:raise ValueError('Perfil de veículo inválido.')
        geograficos=sistema.dados_geograficos('rotograma',{k:v for k,v in dados.items() if k not in ('rota_modo','rota_token')})
        base=sistema.sugestoes_municipais.obter_base()
        extremos=[]
        for prefixo in ('origem_','destino_'):
            local=localizar_extremo(dados.get(prefixo[:-1],''),geograficos.get(prefixo+'uf'),geograficos.get(prefixo+'latitude'),geograficos.get(prefixo+'longitude'),base)
            if not local:raise ValueError('Informe municípios/UF reconhecidos ou coordenadas para origem e destino.')
            extremos.append(local)
        intermediarios=dados.get('intermediarios',[])
        if not isinstance(intermediarios,list) or len(intermediarios)>48:raise ValueError('Use no máximo 48 pontos intermediários.')
        pontos=[extremos[0]['ponto']]+[F.ponto(p) for p in intermediarios]+[extremos[1]['ponto']]
        chave=hashlib.sha256(json.dumps([pontos,perfil,'ors-v2-snap3000']).encode()).hexdigest()
        with _lock:
            cache=db.session.get(Cache,chave)
            if cache and cache.criado_em>datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(days=7):
                resultado=cache.dados
            else:
                if not reservar():return jsonify(erro='Limite de consultas atingido. Aguarde para calcular novamente.'),429
                resultado=consultar(pontos,perfil)
                if cache:
                    cache.dados=resultado;cache.criado_em=datetime.now(timezone.utc).replace(tzinfo=None)
                else:db.session.add(Cache(chave=chave,dados=resultado,criado_em=datetime.now(timezone.utc).replace(tzinfo=None)))
                db.session.commit()
        rota=dict(resultado,pontos=pontos,perfil=perfil,extremos=assinatura_extremos(dados),origem=extremos[0],destino=extremos[1],
                  hash=hashlib.sha256(json.dumps(resultado['caminho']).encode()).hexdigest(),fonte='OpenRouteService / OpenStreetMap')
        return jsonify(rota=rota,token=token_rota(rota))
    except HTTPError as exc:
        db.session.rollback()
        mensagem={401:'Chave da API inválida.',403:'A API recusou a chave ou o acesso.',429:'Limite da API atingido. Tente mais tarde.',400:'A API não encontrou uma rota para esses pontos.',404:'Nenhuma via foi encontrada para um dos pontos.'}.get(exc.code,'O serviço de rotas está indisponível. Tente novamente.')
        return jsonify(erro=mensagem),503
    except (URLError,TimeoutError,OSError):
        db.session.rollback()
        return jsonify(erro='Sem conexão com o serviço de rotas. Seu cadastro não foi alterado.'),503
    except (ValueError,TypeError,KeyError,IndexError,OverflowError):
        db.session.rollback()
        return jsonify(erro='Não foi possível calcular. Confira origem, destino, coordenadas e pontos de passagem. Se a cidade não for identificada, informe coordenadas.'),400
    finally:
        db.session.info.pop('municipios_preparando',None)
