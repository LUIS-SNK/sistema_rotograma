"""Executar: python -m unittest discover -s tests -v. Usa somente bancos temporários."""
import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['DESATIVAR_VERIFICADOR'] = '1'
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import threading
import time
import sqlite3
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError
import app as sistema
from validade import vencimento, somar_meses, situacao_validade, ler_referencia, VerificadorInterno


class Regras(unittest.TestCase):
    def setUp(self):
        self.contexto = sistema.app.app_context(); self.contexto.push()
        sistema.app.config['TESTING'] = True
        sistema.db.drop_all(); sistema.db.create_all()
        self.cliente = sistema.app.test_client()
        self.patches = [patch('app.hoje', return_value=date(2026,10,28)), patch('validade.hoje', return_value=date(2026,10,28))]
        for p in self.patches: p.start()

    def tearDown(self):
        sistema.db.session.remove()
        for p in self.patches: p.stop()
        self.contexto.pop()

    def criar(self, tipo, nome='Teste', **extras):
        dados={'nome':nome,'ativo':'on','tipo':'Refeição' if tipo=='posto' else 'Via','data_referencia':'2025-03-15','cidade':'Mogi Mirim','estado':'SP'}
        dados.update(extras)
        url={'posto':'/postos/novo','cerca':'/cercas/nova','rotograma':'/rotogramas/novo'}[tipo]
        resposta=self.cliente.post(url,data=dados)
        self.assertEqual(resposta.status_code,302,resposta.get_data(as_text=True))
        return {'posto':sistema.Posto,'cerca':sistema.Cerca,'rotograma':sistema.Rotograma}[tipo].query.filter_by(nome=nome).one()

    def editar(self, tipo, item, **extras):
        dados={campo:getattr(item,campo) or '' for campo in ('nome','descricao')}
        dados.update(versao=item.versao,ativo='on' if item.ativo else '')
        if tipo=='posto': dados.update(tipo=item.tipo,endereco=item.endereco or '',cidade=item.cidade or '',estado=item.estado or '',data_referencia=item.data_referencia.isoformat() if item.data_referencia else '')
        if tipo=='cerca': dados.update(tipo=item.tipo,cidade=item.cidade or '',estado=item.estado or '',velocidade=str(item.velocidade or ''))
        if tipo=='rotograma': dados.update(origem=item.origem or '',destino=item.destino or '',data_referencia=item.data_referencia.isoformat() if item.data_referencia else '')
        dados.update(extras)
        return self.cliente.post(f'/{tipo}s/{item.id}/editar',data=dados)

    def vincular(self, r, p):
        self.assertEqual(self.cliente.post(f'/rotogramas/{r.id}/vincular-posto',data={'posto_id':p.id,'versao':r.versao}).status_code,302)

    def test_calculo_calendario(self):
        self.assertEqual(vencimento(date(2025,3,15)),date(2027,3,15))
        self.assertEqual(vencimento(date(2024,2,29)),date(2026,2,28))
        self.assertEqual(somar_meses(date(2027,3,31),-1),date(2027,2,28))
        self.assertIsNone(vencimento(None))

    def test_limites_alerta_mes_calendario(self):
        p=sistema.Posto(data_vencimento=date(2026,11,28))
        self.assertEqual(situacao_validade(p,date(2026,10,27)),'vigente')
        self.assertEqual(situacao_validade(p,date(2026,10,28)),'proximo')
        self.assertEqual(situacao_validade(p,date(2026,11,28)),'vencido')

    def test_validacoes_datas(self):
        for valor in ['2026-10-29','2025-02-29','2025-99-10','9999-01-01']:
            with self.assertRaises(ValueError): ler_referencia(valor,True)
        for tipo in ['posto','rotograma']:
            url='/postos/novo' if tipo=='posto' else '/rotogramas/novo'
            self.assertEqual(self.cliente.post(url,data={'nome':'Sem Data','tipo':'Refeição'}).status_code,400)
        with self.assertRaises(ValueError): ler_referencia('2020-01-01',True,True)

    def test_criacao_retroativa_posto_inativo_rotograma_apenas_sinalizado(self):
        p=self.criar('posto',data_referencia='2020-01-01')
        r=self.criar('rotograma',data_referencia='2020-01-01')
        self.assertFalse(p.ativo);self.assertEqual(p.motivo_inativacao,'vencimento')
        self.assertTrue(r.ativo);self.assertEqual(situacao_validade(r),'vencido')
        self.assertEqual(sistema.verificar_vencimentos(),0)

    def test_verificador_inativa_uma_vez_e_preserva_vinculo(self):
        p=self.criar('posto');r=self.criar('rotograma');self.vincular(r,p)
        self.assertEqual(sistema.verificar_vencimentos(date(2027,3,15)),1)
        self.assertEqual(sistema.verificar_vencimentos(date(2027,3,15)),0)
        sistema.db.session.refresh(p)
        self.assertFalse(p.ativo);self.assertEqual(sistema.RotogramaPosto.query.count(),1)
        self.assertEqual(sistema.HistoricoAlteracao.query.filter_by(tipo_operacao='inativacao_automatica').count(),2)
        self.assertEqual(len(sistema.problemas_rotograma(r)),1)

    def test_verificador_nao_sobrepoe_concessao(self):
        sistema.db.session.add(sistema.ControleRotina(nome='vencimentos',bloqueado_ate=sistema.agora_utc()+timedelta(minutes=5),token='outro'))
        sistema.db.session.commit()
        self.assertEqual(sistema.verificar_vencimentos(),0)
        self.assertEqual(sistema.db.session.get(sistema.ControleRotina,'vencimentos').token,'outro')

    def test_regularizacao_resolve_alerta_preserva_verificacao_manual(self):
        p=self.criar('posto');r=self.criar('rotograma');self.vincular(r,p)
        antes=sistema.Pendencia.query.filter_by(status='aberta').count()
        sistema.verificar_vencimentos(date(2027,3,15));sistema.db.session.refresh(p)
        resposta=self.cliente.post(f'/cadastros/posto/{p.id}/regularizar',data={'versao':p.versao,'data_referencia':'2026-10-01'})
        self.assertEqual(resposta.status_code,302)
        self.assertTrue(p.ativo);self.assertEqual(sistema.problemas_rotograma(r),[])
        self.assertGreaterEqual(sistema.Pendencia.query.filter_by(status='aberta').count(),antes)
        self.assertGreater(sistema.HistoricoAlteracao.query.filter_by(tipo_operacao='regularizacao').count(),0)

    def test_regularizacao_nao_reativa_manual(self):
        p=self.criar('posto',ativo='')
        resposta=self.cliente.post(f'/cadastros/posto/{p.id}/regularizar',data={'versao':p.versao,'data_referencia':'2026-10-01'})
        self.assertEqual(resposta.status_code,302);self.assertFalse(p.ativo);self.assertEqual(p.motivo_inativacao,'manual')

    def test_exclusao_logica_e_integridade(self):
        p=self.criar('posto');r=self.criar('rotograma');self.vincular(r,p)
        confirmacao=self.cliente.get(f'/cadastros/posto/{p.id}/excluir').get_data(as_text=True)
        self.assertIn(r.nome,confirmacao)
        resposta=self.cliente.post(f'/cadastros/posto/{p.id}/excluir',data={'versao':p.versao,'confirmar':'sim'})
        self.assertEqual(resposta.status_code,302);self.assertIsNotNone(p.excluido_em)
        self.assertEqual(sistema.RotogramaPosto.query.count(),1)
        self.assertEqual(sistema.problemas_rotograma(r)[0]['motivo'],'Excluído')
        self.assertNotIn('<strong>Teste</strong>',self.cliente.get('/postos').get_data(as_text=True))
        self.assertIn('<strong>Teste</strong>',self.cliente.get('/postos?status=excluido').get_data(as_text=True))
        self.assertEqual(self.cliente.get(f'/cadastros/posto/{p.id}/regularizar').status_code,409)
        self.assertEqual(self.cliente.get(f'/rotogramas/{r.id}').status_code,200)

    def test_remocao_explicita_resolve_composicao(self):
        p=self.criar('posto');r=self.criar('rotograma');self.vincular(r,p)
        self.assertEqual(self.editar('posto',p,ativo='').status_code,302)
        self.assertEqual(len(sistema.problemas_rotograma(r)),1)
        self.assertEqual(self.cliente.post(f'/rotogramas/{r.id}/desvincular-posto/{p.id}',data={'versao':r.versao}).status_code,302)
        sistema.db.session.expire_all()
        self.assertEqual(sistema.problemas_rotograma(r),[])

    def test_concorrencia_formulario_e_orm(self):
        p=self.criar('posto');antiga=p.versao
        self.assertEqual(self.editar('posto',p,cidade='Campinas').status_code,302)
        self.assertEqual(self.editar('posto',p,versao=antiga,cidade='Outra').status_code,409)
        self.assertEqual(p.cidade,'Campinas')
        a=Session(sistema.db.engine);b=Session(sistema.db.engine)
        try:
            x=a.get(sistema.Posto,p.id);y=b.get(sistema.Posto,p.id)
            x.descricao='A';a.commit();y.descricao='B'
            with self.assertRaises(StaleDataError):b.commit()
        finally:a.close();b.close()

    def test_cidade_uf_e_historico(self):
        self.assertEqual(self.cliente.post('/cercas/nova',data={'nome':'Nova','tipo':'Via'}).status_code,400)
        self.assertEqual(self.cliente.post('/cercas/nova',data={'nome':'Nova','tipo':'Via','cidade':'Mogi','estado':'XX'}).status_code,400)
        c=self.criar('cerca')
        self.assertEqual(self.editar('cerca',c,cidade='Campinas',estado='sp').status_code,302)
        self.assertEqual(c.estado,'SP')
        self.assertEqual(sistema.HistoricoAlteracao.query.filter_by(tipo_item='cerca',campo='cidade',tipo_operacao='edicao').count(),1)
        for url in ['/cercas?cidade=campinas&uf=SP',f'/cadastros/cerca/{c.id}']:
            self.assertIn('Campinas',self.cliente.get(url).get_data(as_text=True))

    def test_antigos_sem_datas_ou_localizacao(self):
        p=sistema.Posto(nome='Antigo',ativo=True);c=sistema.Cerca(nome='Antiga',ativo=True)
        sistema.db.session.add_all([p,c]);sistema.db.session.commit()
        self.assertEqual(sistema.verificar_vencimentos(),0);self.assertTrue(p.ativo)
        self.assertEqual(situacao_validade(p),'sem_data');self.assertIsNone(c.cidade)
        self.assertEqual(self.editar('cerca',c,descricao='Sem local').status_code,302)

    def test_filtros_validade_composicao_e_duplicidade(self):
        p=self.criar('posto','São José');r=self.criar('rotograma','Rota');self.vincular(r,p)
        self.editar('posto',p,ativo='')
        self.assertIn('<strong>Rota</strong>',self.cliente.get('/rotogramas?composicao=com').get_data(as_text=True))
        self.assertNotIn('<strong>Rota</strong>',self.cliente.get('/rotogramas?composicao=sem').get_data(as_text=True))
        self.assertEqual(self.cliente.post('/postos/novo',data={'nome':' SAO  JOSE ','tipo':'Refeição','data_referencia':'2025-03-15'}).status_code,409)
        self.assertIn('<strong>São José</strong>',self.cliente.get('/postos?q=sao&rotograma='+str(r.id)).get_data(as_text=True))

    def test_sem_duplicacao_alertas(self):
        self.criar('posto',data_referencia='2024-11-20')
        a=sistema.coletar_alertas();b=sistema.coletar_alertas()
        self.assertEqual([x['chave'] for x in a],[x['chave'] for x in b])
        self.assertEqual(len(a),len({x['chave'] for x in a}))
        self.assertEqual(self.cliente.get('/alertas').status_code,200)

    def test_posto_vencido_nao_vincula_antes_da_thread(self):
        p=self.criar('posto');r=self.criar('rotograma')
        p.data_vencimento=date(2026,10,28);sistema.db.session.commit()
        resposta=self.cliente.post(f'/rotogramas/{r.id}/vincular-posto',data={'posto_id':p.id,'versao':r.versao})
        self.assertEqual(resposta.status_code,302);self.assertEqual(sistema.RotogramaPosto.query.count(),0)

    def test_manter_inativo_remove_alerta_validade_mas_preserva_composicao(self):
        p=self.criar('posto');r=self.criar('rotograma');self.vincular(r,p)
        p.data_vencimento=date(2026,10,28);sistema.db.session.commit()
        sistema.verificar_vencimentos()
        self.assertEqual(self.cliente.post(f'/cadastros/posto/{p.id}/manter-inativo',data={'versao':p.versao}).status_code,302)
        self.assertEqual(p.motivo_inativacao,'manual')
        alertas=sistema.coletar_alertas()
        self.assertFalse(any(a['categoria']=='validade' and a['tipo']=='posto' and a['item'].id==p.id for a in alertas))
        self.assertEqual(len(sistema.problemas_rotograma(r)),1)

    def test_excluir_rotograma_nao_remove_composicao(self):
        p=self.criar('posto');r=self.criar('rotograma');self.vincular(r,p)
        self.assertEqual(self.cliente.post(f'/cadastros/rotograma/{r.id}/excluir',data={'versao':r.versao,'confirmar':'sim'}).status_code,302)
        self.assertEqual(sistema.RotogramaPosto.query.count(),1)
        self.assertEqual(self.cliente.get(f'/rotogramas/{r.id}').status_code,200)
        self.assertEqual(self.cliente.post(f'/rotogramas/{r.id}/desvincular-posto/{p.id}',data={'versao':r.versao}).status_code,409)

    def test_cerca_inativa_e_excluida_causam_problema_sem_remover_vinculo(self):
        c=self.criar('cerca');r=self.criar('rotograma')
        self.assertEqual(self.cliente.post(f'/rotogramas/{r.id}/vincular-cerca',data={'versao':r.versao,'cerca_id':c.id}).status_code,302)
        self.assertEqual(self.editar('cerca',c,ativo='').status_code,302)
        self.assertEqual(len(sistema.problemas_rotograma(r)),1)
        self.assertEqual(self.cliente.post(f'/cadastros/cerca/{c.id}/excluir',data={'versao':c.versao,'confirmar':'sim'}).status_code,302)
        self.assertEqual(sistema.RotogramaCerca.query.count(),1)
        self.assertEqual(sistema.problemas_rotograma(r)[0]['motivo'],'Excluído')

    def test_templates_todos(self):
        p=self.criar('posto');c=self.criar('cerca');r=self.criar('rotograma')
        urls=['/','/alertas','/historico','/pendencias','/cercas','/postos','/rotogramas','/postos/novo','/cercas/nova','/rotogramas/novo',f'/rotogramas/{r.id}',f'/postos/{p.id}/editar',f'/cercas/{c.id}/editar',f'/rotogramas/{r.id}/editar',f'/cadastros/posto/{p.id}',f'/cadastros/cerca/{c.id}',f'/cadastros/posto/{p.id}/regularizar',f'/cadastros/rotograma/{r.id}/regularizar',f'/cadastros/posto/{p.id}/excluir']
        for url in urls:
            with self.subTest(url=url):self.assertEqual(self.cliente.get(url).status_code,200)


