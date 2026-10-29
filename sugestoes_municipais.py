"""Notificações por nova cerca, com sugestões municipais de rotogramas."""
import hmac
import json
import os
import secrets
from pathlib import Path
from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import event, inspect
from sqlalchemy.orm import backref
import click
import municipios
import faixa_geografica as faixa


def instalar(sistema):
    global S, db, app, Fila, Sugestao
    S = sistema; db = S.db; app = S.app
    app.config.setdefault('FAIXA_RAIO_KM', faixa.raio(os.getenv('FAIXA_RAIO_KM', '30')))

    class Fila(db.Model):
        __tablename__ = 'fila_municipal'
        cerca_id = db.Column(db.Integer, db.ForeignKey('cercas.id'), primary_key=True)
        status = db.Column(db.String(40), nullable=False, default='pendente')
        mensagem = db.Column(db.String(500), nullable=True)
        processada_em = db.Column(db.DateTime, nullable=True)
        base_versao = db.Column(db.String(64), nullable=True)
        cerca = db.relationship(S.Cerca)

    class Sugestao(db.Model):
        __tablename__ = 'sugestoes_municipais'
        id = db.Column(db.Integer, primary_key=True)
        cerca_id = db.Column(db.Integer, db.ForeignKey('cercas.id'), nullable=False)
        rotograma_id = db.Column(db.Integer, db.ForeignKey('rotogramas.id'), nullable=False)
        pendencia_id = db.Column(db.Integer, db.ForeignKey('pendencias.id'), unique=True, nullable=False)
        municipio_origem = db.Column(db.String(150), nullable=False)
        motivo = db.Column(db.JSON, nullable=False)
        decisao = db.Column(db.String(25), nullable=True)
        responsavel = db.Column(db.String(120), nullable=True)
        justificativa = db.Column(db.String(500), nullable=True)
        decidida_em = db.Column(db.DateTime, nullable=True)
        versao = db.Column(db.Integer, nullable=False, default=1, server_default='1')
        __mapper_args__ = {'version_id_col': versao}
        __table_args__ = (db.UniqueConstraint('cerca_id', 'rotograma_id', name='uq_sugestao_municipal_par'),)
        cerca = db.relationship(S.Cerca)
        rotograma = db.relationship(S.Rotograma)
        pendencia = db.relationship(S.Pendencia, backref=backref('sugestao_municipal', uselist=False))

    S.FilaMunicipal = Fila; S.SugestaoMunicipal = Sugestao
    # Usado apenas nas ações novas. Não cria contas ou muda o acesso da versão 2.0.
    if app.secret_key == 'dev-chave-alterar':
        if app.config['SQLALCHEMY_DATABASE_URI'].endswith(':memory:'):
            app.secret_key = secrets.token_hex(32)
        else:
            p = Path(app.instance_path) / 'secret.key'; p.parent.mkdir(exist_ok=True)
            try:
                with p.open('x', encoding='ascii') as f: f.write(secrets.token_hex(32))
            except FileExistsError:
                pass
            app.secret_key = p.read_text(encoding='ascii').strip()
    app.jinja_env.globals['token_municipal'] = token_csrf
    app.context_processor(contexto)
    app.add_url_rule('/notificacoes', 'listar_notificacoes', listar)
    app.add_url_rule('/notificacoes/<int:item_id>/decidir', 'decidir_notificacao', decidir, methods=['POST'])
    app.add_url_rule('/pendencias/<int:item_id>/decidir-sugestao', 'decidir_sugestao', decidir, methods=['POST'])
    app.add_url_rule('/pendencias/reprocessar-municipios', 'reprocessar_municipios', repetir, methods=['POST'])
    app.cli.command('atualizar-municipios')(comando_atualizar)
    sessao = db.session.session_factory.class_
    event.listen(sessao, 'after_flush', capturar)
    event.listen(sessao, 'before_commit', preparar)
    event.listen(sessao, 'after_rollback', lambda sess: (sess.info.pop('municipios_alvos', None), sess.info.pop('faixas_alteradas', None)))


def obter_base():
    try:
        return municipios.carregar(app.config.get('MUNICIPIOS_ARQUIVO'))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def identificacao(cerca, base):
    m = municipios.buscar(base, cerca.cidade, cerca.estado) if base else None
    if m:
        return m['codigo'], m
    return 'texto:' + municipios.normalizar(cerca.cidade) + '|' + (cerca.estado or '').upper(), None


