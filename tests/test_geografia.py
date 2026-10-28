import os
os.environ['DATABASE_URL']='sqlite:///:memory:'
os.environ['DESATIVAR_VERIFICADOR']='1'
import unittest
import re
from datetime import timedelta
from unittest.mock import patch
from werkzeug.security import generate_password_hash
import app as S
import geografia as G
from ors_client import ErroORS,distancia_trajeto

SENHA='SenhaTeste!2026'

class FakeORS:
    def __init__(self):self.geocodes=0;self.rotas=0;self.falhar=False;self.ambiguo=False
    def geocodificar(self,texto,uf):
        self.geocodes+=1
        if self.falhar:raise ErroORS('API indisponível para teste')
        coords={'Campinas':[-47,-23],'Mogi Mirim':[-47,-22],'Jaguariúna':[-46.99,-22.5],'Santos':[-46,-24]}
        p={'rotulo':texto+', SP, Brasil','coordenadas':coords[texto],'uf':'SP','regiao':'São Paulo','tipo':'locality','confianca':1}
        return [p,dict(p,rotulo='Outro candidato',coordenadas=[p['coordenadas'][0]+.1,p['coordenadas'][1]])] if self.ambiguo else [p]
    def trajeto(self,a,b):
        self.rotas+=1
        if self.falhar:raise ErroORS('API indisponível para teste')
        return {'linha':[a,b],'credito':'ORS e OpenStreetMap — teste simulado'}

