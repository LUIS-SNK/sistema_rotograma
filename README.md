# Gestão de Rotogramas — v2.0.0

Aplicação interna em Python, Flask e SQLAlchemy para gerenciar cercas, postos,
rotogramas, vínculos, validade, histórico e pendências. Não executa nem monitora
rotogramas. Compatível com SQLite e preparada para MySQL via PyMySQL.

Consulte [CHANGELOG.md](CHANGELOG.md) para a descrição da atualização.

## Instalação no Windows

Requisitos: Python 3.10 ou superior e internet para instalar dependências.

1. Baixe o projeto em **Code > Download ZIP** e extraia a pasta completa.
2. Execute **instalar.bat** e aguarde a confirmação.
3. Execute **iniciar.bat**.
4. Abra <http://127.0.0.1:5000> e mantenha a janela aberta.

A instalação cria `.venv`. O banco SQLite é criado em `instance/rotogramas.db`.
Ambientes virtuais não devem ser copiados entre computadores. O repositório não
inclui cadastros reais, bancos, credenciais ou arquivos `.env` locais.

### Atualizar uma instalação existente

1. Pare o servidor e faça uma cópia da pasta `instance` e do arquivo `.env`, se houver.
2. Substitua os arquivos do programa pela nova versão, preservando `instance` e `.env`.
3. Execute **atualizar.bat**. Ele instala as dependências e aplica a migração.
4. Execute **iniciar.bat** e atualize o navegador com Ctrl + F5.

A migração também é aplicada na inicialização padrão e cria um backup prévio do
SQLite em `instance/backups` quando há uma revisão pendente. Não há remoção de
dados. Para MySQL, faça backup externo antes de migrar. Não execute migrações
simultaneamente em vários processos. O downgrade destrutivo é bloqueado; para
restaurar uma versão anterior, use código e backup compatíveis.

## Validade e situações dos cadastros

- Postos e rotogramas novos exigem data de referência manual.
- Vencimento = referência + 24 meses de calendário. 29/02/2024 vence em 28/02/2026.
- Datas futuras não são aceitas; datas retroativas podem produzir um registro vencido.
- O vencimento começa no início da data calculada, no fuso America/Sao_Paulo.
- O alerta começa um mês de calendário antes, não necessariamente 30 dias.
- Postos ativos vencidos são inativados automaticamente, com histórico e motivo.
- Rotogramas vencidos são apenas sinalizados: sua inativação automática não foi adotada.
- Regularização exige uma referência que resulte em validade vigente.
- Regularizar reativa postos inativados por vencimento, mas respeita inativações manuais.
- Manter inativo é uma decisão explícita e não exige regularização imediata.
- Atividade, validade, exclusão e pendências são informações separadas.

Registros antigos continuam sem referência até preenchimento posterior. Não são
usadas datas de criação como referência. Cercas antigas não recebem localização
fictícia. A criação no sistema continua preservada para auditoria. Datas e horários
de auditoria são armazenados/exibidos em UTC; datas de validade usam São Paulo.

## Verificador interno — sem Agendador de Tarefas

`iniciar.bat` executa `servidor.py`, que prepara o banco, processa vencimentos
pendentes e inicia o servidor Waitress e uma thread interna. A rotina repete a
checagem a cada 900 segundos (15 minutos), mesmo sem acessos pelo navegador.

O computador e o processo precisam estar funcionando. Ao reiniciar, o sistema
recupera os vencimentos ocorridos enquanto estava desligado. Operações de vínculo
também verificam a validade, sem esperar o próximo ciclo. A concessão no banco e
as versões dos registros protegem contra processamento concorrente.

Comandos alternativos:

```powershell
.\.venv\Scripts\python.exe servidor.py
.\.venv\Scripts\python.exe -m flask --app app atualizar-banco
.\.venv\Scripts\python.exe -m flask --app app verificar-validade
```