def evidencias(cerca, base):
    chave, municipio = identificacao(cerca, base)
    cidade = municipios.normalizar(cerca.cidade)
    vizinhos = set(municipio['vizinhos']) if municipio and municipio['malha'] and not municipio.get('revisar_divisas') else set()
    itens = db.session.query(S.Rotograma, S.Cerca).join(S.RotogramaCerca, S.RotogramaCerca.rotograma_id == S.Rotograma.id).join(
        S.Cerca, S.Cerca.id == S.RotogramaCerca.cerca_id).filter(
        S.Rotograma.ativo.is_(True), S.Rotograma.excluido_em.is_(None), S.Cerca.ativo.is_(True),
        S.Cerca.excluido_em.is_(None), S.Cerca.id != cerca.id).all()
    vinculados = {v.rotograma_id for v in S.RotogramaCerca.query.filter_by(cerca_id=cerca.id)}
    resultado = {}
    for rota, referencia in itens:
        if rota.id in vinculados:
            continue
        codigo_ref, m_ref = identificacao(referencia, base)
        mesmo = bool(cidade and cerca.estado) and ((codigo_ref == chave) if municipio and m_ref else (
            municipios.normalizar(referencia.cidade) == cidade and (referencia.estado or '').upper() == cerca.estado.upper()))
        vizinho = codigo_ref in vizinhos and m_ref and m_ref['malha'] and not m_ref.get('revisar_divisas')
        if not mesmo and not vizinho:
            continue
        # Uma sugestão por rotograma; priorizar o motivo mais direto.
        if rota.id in resultado and resultado[rota.id][1]['tipo'] == 'mesmo':
            continue
        resultado[rota.id] = (rota, {'tipo': 'mesmo' if mesmo else 'vizinho', 'referencia_id': referencia.id,
            'origem_cidade': cerca.cidade, 'origem_uf': cerca.estado,
            'referencia_nome': referencia.nome, 'cidade': referencia.cidade, 'uf': referencia.estado,
            'fonte': base['fonte'] if base else 'Comparação textual de Cidade/UF (base indisponível)',
            'base_obtida_em': base['obtida_em'] if base else None})
    for rota in S.Rotograma.query.filter(S.Rotograma.ativo.is_(True), S.Rotograma.excluido_em.is_(None), S.Rotograma.faixa_ativa.is_(True)).all():
        if rota.id in vinculados:
            continue
        comparacao = faixa.comparar(cerca, rota, base, app.config['FAIXA_RAIO_KM'])
        if not comparacao:
            continue
        if rota.id in resultado:
            resultado[rota.id][1]['faixa'] = comparacao
        else:
            resultado[rota.id] = (rota, {'tipo': 'faixa', 'origem_cidade': cerca.cidade, 'origem_uf': cerca.estado,
                'cidade': cerca.cidade or '', 'uf': cerca.estado or '', 'faixa': comparacao,
                'fonte': 'Faixa direta em modelo esférico, sem consulta a estradas'})
    for rota, motivo in resultado.values():
        motivo['origem_coordenadas'] = [cerca.longitude, cerca.latitude]
    return resultado


def dados_faixa(rotograma):
    d = faixa.dados_rotograma(rotograma, obter_base(), app.config['FAIXA_RAIO_KM'])
    d['diagrama'] = faixa.diagrama(d)
    return d


def titulo_motivo(motivo):
    return {'mesmo': 'Mesmo município', 'vizinho': 'Município vizinho (divisa)', 'faixa': 'Dentro da faixa geográfica'}[motivo['tipo']]


def registrar(a, operacao, anterior, novo):
    return S.registrar_historico('sugestao_municipal', a.cerca_id,
        (a.cerca.nome + ' | ' + a.rotograma.nome)[:180], 'analise_municipal', anterior, novo, operacao)


def encerrar(a, decisao, mensagem):
    a.decisao = decisao; a.decidida_em = S.agora_utc()
    a.pendencia.status = 'concluida'; a.pendencia.concluida_em = a.decidida_em
    registrar(a, 'encerramento_sugestao', 'aberta', mensagem)


def disponivel(item):
    return item.ativo and item.excluido_em is None


def origem_mudou(a, base):
    return (municipios.normalizar(a.cerca.cidade) != municipios.normalizar(a.motivo.get('origem_cidade'))
            or (a.cerca.estado or '').upper() != (a.motivo.get('origem_uf') or '').upper()
            or [a.cerca.longitude, a.cerca.latitude] != a.motivo.get('origem_coordenadas', [None, None]))


