"""Cápsula direta, sem APIs de estrada e sem uso do banco real."""
import os
os.environ['DATABASE_URL']='sqlite:///:memory:'
os.environ['DESATIVAR_VERIFICADOR']='1'
import math,re,unittest
from unittest.mock import patch
import app as S
import faixa_geografica as F
import sugestoes_municipais as G
import municipios as M

class Geometria(unittest.TestCase):
 def test_lateral_dentro(self):self.assertAlmostEqual(F.distancia_segmento([5,.1],[0,0],[10,0]),11.119508,places=5)
 def test_lateral_fora(self):self.assertGreater(F.distancia_segmento([5,.4],[0,0],[10,0]),30)
 def test_ponta_antes_origem(self):self.assertLess(F.distancia_segmento([-.1,0],[0,0],[10,0]),30)
 def test_ponta_depois_destino(self):self.assertLess(F.distancia_segmento([10.1,0],[0,0],[10,0]),30)
 def test_canto_fora_da_ponta_redonda(self):self.assertGreater(F.distancia_segmento([-.2,.2],[0,0],[10,0]),30)
 def test_nao_estende_linha_ao_infinito(self):self.assertGreater(F.distancia_segmento([20,0],[0,0],[10,0]),1000)
 def test_origem_destino_coincidentes(self):self.assertLess(F.distancia_segmento([.1,.1],[0,0],[0,0]),30)
 def test_antimeridiano(self):self.assertLess(F.distancia_segmento([180,.1],[179,0],[-179,0]),30)
 def test_antipodas_rejeitadas(self):
  with self.assertRaises(ValueError):F.distancia_segmento([10,0],[0,0],[180,0])
 def test_limite_da_faixa(self):self.assertAlmostEqual(F.distancia_segmento([5,math.degrees(30/F.RAIO_TERRA_KM)],[0,0],[10,0]),30,places=7)
 def test_coordenadas_invalidas(self):
  for p in [[0,float('nan')],[0,91],[181,0],[None,0]]:
   with self.subTest(p=p):
    with self.assertRaises((ValueError,TypeError)):F.ponto(p)
 def test_raio_invalido(self):
  for r in [0,-1,201,'nan','inf']:
   with self.subTest(r=r):
    with self.assertRaises(ValueError):F.raio(r)
 def test_municipio_com_uf_e_terminal(self):
  b=M.carregar();self.assertEqual(F.municipio_texto('GUARIBA/SP (BONFIM)','',b)['nome'],'Guariba')
  self.assertIsNone(F.municipio_texto('GUARIBA/SP (BONFIM)','GO',b))
  self.assertIsNone(F.municipio_texto('Terminal sem municipio','',b))
 def test_centros_municipais_presentes(self):
  b=M.carregar();self.assertEqual(sum(bool(m.get('centro')) for m in b['municipios']),5570)
  self.assertIsNotNone(F.localizar('Araras','SP',None,None,b))