`python app.py` também ativa o verificador, com servidor de desenvolvimento e sem
reloader. Para produção, prefira `servidor.py`. Se usar WSGI próprio, inicialize
pela factory `app:criar_aplicacao` (por exemplo, `waitress-serve --call app:criar_aplicacao`).
A importação simples `app:app` ou `flask run` não inicia a rotina interna.
A configuração padrão pressupõe uma instância central; clientes acessam pelo navegador.

## Alertas e pendências

**Alertas atuais** são calculados a partir dos dados atuais e não possuem botão
para ocultar problemas ainda existentes. Incluem validade e composição dos
rotogramas. Corrigir a causa ou remover o vínculo explicitamente resolve o aviso.
Cada elemento indisponível gera um aviso por rotograma, sem duplicação.

**Pendências de verificação** são os eventos históricos já existentes. Continuam
sendo concluídas manualmente e não desaparecem ao regularizar um cadastro.
Um rotograma pode estar ativo, ter validade vencida e ter vários problemas de
composição ao mesmo tempo; cada condição é mostrada separadamente.

## Exclusão e concorrência

A exclusão é lógica: requer confirmação, mostra vínculos afetados, mantém todos
os registros e relacionamentos e bloqueia novos vínculos. Excluídos são acessíveis
pelo filtro de situação. Dependências continuam sinalizadas até o vínculo ser
tratado pelo usuário. Não há exclusão física nem restauração automática.

Formulários e ações usam controle de versão. Uma tela desatualizada não pode
sobrescrever silenciosamente uma alteração feita por outro usuário ou pelo
verificador. Em conflito, volte para recuperar os dados digitados, compare com
uma aba atualizada e tente novamente. Operações de banco são transacionais.

## Cercas, buscas e aparência

- Cidade e UF obrigatórias em novas cercas, com 27 siglas oficiais.
- Cercas antigas podem continuar sem localização; ao preencher, informe Cidade e UF juntas.
- Localização Cidade – UF nas consultas e na composição do rotograma.
- Histórico e pendências para alterações de localização, sem modificar vínculos.
- Filtros combináveis por status, tipo, localização, rotograma e validade.
- Rotogramas filtráveis por verificações abertas e por problemas atuais de composição.
- Pesquisa de postos ao vincular, nomes em A–Z, busca sem diferenças de acentos ou caixa.
- Nomes duplicados bloqueados; temas claro e escuro com preferência no navegador.

## Configuração e banco

Sem `.env`, utiliza SQLite local. Cada computador com uma instalação separada
possui seus próprios dados, sem sincronização. Para uso compartilhado, hospede uma
instância central e configure o acesso da equipe conforme a política da empresa.

Copie `.env.example` para `.env` somente se precisar personalizar a configuração.
Não publique credenciais. Exemplo de MySQL:

```env
DATABASE_URL=mysql+pymysql://USUARIO:SENHA@localhost:3306/rotogramas
SECRET_KEY=SUBSTITUA-POR-UMA-CHAVE-ALEATORIA
INTERVALO_VERIFICACAO_SEGUNDOS=900
HOST=127.0.0.1
PORT=5000
```

Crie o banco MySQL com utf8mb4 antes de executar a migração. A suíte foi executada
em SQLite; é necessário validar migração e concorrência no MySQL do ambiente antes
de adotá-lo. `DESATIVAR_VERIFICADOR=1` é reservado para testes ou implantação com
outro processo central responsável; não o utilize na instalação padrão.

## Testes

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Os testes usam bancos temporários e verificam datas, bissextos, notificações,
regularização, exclusão, vínculos, concorrência e migrações sem alterar os cadastros
reais. O módulo `tests/test_validade.py` contém os cenários desta atualização.

## Antes de disponibilizar em produção

Configurar autenticação/autorização, proteção CSRF, chave secreta segura, HTTPS,
backup e restauração e monitoramento conforme o ambiente da empresa. Login e
permissões não foram adicionados nesta atualização. O histórico não identifica
usuários individuais, e a fila de verificações continua compartilhada.