class Integracao(unittest.TestCase):
    def setUp(self):
        self.ctx=S.app.app_context();self.ctx.push()
        S.app.config.update(TESTING=True,LOGIN_DISABLED=False,WTF_CSRF_ENABLED=False,ORS_ENABLED=False,ORS_API_KEY='',ORS_RAIO_KM=10)
        S.db.session.remove();S.db.drop_all();S.db.create_all()
        self.fake=FakeORS();S.app.config['ORS_CLIENT_FACTORY']=lambda:self.fake
        self.admin=S.Usuario(login='admin',nome='Administrador Teste',senha_hash=generate_password_hash(SENHA),ativo=True,admin=True)
        S.db.session.add(self.admin);S.db.session.commit()
        self.c=S.app.test_client();self.assertEqual(self.c.post('/login',data={'login':'admin','senha':SENHA}).status_code,302)
    def tearDown(self):
        S.db.session.remove();S.app.config.pop('ORS_CLIENT_FACTORY',None);self.ctx.pop()
    def rota(self,**extras):
        dados=dict(nome='Rota Teste',origem='Campinas',destino='Mogi Mirim',origem_uf='SP',destino_uf='SP',ativo=True)
        dados.update(extras);r=S.Rotograma(**dados);S.db.session.add(r);S.db.session.commit();return r
    def cerca(self,nome='Cerca Teste',**extras):
        dados=dict(nome=nome,cidade='Jaguariúna',estado='SP',tipo='Via',ativo=True,geo_habilitada=True)
        dados.update(extras);c=S.Cerca(**dados);S.db.session.add(c);S.db.session.commit();return c
    def gerar(self):
        r=self.rota();c=self.cerca();G.processar_fila();return r,c,G.Analise.query.one()
    def decidir(self,a,decisao='vincular',**extras):
        dados={'versao':a.versao,'decisao':decisao,'confirmar':'sim','justificativa':'Revisão de demonstração'};dados.update(extras)
        return self.c.post(f'/analises-cercas/{a.id}/decidir',data=dados)

    def test_sugestao_sem_vinculo_automatico(self):
        r,c,a=self.gerar()
        self.assertEqual(a.status,'pendente');self.assertLess(a.distancia_m,10000)
        self.assertEqual(S.RotogramaCerca.query.count(),0)
        self.assertEqual(G.Tarefa.query.one().status,'concluida')
        self.assertTrue(any(x['categoria']=='analise_geografica' for x in S.coletar_alertas()))

    def test_cache_persistente_e_avisos_unicos(self):
        r,c,a=self.gerar();contador=self.fake.rotas
        G.processar_fila();G.processar_fila()
        self.assertEqual(G.Analise.query.count(),1);self.assertEqual(self.fake.rotas,contador)
        self.cerca('Segunda cerca')
        G.processar_fila()
        self.assertEqual(self.fake.rotas,1);self.assertEqual(G.Analise.query.count(),2)
        S.db.session.remove();self.assertEqual(G.Trajeto.query.count(),1)

    def test_fora_da_margem_so_conclui_depois_do_calculo(self):
        self.rota();self.cerca(cidade='Santos');G.processar_fila()
        self.assertEqual(G.Analise.query.count(),0);self.assertEqual(G.Tarefa.query.one().status,'concluida')
        self.assertIn('Comparação concluída',G.Tarefa.query.one().mensagem)

    def test_api_falha_nao_bloqueia_cadastro(self):
        self.rota();self.fake.falhar=True
        res=self.c.post('/cercas/nova',data={'nome':'Nova','tipo':'Via','cidade':'Jaguariúna','estado':'SP','ativo':'on'})
        self.assertEqual(res.status_code,302);self.assertEqual(S.Cerca.query.count(),1)
        self.assertEqual(G.Tarefa.query.one().status,'pendente')
        G.processar_fila()
        self.assertEqual(G.Tarefa.query.one().status,'aguardando_api');self.assertEqual(G.Analise.query.count(),0)

    def test_sem_chave_preserva_fila(self):
        S.app.config.pop('ORS_CLIENT_FACTORY');self.rota();self.cerca();G.processar_fila()
        self.assertEqual(G.Tarefa.query.one().status,'aguardando_configuracao')
        self.assertEqual(G.Tarefa.query.one().tentativas,0)

    def test_localizacao_ambigua_exige_confirmacao(self):
        self.rota();self.fake.ambiguo=True;self.cerca();G.processar_fila()
        t=G.Tarefa.query.one();self.assertEqual(t.status,'revisar_localizacao');local=S.db.session.get(G.Geocodificacao,t.localizacao_id)
        self.assertEqual(G.Analise.query.count(),0)
        self.assertEqual(self.c.post(f'/analises-cercas/localizacoes/{local.id}',data={'versao':local.versao,'candidato':'0','confirmar':'sim'}).status_code,302)
        self.fake.ambiguo=False;G.processar_fila()
        self.assertEqual(G.Analise.query.count(),1);self.assertEqual(local.usuario_id,self.admin.id)

    def test_origem_sem_uf_nao_e_escolhida_silenciosamente(self):
        self.rota(origem_uf=None);self.cerca();G.processar_fila()
        self.assertEqual(G.Tarefa.query.one().status,'revisar_localizacao')
        self.assertEqual(G.Analise.query.count(),0)

    def test_coordenadas_manuais_dispensa_geocodificacao(self):
        self.rota(origem_latitude=-23,origem_longitude=-47,destino_latitude=-22,destino_longitude=-47)
        self.cerca(latitude=-22.5,longitude=-46.99);G.processar_fila()
        self.assertEqual(self.fake.geocodes,0);self.assertEqual(G.Analise.query.one().precisao,'Coordenadas informadas')

    def test_vincular_com_autoria_e_historico(self):
        r,c,a=self.gerar();self.assertEqual(self.decidir(a).status_code,302)
        self.assertEqual(S.RotogramaCerca.query.count(),1);self.assertEqual(a.status,'vinculada')
        self.assertEqual(a.usuario_id,self.admin.id);self.assertIsNotNone(a.decidida_em)
        h=S.HistoricoAlteracao.query.filter_by(tipo_operacao='decisao_analise').one()
        self.assertEqual(h.usuario_id,self.admin.id);self.assertEqual(h.origem_operacao,'usuario')
        self.assertEqual(S.Pendencia.query.count(),1)

    def test_dispensa_nao_reabre_em_ciclos_iguais(self):
        r,c,a=self.gerar();self.assertEqual(self.decidir(a,'dispensar').status_code,302)
        t=a.tarefa;t.status='pendente';t.proxima_tentativa=S.agora_utc();S.db.session.commit();G.processar_fila()
        self.assertEqual(a.status,'dispensada');self.assertEqual(S.RotogramaCerca.query.count(),0)

    def test_decisao_dupla_rejeitada(self):
        r,c,a=self.gerar();versao=a.versao
        self.assertEqual(self.decidir(a,'dispensar').status_code,302)
        self.assertEqual(self.decidir(a,'vincular',versao=versao).status_code,409)
        self.assertEqual(S.RotogramaCerca.query.count(),0)

    def test_mudanca_localizacao_invalida_analise(self):
        r,c,a=self.gerar();c.cidade='Santos';S.db.session.commit()
        self.assertEqual(a.status,'obsoleta');self.assertEqual(self.decidir(a).status_code,409)
        G.processar_fila();self.assertEqual(S.RotogramaCerca.query.count(),0)
        self.assertEqual(G.Tarefa.query.filter_by(status='concluida').count(),1)

    def test_exclusao_ou_inativacao_cancela_sem_remover_vinculos(self):
        r,c,a=self.gerar();c.ativo=False;S.db.session.commit()
        self.assertEqual(a.status,'cancelada');self.assertEqual(self.decidir(a).status_code,409)

    def test_cache_vencido_exige_nova_comparacao(self):
        r,c,a=self.gerar();a.trajeto.valido_ate=S.agora_utc()-timedelta(seconds=1);S.db.session.commit()
        self.assertEqual(self.decidir(a).status_code,409)
        self.assertEqual(a.tarefa.status,'pendente');G.processar_fila()
        self.assertEqual(self.fake.rotas,2)
        self.assertEqual(self.decidir(a).status_code,302)

    def test_cercas_antigas_nao_geram_analises_automaticas(self):
        r=self.rota();c=self.cerca(geo_habilitada=False)
        G.processar_fila();self.assertEqual(G.Tarefa.query.count(),0)
        self.assertEqual(self.c.post(f'/analises-cercas/cercas/{c.id}/solicitar',data={'versao':c.versao}).status_code,302)
        G.processar_fila();self.assertEqual(G.Analise.query.count(),1)

    def test_nova_rota_recalcula_pares_habilitados(self):
        r,c,a=self.gerar();r2=self.rota(nome='Segunda rota')
        G.processar_fila();self.assertEqual(G.Analise.query.count(),2);self.assertEqual(self.fake.rotas,1)

    def test_concessao_impede_workers_concorrentes(self):
        self.rota();self.cerca()
        S.db.session.add(S.ControleRotina(nome='geografia',bloqueado_ate=S.agora_utc()+timedelta(minutes=5),token='outro'));S.db.session.commit()
        self.assertEqual(G.processar_fila(),0);self.assertEqual(self.fake.rotas,0)

    def test_saldo_e_intervalo_respeitados(self):
        S.app.config.update(ORS_ENABLED=True,ORS_API_KEY='chave-ficticia-nao-utilizada')
        G.reservar('directions')
        with self.assertRaises(G.Aguardar):G.reservar('directions')
        c=S.db.session.get(G.Cota,'directions');c.proxima=S.agora_utc()-timedelta(seconds=1);c.restante_api=0;c.reset_api=S.agora_utc()+timedelta(hours=2);S.db.session.commit()
        with self.assertRaises(G.Aguardar):G.reservar('directions')

    def test_login_obrigatorio_e_logout(self):
        outro=S.app.test_client();self.assertEqual(outro.get('/').status_code,302)
        self.assertEqual(outro.post('/cercas/nova',data={}).status_code,401)
        self.assertEqual(outro.post('/login',data={'login':'admin','senha':'errada'}).status_code,401)
        self.assertEqual(self.c.post('/sair').status_code,302);self.assertEqual(self.c.get('/analises-cercas').status_code,302)

    def test_csrf_em_login_e_nova_decisao(self):
        S.app.config['WTF_CSRF_ENABLED']=True
        outro=S.app.test_client()
        self.assertEqual(outro.post('/login',data={'login':'admin','senha':SENHA}).status_code,400)
        html=outro.get('/login').get_data(as_text=True);token=re.search('name="csrf_token" value="([^"]+)"',html).group(1)
        self.assertEqual(outro.post('/login',data={'login':'admin','senha':SENHA,'csrf_token':token}).status_code,302)
        self.assertEqual(outro.post('/sair').status_code,400)
        S.app.config['WTF_CSRF_ENABLED']=False

    def test_desativacao_revoga_sessao(self):
        self.admin.ativo=False;S.db.session.commit()
        self.assertEqual(self.c.get('/').status_code,302)

    def test_usuarios_apenas_admin(self):
        self.admin.admin=False;S.db.session.commit()
        with self.c.session_transaction() as sess:sess['usuario_versao']=self.admin.versao
        self.assertEqual(self.c.get('/usuarios').status_code,403)

    def test_coordenadas_invalidas_rejeitadas(self):
        for dados in [{'latitude':'-22'},{'latitude':'nan','longitude':'-47'},{'latitude':'91','longitude':'-47'}]:
            res=self.c.post('/cercas/nova',data=dict(nome='Inválida',tipo='Via',cidade='Jaguariúna',estado='SP',ativo='on',**dados))
            self.assertEqual(res.status_code,400)
        self.assertEqual(S.Cerca.query.count(),0)

    def test_templates_analises_e_autoria(self):
        r,c,a=self.gerar()
        for url in ['/usuarios','/analises-cercas',f'/analises-cercas/{a.id}','/alertas?categoria=analise_geografica','/historico',f'/cadastros/cerca/{c.id}',f'/rotogramas/{r.id}/editar']:
            with self.subTest(url=url):self.assertEqual(self.c.get(url).status_code,200)

if __name__=='__main__':unittest.main()
