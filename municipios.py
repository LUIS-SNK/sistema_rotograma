"""Base municipal local derivada das APIs públicas do IBGE, sem chave."""
import gzip
import hashlib
import json
import unicodedata
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

ARQUIVO = Path(__file__).parent / 'dados' / 'municipios_ibge.json.gz'
URL_LOCALIDADES = 'https://servicodados.ibge.gov.br/api/v1/localidades/municipios'
URL_MALHA = 'https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?formato=application/json&intrarregiao=municipio&qualidade=maxima'


def normalizar(texto):
    return ''.join(c for c in unicodedata.normalize('NFKD', ' '.join((texto or '').split()).casefold()) if not unicodedata.combining(c))


def gerar_base(localidades, topologia):
    if topologia.get('type') != 'Topology':
        raise ValueError('A malha recebida não contém topologia municipal.')
    municipios = {}
    for m in localidades:
        regiao = m.get('regiao-imediata') or {}
        uf = (regiao.get('regiao-intermediaria') or {}).get('UF') or (((m.get('microrregiao') or {}).get('mesorregiao') or {}).get('UF'))
        if not uf or not uf.get('sigla'):
            raise ValueError('Município sem UF na resposta do IBGE.')
        codigo = str(m['id'])
        if codigo in municipios:
            raise ValueError('Identificador municipal duplicado.')
        municipios[codigo] = {'codigo': codigo, 'nome': m['nome'], 'uf': uf['sigla'], 'vizinhos': [], 'malha': False}
    donos = defaultdict(set)
    limites_arcos = {}

    def limites(arco):
        if arco not in limites_arcos:
            x = y = 0; pontos = []; transformacao = topologia.get('transform')
            for par in topologia['arcs'][arco]:
                if transformacao:
                    x += par[0]; y += par[1]
                    pontos.append((x*transformacao['scale'][0]+transformacao['translate'][0], y*transformacao['scale'][1]+transformacao['translate'][1]))
                else:
                    pontos.append(par[:2])
            if pontos:
                limites_arcos[arco] = [min(p[0] for p in pontos), min(p[1] for p in pontos), max(p[0] for p in pontos), max(p[1] for p in pontos)]
            else:
                limites_arcos[arco] = None
        return limites_arcos[arco]

    def indices(lista):
        for x in lista:
            if isinstance(x, list):
                yield from indices(x)
            elif isinstance(x, int):
                yield x if x >= 0 else ~x

    for objeto in topologia.get('objects', {}).values():
        for geometria in objeto.get('geometries', []):
            codigo = str(geometria.get('properties', {}).get('codarea', ''))
            if codigo not in municipios:
                continue
            municipios[codigo]['malha'] = True
            caixas = []
            for arco in set(indices(geometria.get('arcs', []))):
                if arco < 0 or arco >= len(topologia['arcs']):
                    raise ValueError('Índice de divisa inválido na topologia.')
                # Apenas segmentos com extensão; contato isolado por um ponto não é divisa.
                linha = topologia['arcs'][arco]
                caixa = limites(arco)
                if caixa:
                    caixas.append(caixa)
                if len(linha) > 1 and any(p[0] != 0 or p[1] != 0 for p in linha[1:]):
                    donos[arco].add(codigo)
            if caixas:
                municipios[codigo]['centro'] = [round((min(c[0] for c in caixas)+max(c[2] for c in caixas))/2, 7),
                    round((min(c[1] for c in caixas)+max(c[3] for c in caixas))/2, 7)]
    vizinhos = defaultdict(set)
    for codigos in donos.values():
        if len(codigos) > 2:
            # Simplificações podem sobrepor um arco de três áreas. Não inferir
            # vizinhança nesse caso; sinalizar a cobertura para revisão.
            for codigo in codigos:
                municipios[codigo]['revisar_divisas'] = True
            continue
        if len(codigos) == 2:
            a, b = sorted(codigos)
            vizinhos[a].add(b); vizinhos[b].add(a)
    for codigo, item in municipios.items():
        item['vizinhos'] = sorted(vizinhos[codigo])
    return {'formato': 1, 'fonte': 'IBGE — APIs de Localidades e Malhas v3 (simplificada)',
            'obtida_em': datetime.now(timezone.utc).isoformat(),
            'urls': [URL_LOCALIDADES, URL_MALHA],
            'criterio': 'segmento de divisa compartilhado na topologia; não é distância rodoviária',
            'municipios': sorted(municipios.values(), key=lambda x: x['codigo'])}