class Agendamento(unittest.TestCase):
    def test_periodico_sem_requisicao_e_sem_threads_duplicadas(self):
        contador=[];pronto=threading.Event()
        def executar():
            contador.append(1)
            if len(contador)>=2:pronto.set()
        verificador=VerificadorInterno(sistema.app,executar,.02)
        verificador.iniciar();thread=verificador.thread;verificador.iniciar()
        self.assertIs(verificador.thread,thread)
        self.assertTrue(pronto.wait(2));verificador.encerrar()
        self.assertFalse(thread.is_alive())


class Migracao(unittest.TestCase):
    def test_banco_novo_e_reexecucao(self):
        from alembic import command
        from alembic.config import Config
        with TemporaryDirectory() as pasta:
            engine=create_engine('sqlite:///'+str(Path(pasta)/'novo.db'))
            try:
                cfg=Config();cfg.set_main_option('script_location',str(Path(sistema.__file__).parent/'migrations'))
                for _ in range(2):
                    with engine.begin() as conn:cfg.attributes['connection']=conn;command.upgrade(cfg,'head')
                with engine.connect() as conn:self.assertEqual(conn.execute(text('SELECT COUNT(*) FROM postos')).scalar(),0)
            finally:engine.dispose()

    def test_banco_legado_preserva_dados_vinculos_e_datas_nulas(self):
        from alembic import command
        from alembic.config import Config
        with TemporaryDirectory() as pasta:
            engine=create_engine('sqlite:///'+str(Path(pasta)/'antigo.db'))
            try:
                with engine.begin() as conn:
                    conn.execute(text('CREATE TABLE postos (id INTEGER PRIMARY KEY, nome VARCHAR(120) NOT NULL, ativo BOOLEAN NOT NULL, criado_em DATETIME NOT NULL, atualizado_em DATETIME NOT NULL)'))
                    conn.execute(text("INSERT INTO postos VALUES (1, 'Legado', 0, '2025-01-01 12:00:00', '2025-01-01 12:00:00')"))
                cfg=Config();cfg.set_main_option('script_location',str(Path(sistema.__file__).parent/'migrations'))
                for _ in range(2):
                    with engine.begin() as conn:cfg.attributes['connection']=conn;command.upgrade(cfg,'head')
                with engine.connect() as conn:
                    linha=conn.execute(text('SELECT nome,data_referencia,data_vencimento,motivo_inativacao,versao FROM postos')).one()
                    self.assertEqual(tuple(linha),('Legado',None,None,'manual',1))
            finally:engine.dispose()


if __name__=='__main__':unittest.main()