def gerar(cerca, base):
    fila = db.session.get(Fila, cerca.id)
    if fila is None:
        fila = Fila(cerca_id=cerca.id); db.session.add(fila)
    fila.processada_em = S.agora_utc(); fila.base_versao = base['versao'] if base else None
    if not disponivel(cerca):
        fila.status = 'cancelada'; fila.mensagem = 'Cerca inativa ou excluída.'; return
    chave, municipio = identificacao(cerca, base)
    for rota, motivo in evidencias(cerca, base).values():
        a = Sugestao.query.filter_by(cerca_id=cerca.id, rotograma_id=rota.id).first()
        faixa_anterior = (a.motivo.get('faixa') or {}).get('contexto') if a else None
        faixa_nova = (motivo.get('faixa') or {}).get('contexto')
        if a and not origem_mudou(a, base) and a.decisao != 'cancelada' and not (
                a.pendencia.status != 'aberta' and a.motivo['tipo'] == 'faixa' and faixa_anterior != faixa_nova):
            # Dispensas e decisões encerradas nunca são reabertas por um reprocessamento.
            continue
        if a and a.pendencia.status == 'aberta':
            encerrar(a, 'cancelada', 'Localização da nova cerca alterada.')
        texto = titulo_motivo(motivo)
        h = S.registrar_historico('sugestao_municipal', cerca.id, (cerca.nome + ' | ' + rota.nome)[:180],
            'nova_cerca', None, json.dumps(motivo, ensure_ascii=False), 'sugestao_municipal')
        p = S.Pendencia(rotograma_id=rota.id, historico=h, tipo='sugestao_municipal',
            descricao=(texto + ': analisar nova cerca ' + cerca.nome)[:255])
        db.session.add(p); db.session.flush()
        if a is None:
            a = Sugestao(cerca_id=cerca.id, rotograma_id=rota.id, pendencia_id=p.id, municipio_origem=chave, motivo=motivo)
            db.session.add(a)
        else:
            a.pendencia = p; a.municipio_origem = chave; a.motivo = motivo
            a.decisao = None; a.responsavel = None; a.justificativa = None; a.decidida_em = None
    if not base:
        fila.status = 'aguardando_base'; fila.mensagem = 'Mesmo município verificado por Cidade/UF. Vizinhos aguardam a base municipal.'
    elif not municipio:
        fila.status = 'revisar_municipio'; fila.mensagem = 'Cidade/UF não encontrada na base IBGE. Revise a grafia no cadastro; vizinhos não foram comparados.'
    elif not municipio['malha'] or municipio.get('revisar_divisas'):
        fila.status = 'cobertura_parcial'; fila.mensagem = 'Mesmo município verificado. Divisas indisponíveis ou ambíguas na malha para este município.'
    else:
        fila.status = 'concluida'; fila.mensagem = 'Mesmo município e municípios com divisa verificados. Ausência de sugestão não comprova ausência de passagem.'
    if S.Rotograma.query.filter_by(faixa_ativa=True, ativo=True, excluido_em=None).first() and not faixa.localizar(
            cerca.cidade, cerca.estado, cerca.latitude, cerca.longitude, base):
        fila.status = 'revisar_coordenadas'
        fila.mensagem = 'Faixas não comparadas: informe coordenadas da cerca ou um município reconhecido com centro disponível. As relações municipais continuam sendo avaliadas.'


def reconciliar(base):
    por_cerca = {}
    for a in Sugestao.query.join(S.Pendencia).filter(S.Pendencia.status == 'aberta').all():
        if not disponivel(a.cerca) or not disponivel(a.rotograma):
            encerrar(a, 'cancelada', 'Cerca ou rotograma inativo/excluído.'); continue
        if S.RotogramaCerca.query.filter_by(cerca_id=a.cerca_id, rotograma_id=a.rotograma_id).first():
            encerrar(a, 'ja_vinculada', 'Vínculo criado por outro fluxo.'); continue
        if origem_mudou(a, base):
            encerrar(a, 'cancelada', 'Localização da cerca alterada.'); continue
        if a.cerca_id not in por_cerca:
            por_cerca[a.cerca_id] = evidencias(a.cerca, base)
        if a.rotograma_id not in por_cerca[a.cerca_id]:
            # Sem base não cancelar uma sugestão anterior de vizinhança.
            if not base and a.motivo['tipo'] == 'vizinho':
                continue
            if a.motivo['tipo'] == 'faixa' and a.rotograma.faixa_ativa and (
                    faixa.dados_rotograma(a.rotograma, base, app.config['FAIXA_RAIO_KM'])['erro'] or
                    not faixa.localizar(a.cerca.cidade, a.cerca.estado, a.cerca.latitude, a.cerca.longitude, base)):
                continue
            encerrar(a, 'cancelada', 'A referência municipal ou seus vínculos deixaram de justificar a sugestão.')
        else:
            motivo = por_cerca[a.cerca_id][a.rotograma_id][1]
            if a.motivo != motivo:
                a.motivo = motivo
                prefixo = titulo_motivo(motivo)
                a.pendencia.descricao = (prefixo + ': analisar nova cerca ' + a.cerca.nome)[:255]
                registrar(a, 'referencia_municipal', 'Referência anterior', json.dumps(motivo, ensure_ascii=False))