class IntegracaoFaixa(unittest.TestCase):
 def setUp(self):
  self.ctx=S.app.app_context();self.ctx.push();S.app.config.update(TESTING=True,FAIXA_RAIO_KM=30)
  S.app.config.pop('MUNICIPIOS_ARQUIVO',None)
  S.db.session.remove();S.db.drop_all();S.db.create_all();self.c=S.app.test_client()
 def tearDown(self):
  S.db.session.remove();S.app.config.pop('MUNICIPIOS_ARQUIVO',None);self.ctx.pop()
 def rota(self,nome='Sem cercas vinculadas',**extras):
  dados=dict(nome=nome,origem='Origem de teste',destino='Destino de teste',ativo=True,faixa_ativa=True,
   origem_latitude=0,origem_longitude=0,destino_latitude=0,destino_longitude=10,faixa_raio_km=30)
  dados.update(extras);r=S.Rotograma(**dados);S.db.session.add(r);S.db.session.commit();return r
 def cerca(self,lat=.1,lon=5,nome='Nova cerca'):
  c=S.Cerca(nome=nome,cidade='Santos',estado='SP',tipo='Via',ativo=True,latitude=lat,longitude=lon)
  S.db.session.add(c);S.db.session.commit();return c
 def decidir(self,a,**extras):
  self.c.get('/notificacoes')
  with self.c.session_transaction() as sess:token=sess['_municipal_csrf']
  dados=dict(token_municipal=token,versao=a.versao,cerca_versao=a.cerca.versao,rotograma_versao=a.rotograma.versao,
   confirmar='sim',responsavel='Teste da faixa',justificativa='Revisão manual',decisao='vincular')
  dados.update(extras);return self.c.post(f'/notificacoes/{a.pendencia_id}/decidir',data=dados)
 def test_sem_cerca_previa_gera_sugestao(self):
  r=self.rota();c=self.cerca();a=G.Sugestao.query.one()
  self.assertEqual(a.motivo['tipo'],'faixa');self.assertEqual(a.rotograma_id,r.id)
  self.assertEqual(S.RotogramaCerca.query.count(),0);self.assertLess(a.motivo['faixa']['distancia_km'],30)
 def test_cerca_fora_nao_sugere(self):
  self.rota();self.cerca(lat=.4);self.assertEqual(G.Sugestao.query.count(),0)
 def test_sugere_nas_pontas(self):
  self.rota();self.cerca(lat=0,lon=-.1);self.assertEqual(G.Sugestao.query.count(),1)
 def test_raio_e_pontas_respeitados(self):
  self.rota();self.cerca(lat=.2,lon=-.2);self.assertEqual(G.Sugestao.query.count(),0)
 def test_varios_rotogramas_uma_notificacao(self):
  self.rota();self.rota('Segunda rota');c=self.cerca()
  self.assertEqual(G.Sugestao.query.count(),2);self.assertEqual(len(G.alertas()),1)
  self.assertEqual(G.alertas()[0]['quantidade'],2)
 def test_municipio_e_faixa_nao_duplicam(self):
  ref=self.cerca(nome='Referência');r=self.rota();S.db.session.add(S.RotogramaCerca(cerca_id=ref.id,rotograma_id=r.id));S.db.session.commit()
  c=self.cerca(nome='Outra cerca');a=G.Sugestao.query.filter_by(cerca_id=c.id).one()
  self.assertEqual(a.motivo['tipo'],'mesmo');self.assertIn('faixa',a.motivo)
 def test_somente_municipios_sem_coordenadas_manualmente(self):
  r=self.rota(origem='Santos',origem_uf='SP',destino='Goiânia',destino_uf='GO',origem_latitude=None,origem_longitude=None,
   destino_latitude=None,destino_longitude=None,faixa_raio_km=40)
  c=S.Cerca(nome='Araras',cidade='Araras',estado='SP',ativo=True);S.db.session.add(c);S.db.session.commit()
  a=G.Sugestao.query.filter_by(cerca_id=c.id).one();self.assertEqual(a.motivo['tipo'],'faixa')
  self.assertIn('aproximado',a.motivo['faixa']['ponto_cerca']['precisao'])
 def test_manual_tem_prioridade_sobre_cidade(self):
  self.rota();c=self.cerca();a=G.Sugestao.query.one()
  self.assertEqual(a.motivo['faixa']['ponto_cerca']['ponto'],[5,.1])
 def test_coordenadas_manuais_funcionam_sem_base(self):
  S.app.config['MUNICIPIOS_ARQUIVO']='inexistente';self.rota();self.cerca()
  self.assertEqual(G.Sugestao.query.one().motivo['tipo'],'faixa')
 def test_origem_nao_identificada_nao_bloqueia(self):
  self.rota(origem_latitude=None,origem_longitude=None);self.cerca()
  self.assertEqual(G.Sugestao.query.count(),0)
  self.assertIn('Faixas com localização incompleta',self.c.get('/notificacoes').text)
 def test_faixa_desativada_nao_sugere(self):
  self.rota(faixa_ativa=False);self.cerca();self.assertEqual(G.Sugestao.query.count(),0)
 def test_mudar_raio_invalida_pendente(self):
  r=self.rota();self.cerca();a=G.Sugestao.query.one();r.faixa_raio_km=5;S.db.session.commit()
  self.assertEqual(a.decisao,'cancelada');self.assertEqual(a.pendencia.status,'concluida')
 def test_nao_reabre_dispensa_sem_mudanca(self):
  self.rota();c=self.cerca();a=G.Sugestao.query.one();self.assertEqual(self.decidir(a,decisao='dispensar').status_code,302)
  G.gerar(c,G.obter_base());S.db.session.commit();self.assertEqual(a.decisao,'dispensada')
 def test_mudar_faixa_reabre_com_historico(self):
  r=self.rota();self.cerca();a=G.Sugestao.query.one();self.decidir(a,decisao='dispensar');p=a.pendencia_id
  r.faixa_raio_km=40;S.db.session.commit();self.assertIsNone(a.decisao);self.assertNotEqual(a.pendencia_id,p)
  self.assertEqual(S.db.session.get(S.Pendencia,p).status,'concluida')
 def test_decisao_manual_de_faixa_sem_referencia(self):
  r=self.rota();c=self.cerca();a=G.Sugestao.query.one();self.assertEqual(self.decidir(a).status_code,302)
  self.assertEqual(S.RotogramaCerca.query.count(),1);self.assertEqual(a.decisao,'vinculada')
 def test_formulario_invalido_nao_salva(self):
  for extras in [{'latitude':'0','longitude':''},{'latitude':'nan','longitude':'0'},{'latitude':'91','longitude':'0'}]:
   d=dict(nome='Inválida',cidade='Santos',estado='SP',ativo='on');d.update(extras)
   self.assertEqual(self.c.post('/cercas/nova',data=d).status_code,400)
  self.assertEqual(S.Cerca.query.count(),0)
 def test_post_gera_com_coordenadas(self):
  self.rota();res=self.c.post('/cercas/nova',data=dict(nome='Pelo formulário',cidade='Santos',estado='SP',latitude='0,1',longitude='5',ativo='on'))
  self.assertEqual(res.status_code,302);self.assertEqual(G.Sugestao.query.count(),1)
 def test_campos_do_rotograma_e_previa(self):
  r=self.rota()
  for url in ['/rotogramas/novo',f'/rotogramas/{r.id}/editar',f'/rotogramas/{r.id}','/notificacoes']:
   res=self.c.get(url);self.assertEqual(res.status_code,200,res.text)
  self.assertIn('pontas arredondadas',self.c.get(f'/rotogramas/{r.id}').text)
 def test_nao_chama_api_para_comparar(self):
  with patch('municipios.baixar',side_effect=AssertionError('Sem chamadas de rede no cadastro')):
   self.rota();self.cerca();self.assertEqual(G.Sugestao.query.count(),1)

if __name__=='__main__':unittest.main()
