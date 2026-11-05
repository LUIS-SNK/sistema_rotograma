"""Integração com API simulada, banco em memória e geometria por segmentos."""
import os
os.environ['DATABASE_URL']='sqlite:///:memory:'
os.environ['DESATIVAR_VERIFICADOR']='1'
import unittest
from unittest.mock import patch
from urllib.error import URLError
import app as S
import rotas as R
import faixa_geografica as F
import sugestoes_municipais as G

class Rotas(unittest.TestCase):
    def setUp(self):
        self.ctx=S.app.app_context();self.ctx.push()
        S.app.config.update(TESTING=True,ROTAS_ENABLED=True,ORS_API_KEY='chave-apenas-teste',ROTAS_LIMITE_DIA=500,ROTAS_LIMITE_MINUTO=10)
        S.db.session.remove();S.db.drop_all();S.db.create_all();self.c=S.app.test_client()
        self.c.get('/rotogramas/novo')
        with self.c.session_transaction() as sess:self.csrf=sess['_municipal_csrf']
        self.dados=dict(origem='Santos',destino='Goiânia',origem_uf='SP',destino_uf='GO',origem_latitude='0',origem_longitude='0',destino_latitude='0',destino_longitude='2',intermediarios=[[1,1]],perfil='driving-hgv')
        self.resultado=dict(caminho=[[0,0],[1,1],[2,0]],indices=[0,1,2],distancia_km=314)
    def tearDown(self):
        S.db.session.remove();self.ctx.pop()
    def calcular(self,dados=None):
        with patch.object(R,'consultar',return_value=self.resultado) as mock:
            res=self.c.post('/api/rotas/calcular',json=dados or self.dados,headers={'X-CSRF-Token':self.csrf})
        return res,mock
    def form(self,res,**extra):
        d={k:v for k,v in self.dados.items() if k not in ('intermediarios','perfil')}
        d.update(nome='Rota aprovada',ativo='on',data_referencia='2026-11-05',faixa_ativa='on',faixa_raio_km='2',rota_modo='estradas',rota_token=res.json['token'])
        d.update(extra);return d
    def rota(self):
        res,_=self.calcular();self.assertEqual(res.status_code,200,res.text)
        saved=self.c.post('/rotogramas/novo',data=self.form(res));self.assertEqual(saved.status_code,302,saved.text)
        return S.Rotograma.query.one()
    def cerca(self,lon,lat,nome='Nova cerca'):
        c=S.Cerca(nome=nome,cidade='Santos',estado='SP',ativo=True,longitude=lon,latitude=lat)
        S.db.session.add(c);S.db.session.commit();return c
    def test_csrf_obrigatorio(self):
        with patch.object(R,'consultar') as mock:
            self.assertEqual(self.c.post('/api/rotas/calcular',json=self.dados).status_code,400);mock.assert_not_called()
    def test_cache_evitar_nova_consulta(self):
        a,mock=self.calcular();self.assertEqual(a.status_code,200);mock.assert_called_once()
        b,mock=self.calcular();self.assertEqual(b.status_code,200);mock.assert_not_called()
        self.assertEqual(R.Cache.query.count(),1)
    def test_sem_chave(self):
        S.app.config['ORS_API_KEY']=''
        a,mock=self.calcular();self.assertEqual(a.status_code,503);mock.assert_not_called()
    def test_falha_api_nao_grava_rota(self):
        with patch.object(R,'consultar',side_effect=URLError('indisponível')):
            res=self.c.post('/api/rotas/calcular',json=self.dados,headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(res.status_code,503);self.assertEqual(S.Rotograma.query.count(),0)
        self.assertEqual(R.Cache.query.count(),0)
    def test_perfil_invalido(self):
        res,mock=self.calcular(dict(self.dados,perfil='url-arbitraria'))
        self.assertEqual(res.status_code,400);mock.assert_not_called()
    def test_limite_passagens(self):
        res,mock=self.calcular(dict(self.dados,intermediarios=[[1,1]]*49))
        self.assertEqual(res.status_code,400);mock.assert_not_called()
    def test_limite_consultas_persistente(self):
        S.app.config['ROTAS_LIMITE_MINUTO']=1
        self.assertEqual(self.calcular()[0].status_code,200)
        res,mock=self.calcular(dict(self.dados,intermediarios=[[1,1.1]]))
        self.assertEqual(res.status_code,429);mock.assert_not_called()
    def test_cadastra_com_percurso_e_historico(self):
        r=self.rota();S.db.session.expire_all()
        self.assertTrue(r.rota_por_estradas);self.assertEqual(r.rota_dados['caminho'],self.resultado['caminho'])
        self.assertIsNotNone(S.HistoricoAlteracao.query.filter_by(campo='rota_dados').first())
        self.assertEqual(self.c.get(f'/rotogramas/{r.id}').status_code,200)
        self.assertIn('Percurso',self.c.get(f'/rotogramas/{r.id}/editar').text)
    def test_token_adulterado_nao_salva(self):
        res,_=self.calcular();form=self.form(res);form['rota_token']+='x'
        self.assertEqual(self.c.post('/rotogramas/novo',data=form).status_code,400)
        self.assertEqual(S.Rotograma.query.count(),0)
    def test_alterar_extremo_exige_recalculo(self):
        res,_=self.calcular()
        self.assertEqual(self.c.post('/rotogramas/novo',data=self.form(res,destino='Outra cidade')).status_code,400)
    def test_nao_usa_linha_reta_com_rota(self):
        r=self.rota();c=self.cerca(1,0)
        self.assertIsNone(F.comparar(c,r,G.obter_base()))
        self.assertEqual(G.Sugestao.query.count(),0)
    def test_cerca_perto_da_curva_sugere_sem_api(self):
        r=self.rota()
        with patch.object(R,'consultar',side_effect=AssertionError('Não chamar API no cadastro')):
            c=self.cerca(1,1.001)
        a=G.Sugestao.query.one();self.assertEqual(a.motivo['faixa']['referencia'],'rota')
        self.assertEqual(a.rotograma_id,r.id);self.assertEqual(S.RotogramaCerca.query.count(),0)
    def test_relacao_municipal_nao_fura_faixa_da_rota(self):
        r=self.rota();ref=self.cerca(1,1,'Referência')
        S.db.session.add(S.RotogramaCerca(cerca_id=ref.id,rotograma_id=r.id));S.db.session.commit()
        c=self.cerca(1,0,'Mesma cidade mas fora do caminho')
        self.assertEqual(G.Sugestao.query.filter_by(cerca_id=c.id).count(),0)
    def test_margem_reconcilia_sugestoes(self):
        r=self.rota();self.cerca(1,1.01);a=G.Sugestao.query.one()
        r.faixa_raio_km=.1;S.db.session.commit()
        self.assertEqual(a.decisao,'cancelada');self.assertEqual(a.pendencia.status,'concluida')
    def test_mudar_percurso_atualiza_sugestao(self):
        r=self.rota();self.cerca(1,1);a=G.Sugestao.query.one()
        dados=dict(r.rota_dados,caminho=[[0,0],[2,0]],hash='nova-geometria')
        r.rota_dados=dados;S.db.session.commit()
        self.assertEqual(a.decisao,'cancelada')
    def test_desativar_rota_mantem_cadastros(self):
        r=self.rota();res=self.c.post(f'/rotogramas/{r.id}/editar',data=dict(nome=r.nome,origem=r.origem,destino=r.destino,data_referencia='2026-11-05',ativo='on',versao=r.versao,rota_modo='direta',faixa_ativa='on',faixa_raio_km='2'))
        self.assertEqual(res.status_code,302,res.text);self.assertFalse(r.rota_por_estradas);self.assertIsNone(r.rota_dados)
    def test_confirmacao_realiza_vinculo(self):
        r=self.rota();c=self.cerca(1,1);a=G.Sugestao.query.one()
        res=self.c.post(f'/notificacoes/{a.pendencia_id}/decidir',data=dict(token_municipal=self.csrf,versao=a.versao,cerca_versao=c.versao,rotograma_versao=r.versao,confirmar='sim',responsavel='Teste',justificativa='Conferido no mapa',decisao='vincular'))
        self.assertEqual(res.status_code,302,res.text)
        S.db.session.expire_all();self.assertEqual(S.RotogramaCerca.query.filter_by(cerca_id=c.id,rotograma_id=r.id).count(),1)
        self.assertIn(c.nome,self.c.get(f'/rotogramas/{r.id}').text)
    def test_geometria_real_validada(self):
        import io,json
        retorno=dict(features=[dict(geometry={'type':'LineString','coordinates':self.resultado['caminho']},properties={'way_points':[0,1,2],'summary':{'distance':314000}})])
        with patch.object(R,'urlopen',return_value=io.BytesIO(json.dumps(retorno).encode())):
            d=R.consultar([[0,0],[1,1],[2,0]],'driving-hgv')
        self.assertEqual(d['distancia_km'],314)
    def test_origem_alterada_diretamente_nao_usa_rota_antiga(self):
        r=self.rota();r.origem='Alterada';S.db.session.commit()
        self.assertIsNone(R.rota_valida(r));self.assertTrue(F.dados_rotograma(r,G.obter_base())['erro'])


class LocalizacaoCidade(unittest.TestCase):
    def setUp(self):
        self.ctx=S.app.app_context();self.ctx.push();S.app.config['ORS_API_KEY']='teste'
    def tearDown(self):self.ctx.pop()
    def buscar(self,features):
        import io,json
        with patch.object(R,'urlopen',return_value=io.BytesIO(json.dumps({'features':features}).encode())):
            return R.geocodificar({'nome':'Santos','uf':'SP'})
    def feature(self,**extras):
        p=dict(name='Santos',region_a='SP',country_a='BRA',localadmin='Santos');p.update(extras)
        return dict(properties=p,geometry={'coordinates':[-46.34,-23.94]})
    def test_cidade_municipal_tem_prioridade_sobre_homonimo(self):
        local=self.buscar([self.feature(),dict(properties=dict(name='Santos',region_a='SP',country_a='BRA'),geometry={'coordinates':[-47.4,-23.6]})])
        self.assertEqual(local['ponto'],[-46.34,-23.94])
    def test_uf_incorreta_nao_aceita(self):
        with self.assertRaises(ValueError):self.buscar([self.feature(region_a='GO')])
    def test_pais_incorreto_nao_aceita(self):
        with self.assertRaises(ValueError):self.buscar([self.feature(country_a='USA')])
    def test_cidades_ambiguas_exigem_coordenadas(self):
        outro=self.feature();outro['geometry']['coordinates']=[-47,-23]
        with self.assertRaises(ValueError):self.buscar([self.feature(),outro])

if __name__=='__main__':unittest.main()
