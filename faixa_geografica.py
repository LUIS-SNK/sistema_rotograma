"""Cápsula geográfica: distância ao segmento direto, em modelo esférico."""
import hashlib
import json
import math
import re
import municipios

RAIO_TERRA_KM = 6371.0088


def ponto(valor):
    if len(valor) != 2:
        raise ValueError('Informe longitude e latitude.')
    lon, lat = map(float, valor)
    if not all(math.isfinite(v) for v in (lon, lat)) or not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise ValueError('Latitude deve estar entre -90 e 90; longitude entre -180 e 180.')
    return [lon, lat]


def angular(a, b):
    lon1, lat1 = map(math.radians, ponto(a)); lon2, lat2 = map(math.radians, ponto(b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2*math.atan2(math.sqrt(max(0, min(1, h))), math.sqrt(max(0, 1-h)))


def rumo(a, b):
    x, y = map(math.radians, a); u, v = map(math.radians, b)
    return math.atan2(math.sin(u-x)*math.cos(v), math.cos(y)*math.sin(v)-math.sin(y)*math.cos(v)*math.cos(u-x))


def distancia_segmento(p, a, b):
    """Menor distância ao arco finito, incluindo as duas pontas arredondadas."""
    p, a, b = ponto(p), ponto(a), ponto(b)
    ab = angular(a, b)
    if math.pi-ab < 1e-7:
        raise ValueError('Origem e destino antipodais não definem uma faixa única.')
    if ab < 1e-12:
        return angular(a, p)*RAIO_TERRA_KM
    ap = angular(a, p); diferenca = rumo(a, p)-rumo(a, b)
    ao_longo = math.atan2(math.sin(ap)*math.cos(diferenca), math.cos(ap))
    if ao_longo < 0 or ao_longo > ab:
        return min(angular(a, p), angular(b, p))*RAIO_TERRA_KM
    transversal = math.asin(max(-1, min(1, math.sin(ap)*math.sin(diferenca))))
    return abs(transversal)*RAIO_TERRA_KM


def raio(valor):
    r = float(str(valor).replace(',', '.'))
    if not math.isfinite(r) or not 0 < r <= 200:
        raise ValueError('O raio da faixa deve ser maior que zero e de até 200 km.')
    return r


def coordenadas_form(dados, prefixo=''):
    lat = str(dados.get(prefixo+'latitude', '') or '').strip()
    lon = str(dados.get(prefixo+'longitude', '') or '').strip()
    if not lat and not lon:
        return None, None
    if not lat or not lon:
        raise ValueError('Informe latitude e longitude juntas, ou deixe ambas em branco.')
    lon, lat = ponto([lon.replace(',', '.'), lat.replace(',', '.')])
    return lat, lon


def municipio_texto(texto, uf, base):
    if not base or not texto:
        return None
    nome = texto.strip(); estado = (uf or '').strip().upper()
    encontrado = re.fullmatch(r'(.+?)\s*[/,]\s*([A-Za-z]{2})(?:\s*\([^)]*\))?\s*', nome)
    if encontrado:
        if estado and estado != encontrado[2].upper():
            return None
        nome, estado = encontrado[1].strip(), encontrado[2].upper()
    if estado:
        return municipios.buscar(base, nome, estado)
    # Apenas correspondência exata e não ambígua. Não adivinhar nomes de terminais.
    candidatos = base.get('indice_nomes', {}).get(municipios.normalizar(nome))
    if candidatos is None:
        candidatos = [m for m in base['municipios'] if municipios.normalizar(m['nome']) == municipios.normalizar(nome)]
    return candidatos[0] if len(candidatos) == 1 else None


def localizar(texto, uf, lat, lon, base):
    if lat is not None or lon is not None:
        try:
            return {'ponto': ponto([lon, lat]), 'precisao': 'Coordenadas informadas'}
        except (ValueError, TypeError):
            return None
    m = municipio_texto(texto, uf, base)
    if m and m.get('centro'):
        return {'ponto': ponto(m['centro']), 'precisao': 'Centro aproximado da extensão municipal (IBGE)',
                'municipio': m['nome']+'/'+m['uf']}
    return None


def dados_rotograma(r, base, raio_padrao=30):
    if not r.faixa_ativa:
        return {'ativa': False, 'erro': None}
    a = localizar(r.origem, r.origem_uf, r.origem_latitude, r.origem_longitude, base)
    b = localizar(r.destino, r.destino_uf, r.destino_latitude, r.destino_longitude, base)
    try:
        largura = raio(r.faixa_raio_km if r.faixa_raio_km is not None else raio_padrao)
        if not a or not b:
            return {'ativa': True, 'erro': 'Informe origem e destino como municípios reconhecidos/UF ou suas coordenadas.'}
        distancia_segmento(a['ponto'], a['ponto'], b['ponto'])
    except (ValueError, TypeError) as exc:
        return {'ativa': True, 'erro': str(exc)}
    return {'ativa': True, 'erro': None, 'origem': a, 'destino': b, 'raio_km': largura}


def comparar(c, r, base, raio_padrao=30):
    d = dados_rotograma(r, base, raio_padrao)
    if not d['ativa'] or d['erro']:
        return None
    local = localizar(c.cidade, c.estado, c.latitude, c.longitude, base)
    if not local:
        return None
    distancia = distancia_segmento(local['ponto'], d['origem']['ponto'], d['destino']['ponto'])
    if distancia > d['raio_km']+1e-8:
        return None
    contexto = [local['ponto'], d['origem'], d['destino'], d['raio_km'], 'capsula-esferica-v1']
    return {'distancia_km': round(distancia, 6), 'raio_km': d['raio_km'], 'ponto_cerca': local,
            'origem': d['origem'], 'destino': d['destino'],
            'contexto': hashlib.sha256(json.dumps(contexto, sort_keys=True).encode()).hexdigest()}


def diagrama(d):
    """Esquema da cápsula em eixo local; não é mapa nem desenho de estradas."""
    if not d['ativa'] or d['erro']:
        return None
    comprimento = angular(d['origem']['ponto'], d['destino']['ponto'])*RAIO_TERRA_KM
    escala = min(520/max(comprimento+2*d['raio_km'], 1), 78/d['raio_km'])
    return {'raio': round(d['raio_km']*escala, 3), 'comprimento': round(comprimento*escala, 3),
            'inicio': round((760-comprimento*escala)/2, 3), 'fim': round((760+comprimento*escala)/2, 3)}
