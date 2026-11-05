"""Visualização geográfica, sem consultas de rota ou alterações no banco."""
import math
import faixa_geografica as F

def deslocar(p, rumo, km):
    lon, lat = map(math.radians, p)
    d = km / F.RAIO_TERRA_KM
    y = math.asin(max(-1, min(1, math.sin(lat)*math.cos(d)+math.cos(lat)*math.sin(d)*math.cos(rumo))))
    x = lon + math.atan2(math.sin(rumo)*math.sin(d)*math.cos(lat), math.cos(d)-math.sin(lat)*math.sin(y))
    return [math.degrees(x), math.degrees(y)]

def geometria(d):
    if not d.get('ativa') or d.get('erro'):
        return None
    if d.get('rota'):
        return {'linha':d['rota']['caminho'], 'raio_km':d['raio_km'], 'por_estradas':True}
    a,b = d['origem']['ponto'],d['destino']['ponto']
    distancia = F.angular(a,b)*F.RAIO_TERRA_KM
    r = d['raio_km']
    if distancia < 1e-7:
        return {'linha':[a,b], 'anel':[deslocar(a, math.radians(t), r) for t in range(0,361,5)]}
    inicial = F.rumo(a,b)
    linha = [deslocar(a,inicial,distancia*i/100) for i in range(101)]
    linha[0],linha[-1]=a,b
    rumos=[F.rumo(x,b) for x in linha[:-1]]+[F.rumo(b,a)+math.pi]
    esquerda=[deslocar(x,t-math.pi/2,r) for x,t in zip(linha,rumos)]
    ponta_b=[deslocar(b,rumos[-1]-math.pi/2+math.pi*i/36,r) for i in range(37)]
    direita=[deslocar(x,t+math.pi/2,r) for x,t in zip(linha,rumos)][::-1]
    ponta_a=[deslocar(a,inicial+math.pi/2+math.pi*i/36,r) for i in range(37)]
    anel=esquerda+ponta_b+direita+ponta_a
    anel.append(anel[0])
    return {'linha':linha,'anel':anel}

def dados(r,cercas,postos,base,faixa):
    marcadores=[]; ausentes=[]
    import rotas
    percurso=rotas.rota_valida(r) if getattr(r,'rota_por_estradas',False) else None
    def adicionar(tipo,nome,texto,uf,lat=None,lon=None):
        local=F.localizar(texto,uf,lat,lon,base)
        if local:
            marcadores.append(dict(tipo=tipo,nome=nome,**local))
        else:
            ausentes.append(tipo+' · '+nome)
    if percurso:
        marcadores.extend([dict(tipo='Origem',nome=r.origem or 'Origem',**percurso['origem']), dict(tipo='Destino',nome=r.destino or 'Destino',**percurso['destino'])])
    else:
        adicionar('Origem',r.origem or 'Origem',r.origem,r.origem_uf,r.origem_latitude,r.origem_longitude)
        adicionar('Destino',r.destino or 'Destino',r.destino,r.destino_uf,r.destino_latitude,r.destino_longitude)
    for v in cercas:
        c=v.cerca
        adicionar('Cerca',c.nome,c.cidade,c.estado,c.latitude,c.longitude)
    for v in postos:
        c=v.posto
        adicionar('Posto',c.nome,c.cidade,c.estado)
    desenho=geometria(faixa)
    if percurso and not desenho:
        desenho={'linha':percurso['caminho'],'raio_km':0,'por_estradas':True}
    return {'marcadores':marcadores,'ausentes':ausentes,'faixa':desenho}
