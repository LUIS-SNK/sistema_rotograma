"""Cliente ORS sem persistência de credenciais e distância geodésica aproximada."""
import math
import json
import unicodedata
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError

class ErroORS(Exception):
    def __init__(self, mensagem, codigo=None, espera=60):
        super().__init__(mensagem)
        self.codigo=codigo
        self.espera=espera

RAIO_TERRA=6371008.8

def validar_ponto(p):
    if not isinstance(p,(list,tuple)) or len(p)!=2:
        raise ValueError('Coordenadas devem estar na ordem longitude latitude')
    lon,lat=map(float,p)
    if not math.isfinite(lon) or not math.isfinite(lat) or not -180<=lon<=180 or not -90<=lat<=90:
        raise ValueError('Coordenadas invalidas')
    return lon,lat

def angular(a,b):
    lon1,lat1=map(math.radians,validar_ponto(a));lon2,lat2=map(math.radians,validar_ponto(b))
    h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2*math.asin(math.sqrt(min(1,max(0,h))))

def rumo(a,b):
    x1,y1=map(math.radians,validar_ponto(a));x2,y2=map(math.radians,validar_ponto(b))
    return math.atan2(math.sin(x2-x1)*math.cos(y2),math.cos(y1)*math.sin(y2)-math.sin(y1)*math.cos(y2)*math.cos(x2-x1))

def distancia_segmento(p,a,b):
    d12=angular(a,b);d13=angular(a,p)
    if d12<1e-12:return RAIO_TERRA*d13
    diferenca=rumo(a,p)-rumo(a,b)
    along=math.atan2(math.sin(d13)*math.cos(diferenca),math.cos(d13))
    if not 0<=along<=d12:return RAIO_TERRA*min(angular(a,p),angular(b,p))
    cross=math.asin(max(-1,min(1,math.sin(d13)*math.sin(diferenca))))
    return abs(cross)*RAIO_TERRA

def distancia_trajeto(p,linha):
    if len(linha)<2:raise ValueError('Trajeto sem segmentos')
    return min(distancia_segmento(p,a,b) for a,b in zip(linha,linha[1:]))

def proximo(p,linha,raio):
    if raio<=0:raise ValueError('Margem deve ser positiva')
    return distancia_trajeto(p,linha)<=raio


def normalizar(valor):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD",str(valor).casefold()) if not unicodedata.combining(c)).split())

class SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class ClienteORS:
    def __init__(self, chave, reservar, registrar_headers):
        self.chave=chave
        self.reservar=reservar
        self.registrar_headers=registrar_headers

    def consultar(self, endpoint, caminho, params=None, corpo=None):
        self.reservar(endpoint)
        parametros=dict(params or {})
        if endpoint=="geocode":parametros["api_key"]=self.chave
        url="https://api.openrouteservice.org"+caminho
        if parametros:url+="?"+urlencode(parametros)
        pedido=Request(url,data=json.dumps(corpo).encode() if corpo else None,
                       headers={"Authorization":self.chave,"Content-Type":"application/json","User-Agent":"Rotogramas/2.1"})
        try:
            with build_opener(SemRedirecionamento()).open(pedido,timeout=15) as resposta:
                self.registrar_headers(endpoint,resposta.headers)
                dados=json.loads(resposta.read(12_000_000))
                if not isinstance(dados,dict):raise ValueError()
                return dados
        except HTTPError as exc:
            self.registrar_headers(endpoint,exc.headers)
            if exc.code in (401,403):raise ErroORS("A API recusou a consulta. Confira chave, permissões e cota no painel ORS.",exc.code,3600) from None
            if exc.code==429:raise ErroORS("Cota momentaneamente indisponível. A fila tentará novamente.",429,120) from None
            if exc.code in (400,404,422):raise ErroORS("A API não conseguiu localizar os pontos ou calcular o trajeto. Revise as localizações.",exc.code,3600) from None
            raise ErroORS("Serviço ORS temporariamente indisponível.",exc.code,60) from None
        except (URLError,TimeoutError,OSError):raise ErroORS("Falha de conexão com ORS. O cadastro foi preservado.",None,60) from None
        except (ValueError,KeyError,TypeError):raise ErroORS("Resposta ORS inesperada. A análise continua pendente.",None,120) from None

    def geocodificar(self, consulta, uf=""):
        dados=self.consultar("geocode","/geocode/search",{"text":consulta+(" "+uf if uf else "")+", Brasil","boundary.country":"BRA","size":5})
        candidatos=[];vistos=set()
        for item in dados.get("features",[]):
            try:
                props=item["properties"]
                if props.get("country_a")!="BRA":continue
                coord=validar_ponto(item["geometry"]["coordinates"])
                chave=tuple(round(c,5) for c in coord)
                if chave in vistos:continue
                vistos.add(chave)
                candidatos.append({"rotulo":str(props.get("label") or props.get("name") or consulta)[:500],
                                   "coordenadas":list(coord),"uf":str(props.get("region_a") or ""),
                                   "regiao":str(props.get("region") or ""),"tipo":str(props.get("layer") or "localidade"),
                                   "confianca":float(props.get("confidence") or 0)})
            except (KeyError,TypeError,ValueError,OverflowError):continue
        return candidatos

    def trajeto(self, origem, destino):
        dados=self.consultar("directions","/v2/directions/driving-hgv/geojson",corpo={"coordinates":[origem,destino],"instructions":False})
        try:
            geometria=dados["features"][0]["geometry"]
            if geometria["type"]!="LineString" or len(geometria["coordinates"])<2:raise ValueError()
            linha=[list(validar_ponto(p)) for p in geometria["coordinates"]]
            return {"linha":linha,"credito":"© openrouteservice by HeiGIT | © OpenStreetMap contributors"}
        except (KeyError,TypeError,ValueError,IndexError):raise ErroORS("A API retornou um trajeto sem geometria válida.",None,120) from None