def capturar(sess, contexto):
    for obj in list(sess.new) + list(sess.dirty):
        if isinstance(obj, S.Cerca):
            campos = ('cidade', 'estado', 'ativo', 'excluido_em', 'latitude', 'longitude')
            if obj in sess.new or any(inspect(obj).attrs[c].history.has_changes() for c in campos):
                sess.info.setdefault('municipios_alvos', set()).add((obj.id, obj in sess.new))
        elif isinstance(obj, S.Rotograma):
            campos = ('origem', 'destino', 'origem_uf', 'destino_uf', 'origem_latitude', 'origem_longitude',
                      'destino_latitude', 'destino_longitude', 'faixa_ativa', 'faixa_raio_km', 'ativo', 'excluido_em')
            if obj in sess.new or any(inspect(obj).attrs[c].history.has_changes() for c in campos):
                sess.info['faixas_alteradas'] = True


def preparar(sess):
    if sess.info.get('municipios_preparando'):
        return
    sess.info['municipios_preparando'] = True
    try:
        sess.flush()
        base = obter_base()
        reconciliar(base)
        alvos = sess.info.pop('municipios_alvos', set())
        if sess.info.pop('faixas_alteradas', False):
            alvos |= {(f.cerca_id, False) for f in Fila.query.all()}
        for cerca_id, nova in alvos:
            c = sess.get(S.Cerca, cerca_id)
            if c and (nova or sess.get(Fila, cerca_id) is not None):
                gerar(c, base)
    finally:
        sess.info.pop('municipios_preparando', None)


def token_csrf():
    if '_municipal_csrf' not in session:
        session['_municipal_csrf'] = secrets.token_hex(32)
    return session['_municipal_csrf']


def validar_csrf():
    enviado = request.form.get('token_municipal', '')
    if not enviado or not hmac.compare_digest(enviado, session.get('_municipal_csrf', '')):
        abort(400, description='Formulário expirado. Recarregue a página e tente novamente.')


def contexto():
    if request.endpoint == 'static':
        return {}
    return {'notificacoes_abertas': len(alertas())}


def alertas():
    grupos = {}
    for a in Sugestao.query.join(S.Pendencia).filter(S.Pendencia.status == 'aberta').all():
        grupo = grupos.setdefault(a.cerca_id, {'cerca': a.cerca, 'quantidade': 0})
        grupo['quantidade'] += 1
    return list(grupos.values())


def listar():
    status = request.args.get('status', 'aberta')
    if status not in ('aberta', 'concluida', 'todas'):
        status = 'aberta'
    busca = request.args.get('q', '').strip()
    cerca_id = request.args.get('cerca_id', type=int)
    query = Sugestao.query
    if cerca_id:
        query = query.filter_by(cerca_id=cerca_id)
    grupos = {}
    for a in query.order_by(Sugestao.cerca_id.desc(), Sugestao.rotograma_id).all():
        grupo = grupos.setdefault(a.cerca_id, {'cerca': a.cerca, 'sugestoes': [], 'abertas': 0, 'concluidas': 0})
        grupo['sugestoes'].append(a)
        grupo['abertas' if a.pendencia.status == 'aberta' else 'concluidas'] += 1
    resultado = []
    for grupo in grupos.values():
        if status == 'aberta' and not grupo['abertas']:
            continue
        if status == 'concluida' and grupo['abertas']:
            continue
        texto = ' '.join([grupo['cerca'].nome, grupo['cerca'].cidade or '', grupo['cerca'].estado or ''] +
                         [a.rotograma.nome + ' ' + (a.motivo.get('cidade') or '') for a in grupo['sugestoes']])
        if busca and municipios.normalizar(busca) not in municipios.normalizar(texto):
            continue
        resultado.append(grupo)
    base = obter_base()
    incompletas = [(r, faixa.dados_rotograma(r, base, app.config['FAIXA_RAIO_KM'])) for r in
        S.Rotograma.query.filter_by(faixa_ativa=True, ativo=True, excluido_em=None).all()]
    return render_template('notificacoes.html', grupos=resultado, status=status, busca=busca,
        base_municipal=base, fila_municipal=Fila.query.filter(~Fila.status.in_(['concluida', 'cancelada'])).all(),
        faixas_incompletas=[(r, d) for r, d in incompletas if d['erro']])