def validar_base(base):
    if base.get('formato') != 1 or not isinstance(base.get('municipios'), list):
        raise ValueError('Formato de base municipal inválido.')
    itens = base['municipios']; por_codigo = {x['codigo']: x for x in itens}
    if not itens or len(itens) != len(por_codigo):
        raise ValueError('Base municipal vazia ou com códigos duplicados.')
    chaves = set()
    for m in itens:
        chave = (normalizar(m['nome']), m['uf'])
        if chave in chaves or not m['codigo'].isdigit() or len(m['codigo']) != 7:
            raise ValueError('Identificação municipal ambígua ou inválida.')
        chaves.add(chave)
        if m.get('centro'):
            import math
            lon, lat = m['centro']
            if not all(math.isfinite(v) for v in (lon, lat)) or not -180 <= lon <= 180 or not -90 <= lat <= 90:
                raise ValueError('Centro municipal inválido.')
        for v in m['vizinhos']:
            if v == m['codigo'] or v not in por_codigo or m['codigo'] not in por_codigo[v]['vizinhos']:
                raise ValueError('Divisa municipal inconsistente.')
    return base


@lru_cache(maxsize=4)
def _carregar(caminho, tamanho, modificado):
    dados = Path(caminho).read_bytes()
    if dados[:2] == b'\x1f\x8b':
        dados = gzip.decompress(dados)
    base = validar_base(json.loads(dados))
    base['versao'] = hashlib.sha256(dados).hexdigest()
    base['indice'] = {(normalizar(m['nome']), m['uf']): m for m in base['municipios']}
    nomes = defaultdict(list)
    for m in base['municipios']:
        nomes[normalizar(m['nome'])].append(m)
    base['indice_nomes'] = dict(nomes)
    return base


def carregar(arquivo=None):
    p = Path(arquivo) if arquivo else ARQUIVO
    st = p.stat()
    return _carregar(str(p.resolve()), st.st_size, st.st_mtime_ns)


def buscar(base, cidade, uf):
    return base['indice'].get((normalizar(cidade), (uf or '').strip().upper()))


def baixar(url):
    requisicao = urllib.request.Request(url, headers={'Accept-Encoding': 'gzip', 'User-Agent': 'Rotogramas-Municipios/1.0'})
    with urllib.request.urlopen(requisicao, timeout=45) as resposta:
        dados = resposta.read(80000001)
    if len(dados) > 80000000:
        raise ValueError('Resposta do IBGE excedeu o tamanho permitido.')
    if dados[:2] == b'\x1f\x8b':
        dados = gzip.decompress(dados)
    return json.loads(dados)


def atualizar(arquivo=None):
    # Publicação atômica: erro de rede ou validação preserva a base anterior.
    base = validar_base(gerar_base(baixar(URL_LOCALIDADES), baixar(URL_MALHA)))
    if len(base['municipios']) < 5000 or sum(bool(m['vizinhos']) for m in base['municipios']) < 4500:
        raise ValueError('Resposta municipal incompleta. A base anterior foi preservada.')
    p = Path(arquivo) if arquivo else ARQUIVO
    p.parent.mkdir(parents=True, exist_ok=True)
    temporario = p.with_suffix('.tmp')
    dados = json.dumps(base, ensure_ascii=False, separators=(',', ':')).encode('utf8')
    temporario.write_bytes(gzip.compress(dados, mtime=0) if p.suffix == '.gz' else dados)
    temporario.replace(p); _carregar.cache_clear()
    return base
