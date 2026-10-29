"""Regras municipais com banco temporário; nenhuma API ou base real é modificada."""
import os
os.environ['DATABASE_URL']='sqlite:///:memory:'
os.environ['DESATIVAR_VERIFICADOR']='1'
import re,json,unittest,gzip
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import app as S
import sugestoes_municipais as G
import municipios as M

class Sugestoes(unittest.TestCase):
 def setUp(self):
  self.ctx=S.app.app_context();self.ctx.push();S.app.config.update(TESTING=True)
  S.app.config.pop('MUNICIPIOS_ARQUIVO',None)
  S.db.session.remove();S.db.drop_all();S.db.create_all();self.c=S.app.test_client()
 def tearDown(self):
  S.db.session.remove();S.app.config.pop('MUNICIPIOS_ARQUIVO',None);self.ctx.pop()
 def cerca(self,nome,cidade='Mogi Mirim',uf='SP',ativo=True):
  c=S.Cerca(nome=nome,cidade=cidade,estado=uf,tipo='Via',ativo=ativo)
  S.db.session.add(c);S.db.session.commit();return c
 def referencia(self,cidade='Mogi Mirim',uf='SP',ativo=True):
  c=self.cerca('Referência',cidade,uf,ativo)
  r=S.Rotograma(nome='Rota de teste',origem='A',destino='B',ativo=True)
  S.db.session.add(r);S.db.session.commit()
  S.db.session.add(S.RotogramaCerca(cerca_id=c.id,rotograma_id=r.id));S.db.session.commit()
  return r,c
 def nova(self,cidade='Mogi Guaçu',uf='SP'):
  res=self.c.post('/cercas/nova',data=dict(nome='Nova cerca',cidade=cidade,estado=uf,tipo='Via',ativo='on'))
  self.assertEqual(res.status_code,302,res.text)
  return S.Cerca.query.filter_by(nome='Nova cerca').one()
 def sugestao(self,**kw):
  r,ref=self.referencia(**kw);c=self.nova();a=G.Sugestao.query.filter_by(cerca_id=c.id,rotograma_id=r.id).one();return r,ref,c,a
 def decidir(self,a,decisao='vincular',**extras):
  pagina=self.c.get('/notificacoes');self.assertEqual(pagina.status_code,200,pagina.text)
  with self.c.session_transaction() as sess:token=sess['_municipal_csrf']
  dados=dict(token_municipal=token,versao=a.versao,cerca_versao=a.cerca.versao,rotograma_versao=a.rotograma.versao,
    confirmar='sim',responsavel='Pessoa de teste',justificativa='Conferência de teste',decisao=decisao)
  dados.update(extras);return self.c.post(f'/pendencias/{a.pendencia_id}/decidir-sugestao',data=dados)
 def test_mesmo_municipio_normaliza_acentos_e_espacos(self):
  r,ref=self.referencia(cidade='  MOGI GUAÇU ');c=self.nova(cidade='mogi guacu')
  a=G.Sugestao.query.filter_by(cerca_id=c.id).one();self.assertEqual(a.motivo['tipo'],'mesmo')
  self.assertEqual(S.RotogramaCerca.query.filter_by(cerca_id=c.id).count(),0)
 def test_divisa_real_mogi_guacu_mirim(self):
  r,ref,c,a=self.sugestao();self.assertEqual(a.motivo['tipo'],'vizinho');self.assertEqual(a.pendencia.status,'aberta')
 def test_cidade_distante_nao_sugere(self):
  self.referencia(cidade='Santos');c=self.nova();self.assertEqual(G.Sugestao.query.filter_by(cerca_id=c.id).count(),0)
  self.assertEqual(S.db.session.get(G.Fila,c.id).status,'concluida')
 def test_mesmo_nome_outra_uf_nao_equivale(self):
  self.referencia(cidade='Mogi Guaçu',uf='MG');c=self.nova();self.assertEqual(G.Sugestao.query.filter_by(cerca_id=c.id).count(),0)
 def test_referencias_duplicadas_uma_sugestao(self):
  r,ref=self.referencia();c2=self.cerca('Outra referência')
  S.db.session.add(S.RotogramaCerca(cerca_id=c2.id,rotograma_id=r.id));S.db.session.commit();c=self.nova()
  self.assertEqual(G.Sugestao.query.filter_by(cerca_id=c.id).count(),1)
 def test_inativa_nao_gera(self):
  self.referencia();c=self.cerca('Inativa','Mogi Guaçu',ativo=False)
  self.assertEqual(G.Sugestao.query.filter_by(cerca_id=c.id).count(),0)
 def test_referencia_inativa_nao_gera(self):
  self.referencia(ativo=False);c=self.nova();self.assertEqual(G.Sugestao.query.filter_by(cerca_id=c.id).count(),0)
 def test_rotograma_inativo_nao_gera(self):
  r,ref=self.referencia();r.ativo=False;S.db.session.commit();c=self.nova()
  self.assertEqual(G.Sugestao.query.filter_by(cerca_id=c.id).count(),0)
 def test_vincular_decisao_manual_historico(self):
  r,ref,c,a=self.sugestao();self.assertEqual(self.decidir(a).status_code,302)
  self.assertEqual(a.decisao,'vinculada');self.assertEqual(a.responsavel,'Pessoa de teste');self.assertIsNotNone(a.decidida_em)
  self.assertEqual(S.RotogramaCerca.query.filter_by(cerca_id=c.id,rotograma_id=r.id).count(),1)
  self.assertEqual(a.pendencia.status,'concluida')
  self.assertTrue(S.HistoricoAlteracao.query.filter_by(tipo_operacao='decisao_municipal').one().valor_novo.find('Pessoa de teste')>=0)
 def test_dispensa_nao_reabre_reprocessamento(self):
  r,ref,c,a=self.sugestao();self.assertEqual(self.decidir(a,'dispensar').status_code,302)
  qtd=S.Pendencia.query.count();G.gerar(c,G.obter_base());S.db.session.commit()
  self.assertEqual(a.decisao,'dispensada');self.assertEqual(S.Pendencia.query.count(),qtd)
  self.assertEqual(S.RotogramaCerca.query.filter_by(cerca_id=c.id).count(),0)
 def test_decisao_duplicada_rejeitada(self):
  r,ref,c,a=self.sugestao();v=a.versao;self.assertEqual(self.decidir(a,'dispensar').status_code,302)
  self.assertEqual(self.decidir(a,versao=v).status_code,409)
 def test_csrf_confirmacao_responsavel_e_versao(self):
  r,ref,c,a=self.sugestao()
  for campos,status in [({'token_municipal':''},400),({'confirmar':''},400),({'responsavel':''},400),({'cerca_versao':0},409)]:
   self.assertEqual(self.decidir(a,**campos).status_code,status,campos)
  self.assertEqual(a.pendencia.status,'aberta')
 def test_nao_conclui_pelo_botao_generico(self):
  r,ref,c,a=self.sugestao();self.assertEqual(self.c.post(f'/pendencias/{a.pendencia_id}/concluir').status_code,400)
  self.assertEqual(a.pendencia.status,'aberta')
 def test_inativacao_cancela(self):
  r,ref,c,a=self.sugestao();c.ativo=False;S.db.session.commit()
  self.assertEqual(a.decisao,'cancelada');self.assertEqual(a.pendencia.status,'concluida')
 def test_desvinculo_referencia_cancela(self):
  r,ref,c,a=self.sugestao();S.db.session.delete(S.RotogramaCerca.query.filter_by(rotograma_id=r.id,cerca_id=ref.id).one());S.db.session.commit()
  self.assertEqual(a.decisao,'cancelada')
 def test_mudanca_cidade_cancela(self):
  r,ref,c,a=self.sugestao();c.cidade='Santos';S.db.session.commit();self.assertEqual(a.decisao,'cancelada')
 def test_vinculo_manual_encerra_sugestao(self):
  r,ref,c,a=self.sugestao()
  res=self.c.post(f'/rotogramas/{r.id}/vincular-cerca',data={'cerca_id':c.id,'versao':r.versao})
  self.assertEqual(res.status_code,302);self.assertEqual(a.decisao,'ja_vinculada')
 def test_base_ausente_cadastro_e_mesma_cidade_funcionam(self):
  self.referencia(cidade='Mogi Guaçu');S.app.config['MUNICIPIOS_ARQUIVO']='arquivo-inexistente.json'
  with patch('municipios.baixar',side_effect=AssertionError('Cadastro não pode chamar API')):
   c=self.nova();self.assertEqual(G.Sugestao.query.filter_by(cerca_id=c.id).count(),1)
  self.assertEqual(S.db.session.get(G.Fila,c.id).status,'aguardando_base')
 def test_grafia_invalida_avisa_sem_bloquear(self):
  self.referencia();c=self.nova(cidade='Mogiiii');self.assertEqual(S.db.session.get(G.Fila,c.id).status,'revisar_municipio')
  self.assertIn('Mogiiii',self.c.get('/cercas').text)
 def test_base_incompleta_sinalizada(self):
  c=self.nova(cidade='Boa Esperança do Norte',uf='MT')
  self.assertEqual(S.db.session.get(G.Fila,c.id).status,'cobertura_parcial')
 def test_atualizacao_offline_preserva_base(self):
  with TemporaryDirectory() as pasta:
   p=Path(pasta)/'base.json';p.write_text('anterior')
   with patch('municipios.baixar',side_effect=TimeoutError):
    with self.assertRaises(TimeoutError):M.atualizar(p)
   self.assertEqual(p.read_text(),'anterior')
 def test_base_real_simetria_divisa_e_ufs(self):
  b=M.validar_base(json.loads(gzip.decompress(M.ARQUIVO.read_bytes())));self.assertGreater(len(b['municipios']),5500)
  b=M.carregar();a=M.buscar(b,'Mogi Guaçu','SP');z=M.buscar(b,'Mogi Mirim','SP')
  self.assertIn(z['codigo'],a['vizinhos']);self.assertIn(a['codigo'],z['vizinhos'])
  por={m['codigo']:m for m in b['municipios']}
  self.assertTrue(any(m['uf']!=por[v]['uf'] for m in b['municipios'] for v in m['vizinhos']))
 def test_perder_base_nao_cancela_sugestao_anterior(self):
  r,ref,c,a=self.sugestao();S.app.config['MUNICIPIOS_ARQUIVO']='ausente.json'
  S.db.session.commit();self.assertEqual(a.pendencia.status,'aberta')
  self.assertEqual(self.decidir(a).status_code,409)
 def test_base_retorna_sem_reabrir_dispensa(self):
  self.referencia(cidade='Mogi Guaçu');S.app.config['MUNICIPIOS_ARQUIVO']='ausente.json';c=self.nova()
  a=G.Sugestao.query.filter_by(cerca_id=c.id).one();self.assertEqual(self.decidir(a,'dispensar').status_code,302)
  S.app.config.pop('MUNICIPIOS_ARQUIVO');qtd=S.Pendencia.query.count()
  G.gerar(c,G.obter_base());S.db.session.commit();self.assertEqual(S.Pendencia.query.count(),qtd)
 def test_topologia_arco_invertido_e_contato_por_ponto(self):
  local=[{'id':codigo,'nome':nome,'microrregiao':{'mesorregiao':{'UF':{'sigla':'SP'}}}} for codigo,nome in [(1000001,'A'),(1000002,'B'),(1000003,'C')]]
  topo={'type':'Topology','arcs':[[[0,0],[1,0]],[[1,0],[0,0]]],
   'objects':{'municipios':{'geometries':[
    {'properties':{'codarea':'1000001'},'arcs':[[0]]},
    {'properties':{'codarea':'1000002'},'arcs':[[-1]]},
    {'properties':{'codarea':'1000003'},'arcs':[[1]]}]}}}
  b=M.validar_base(M.gerar_base(local,topo));m={x['codigo']:x for x in b['municipios']}
  self.assertEqual(m['1000001']['vizinhos'],['1000002']);self.assertEqual(m['1000003']['vizinhos'],[])
 def test_topologia_ambigua_nao_inventa_divisas(self):
  local=[{'id':codigo,'nome':str(codigo),'microrregiao':{'mesorregiao':{'UF':{'sigla':'SP'}}}} for codigo in [1000001,1000002,1000003]]
  topo={'type':'Topology','arcs':[[[0,0],[1,0]]],'objects':{'m':{'geometries':[{'properties':{'codarea':str(x['id'])},'arcs':[[0]]} for x in local]}}}
  b=M.gerar_base(local,topo)
  self.assertTrue(all(x['revisar_divisas'] and not x['vizinhos'] for x in b['municipios']))
 def test_referencia_substituida_atualiza_sugestao(self):
  r,ref,c,a=self.sugestao();antiga=a.versao
  outra=self.cerca('Nova referência válida','Mogi Guaçu')
  S.db.session.add(S.RotogramaCerca(cerca_id=outra.id,rotograma_id=r.id))
  S.db.session.delete(S.RotogramaCerca.query.filter_by(cerca_id=ref.id,rotograma_id=r.id).one());S.db.session.commit()
  self.assertEqual(a.motivo['referencia_id'],outra.id);self.assertGreater(a.versao,antiga)
  self.assertEqual(a.pendencia.status,'aberta')
 def duas_rotas(self):
  r1,ref=self.referencia(cidade='Mogi Guaçu')
  outra=self.cerca('Referência em município vizinho','Mogi Mirim')
  r2=S.Rotograma(nome='Segundo rotograma sugerido',ativo=True)
  S.db.session.add(r2);S.db.session.commit()
  S.db.session.add(S.RotogramaCerca(rotograma_id=r2.id,cerca_id=outra.id));S.db.session.commit()
  c=self.nova();return c,r1,r2
 def test_notificacao_agrupa_rotogramas_por_cerca(self):
  c,r1,r2=self.duas_rotas()
  pagina=self.c.get(f'/notificacoes?cerca_id={c.id}')
  self.assertEqual(pagina.status_code,200);self.assertEqual(pagina.text.count(f'id="cerca-{c.id}"'),1)
  self.assertIn(r1.nome,pagina.text);self.assertIn(r2.nome,pagina.text)
  self.assertIn('Mesma cidade',pagina.text);self.assertIn('Município vizinho (divisa)',pagina.text)
  self.assertEqual(S.RotogramaCerca.query.filter_by(cerca_id=c.id).count(),0)
 def test_alerta_unico_por_cerca_com_quantidade(self):
  c,r1,r2=self.duas_rotas()
  alertas=[a for a in S.coletar_alertas() if a.get('categoria')=='nova_cerca' and a['item'].id==c.id]
  self.assertEqual(len(alertas),1);self.assertIn('2 rotograma(s)',alertas[0]['mensagem'])
  self.assertIn('Ver notificações',self.c.get('/').text)
 def test_sugestoes_fora_das_pendencias_cadastrais(self):
  c,r1,r2=self.duas_rotas();pagina=self.c.get('/pendencias')
  self.assertNotIn('analisar nova cerca',pagina.text)
  self.assertNotIn('decidir-sugestao',pagina.text)
  self.assertIn('Notificações',pagina.text)
 def test_decisao_parcial_mantem_alerta_ate_todas_concluidas(self):
  c,r1,r2=self.duas_rotas()
  a1=G.Sugestao.query.filter_by(cerca_id=c.id,rotograma_id=r1.id).one()
  a2=G.Sugestao.query.filter_by(cerca_id=c.id,rotograma_id=r2.id).one()
  res=self.decidir(a1,'dispensar');self.assertEqual(res.status_code,302)
  self.assertIn('/notificacoes',res.location)
  grupo=next(x for x in G.alertas() if x['cerca'].id==c.id);self.assertEqual(grupo['quantidade'],1)
  self.assertIn(f'id="cerca-{c.id}"',self.c.get(f'/notificacoes?cerca_id={c.id}').text)
  self.assertEqual(self.decidir(a2,'dispensar').status_code,302)
  self.assertFalse(any(x['cerca'].id==c.id for x in G.alertas()))
  self.assertNotIn(f'id="cerca-{c.id}"',self.c.get(f'/notificacoes?cerca_id={c.id}').text)
  self.assertIn(f'id="cerca-{c.id}"',self.c.get(f'/notificacoes?status=concluida&cerca_id={c.id}').text)
 def test_busca_notificacao_por_rotograma(self):
  c,r1,r2=self.duas_rotas()
  self.assertIn(f'id="cerca-{c.id}"',self.c.get('/notificacoes?q=Segundo').text)
  self.assertNotIn(f'id="cerca-{c.id}"',self.c.get('/notificacoes?q=inexistenteXYZ').text)
 def test_cenario_tres_cidades_sugere_so_mesma_e_vizinha(self):
  c,r1,r2=self.duas_rotas()
  ref=self.cerca('Referência distante em Santos','Santos')
  r3=S.Rotograma(nome='Rotograma distante',ativo=True);S.db.session.add(r3);S.db.session.commit()
  S.db.session.add(S.RotogramaCerca(cerca_id=ref.id,rotograma_id=r3.id));S.db.session.commit()
  G.gerar(c,G.obter_base());S.db.session.commit()
  itens=G.Sugestao.query.filter_by(cerca_id=c.id).all()
  self.assertEqual({a.rotograma_id for a in itens},{r1.id,r2.id})
  self.assertEqual(S.RotogramaCerca.query.filter_by(cerca_id=c.id).count(),0)
 def test_mesmo_rotograma_em_duas_cidades_aparece_uma_vez(self):
  r,ref=self.referencia(cidade='Mogi Guaçu')
  vizinha=self.cerca('Referência vizinha adicional','Mogi Mirim')
  S.db.session.add(S.RotogramaCerca(cerca_id=vizinha.id,rotograma_id=r.id));S.db.session.commit()
  c=self.nova();itens=G.Sugestao.query.filter_by(cerca_id=c.id).all()
  self.assertEqual(len(itens),1);self.assertEqual(itens[0].motivo['tipo'],'mesmo')
 def test_duas_cercas_novas_mantem_notificacoes_independentes(self):
  c,r1,r2=self.duas_rotas();outra=self.cerca('Segunda cerca nova','Mogi Guaçu')
  grupos={g['cerca'].id:g for g in G.alertas()}
  self.assertIn(c.id,grupos);self.assertIn(outra.id,grupos)
  self.assertEqual(grupos[c.id]['quantidade'],2);self.assertEqual(grupos[outra.id]['quantidade'],2)
 def test_fluxo_confirmar_um_dispensar_outro_preserva_historico(self):
  c,r1,r2=self.duas_rotas()
  a1=G.Sugestao.query.filter_by(cerca_id=c.id,rotograma_id=r1.id).one()
  a2=G.Sugestao.query.filter_by(cerca_id=c.id,rotograma_id=r2.id).one()
  self.assertEqual(self.decidir(a1,'dispensar').status_code,302)
  self.assertEqual(self.decidir(a2,'vincular').status_code,302)
  self.assertEqual(a1.decisao,'dispensada');self.assertEqual(a2.decisao,'vinculada')
  self.assertEqual({v.rotograma_id for v in S.RotogramaCerca.query.filter_by(cerca_id=c.id)},{r2.id})
  self.assertFalse(any(g['cerca'].id==c.id for g in G.alertas()))
  historicos=S.HistoricoAlteracao.query.filter_by(item_id=c.id,tipo_operacao='decisao_municipal').all()
  self.assertEqual(len(historicos),2);self.assertTrue(all('Pessoa de teste' in h.valor_novo for h in historicos))
 def test_telas_notificacoes(self):
  self.sugestao()
  for url in ['/','/pendencias','/pendencias?status=concluida','/notificacoes','/notificacoes?status=concluida','/historico?tipo=sugestao_municipal','/cercas/nova']:
   r=self.c.get(url);self.assertEqual(r.status_code,200,r.text)
  self.assertIn('Município vizinho (divisa)',self.c.get('/notificacoes').text)

if __name__=='__main__':unittest.main()