def decidir(item_id):
    validar_csrf()
    a = Sugestao.query.filter_by(pendencia_id=item_id).first_or_404()
    S.conferir_versao(a)
    if a.pendencia.status != 'aberta' or a.decisao:
        abort(409, description='Sugestão já encerrada. Recarregue a página.')
    responsavel = request.form.get('responsavel', '').strip()
    justificativa = request.form.get('justificativa', '').strip()
    decisao = request.form.get('decisao')
    if not 2 <= len(responsavel) <= 120 or len(justificativa) > 500 or decisao not in ('vincular', 'dispensar'):
        abort(400, description='Informe o responsável (2 a 120 caracteres) e uma decisão válida. Justificativa: até 500 caracteres.')
    if request.form.get('confirmar') != 'sim':
        abort(400, description='Confirme a revisão da sugestão e de suas limitações.')
    if not disponivel(a.cerca) or not disponivel(a.rotograma):
        abort(409, description='Cerca ou rotograma inativo/excluído. Recarregue a página.')
    if request.form.get('cerca_versao', type=int) != a.cerca.versao or request.form.get('rotograma_versao', type=int) != a.rotograma.versao:
        abort(409, description='Cadastro alterado desde a abertura da página. Recarregue e revise.')
    base = obter_base()
    if origem_mudou(a, base):
        abort(409, description='O município da nova cerca mudou. Recarregue a página.')
    referencia = evidencias(a.cerca, base).get(a.rotograma_id)
    if not referencia:
        abort(409, description='O vínculo já existe ou a referência municipal não está mais disponível. Recarregue a página.')
    if a.motivo['tipo'] == 'faixa' and (a.motivo.get('faixa') or {}).get('contexto') != (referencia[1].get('faixa') or {}).get('contexto'):
        abort(409, description='A localização ou a faixa mudou desde a sugestão. Recarregue e reavalie os dados antes de decidir.')
    # Protege a decisão de edições/inativações concorrentes dos três cadastros.
    a.cerca.versao += 1; a.rotograma.atualizado_em = S.agora_utc()
    if referencia[1].get('referencia_id'):
        ref = db.session.get(S.Cerca, referencia[1]['referencia_id']); ref.versao += 1
    if decisao == 'vincular':
        db.session.add(S.RotogramaCerca(rotograma_id=a.rotograma_id, cerca_id=a.cerca_id))
        S.registrar_historico('vinculo_cerca', a.cerca_id, (a.cerca.nome + ' | ' + a.rotograma.nome)[:180],
            'vinculo_cerca', 'não vinculado', 'Vínculo confirmado na sugestão municipal por ' + responsavel, 'inclusao_vinculo')
    a.responsavel = responsavel; a.justificativa = justificativa or None
    a.decisao = 'vinculada' if decisao == 'vincular' else 'dispensada'; a.decidida_em = S.agora_utc()
    a.pendencia.status = 'concluida'; a.pendencia.concluida_em = a.decidida_em
    registrar(a, 'decisao_municipal', 'aberta', json.dumps({'decisao': a.decisao, 'responsavel_informado': responsavel,
        'justificativa': justificativa, 'evidencia_revalidada': referencia[1]}, ensure_ascii=False))
    db.session.commit()
    flash('Decisão registrada. ' + ('Cerca vinculada ao rotograma.' if decisao == 'vincular' else 'Sugestão dispensada.'), 'sucesso')
    return redirect(url_for('listar_notificacoes', cerca_id=a.cerca_id, status='todas', _anchor='cerca-' + str(a.cerca_id)))


def repetir():
    validar_csrf()
    base = obter_base()
    for fila in Fila.query.filter(~Fila.status.in_(['concluida', 'cancelada'])).all():
        gerar(fila.cerca, base)
    db.session.commit()
    flash('Pendências técnicas reavaliadas com a base local disponível.', 'info')
    return redirect(url_for('listar_notificacoes'))


def comando_atualizar():
    try:
        base = municipios.atualizar(app.config.get('MUNICIPIOS_ARQUIVO'))
    except Exception as exc:
        raise click.ClickException('Não foi possível atualizar a base IBGE. A base anterior e os cadastros foram preservados. ' + type(exc).__name__)
    S.atualizar_estrutura()
    b = obter_base()
    for fila in Fila.query.filter(Fila.status != 'cancelada').all():
        gerar(fila.cerca, b)
    db.session.commit()
    click.echo(f"Base IBGE atualizada: {len(base['municipios'])} municípios. Nenhum vínculo criado automaticamente.")
