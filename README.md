# Gestão de Rotogramas — v2.1.0

Aplicação interna em Python, Flask e SQLAlchemy para gerenciar cercas, postos,
rotogramas, vínculos, validade, histórico e pendências. Não executa nem monitora
rotogramas. Compatível com SQLite e preparada para MySQL via PyMySQL.

Consulte [CHANGELOG.md](CHANGELOG.md) para a descrição da atualização.

## Instalação no Windows

Requisitos: Python 3.10 ou superior e internet para instalar dependências.

1. Baixe o projeto em **Code > Download ZIP** e extraia a pasta completa.
2. Execute **instalar.bat** e aguarde a confirmação.
3. Execute **iniciar.bat**. No primeiro uso, o terminal solicita login, nome e senha do administrador. A senha precisa ter pelo menos 10 caracteres e não aparece ao digitar.
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

Configurar HTTPS, políticas de acesso e recuperação de contas,
backup e restauração e monitoramento conforme o ambiente da empresa. A versão 2.1 adiciona login individual, administração de usuários e proteção CSRF. Registros antigos não recebem autoria inventada; eventos novos identificam usuário ou sistema. A fila continua compartilhada.

## Análises geográficas de novas cercas

A versão 2.1 usa o OpenRouteService apenas como auxílio para análise humana.
Cadastros e vínculos existentes permanecem preservados. Novas cercas ativas entram
em uma fila persistente por rotograma ativo; cercas antigas precisam ser incluídas
explicitamente por **Consultar cerca > Solicitar análise geográfica**. Novos
rotogramas e mudanças de localização, origem/destino ou parâmetros reavaliam os
pares habilitados. Campos de latitude/longitude são opcionais e devem ser
preenchidos em pares; no formato ORS a ordem é longitude, latitude.

A distância é a menor distância geodésica aproximada aos segmentos do percurso,
não apenas aos extremos. A margem inicial é 10 km e pode ser configurada. O
trajeto driving-hgv é estimado: sem dados específicos do veículo e pontos
intermediários ele pode diferir do percurso real. O ponto da cidade não representa
o perímetro da cerca nem toda a área do município. Ausência de correspondência
não comprova que uma cerca não pertença ao rotograma.

### Ativar a API no servidor

Copie `.env.example` para `.env` somente se esse arquivo ainda não existir; caso
exista, acrescente as variáveis sem sobrescrever sua configuração do banco.

```env
ORS_ENABLED=1
ORS_API_KEY=SUA_CHAVE_LOCAL
ORS_RAIO_KM=10
ORS_CACHE_DIAS=30
```

Não coloque a chave no código, na interface, em prints ou no GitHub. A chave usada
na prova de conceito não foi incluída na instalação. Reinicie o servidor após
mudar `.env`. Somente o servidor central precisa de acesso HTTPS ao provedor.
A API recebe coordenadas e consultas de localização; não recebe usuários, nomes
de cercas, histórico ou identificação de rotogramas.

A fila geográfica tem uma thread própria, independente da validade, e é verificada
a cada 10 segundos enquanto o servidor roda. Ela persiste tarefas, repete falhas
transitórias com espera crescente e pausa para revisão após cinco falhas. Sem
chave, com API indisponível ou sem cota, o cadastro continua funcionando. A tela
mostra situação técnica e quantidade concluída, distinguindo processamento parcial
de comparação concluída sem proximidade.

O cache de geocodificações é compartilhado por consulta normalizada e UF. Textos
livres sem UF estruturada, localizações com mais de um candidato e resultados de
baixa confiança precisam de confirmação em **Análises de cercas > Confirmar
localização**. Alternativamente, forneça coordenadas conhecidas no cadastro.
A escolha compartilhada registra quem a confirmou.

Trajetos ficam no banco com geometria, coordenadas, perfil, data, validade e
atribuição. Novas comparações reutilizam o cache vigente. Um recálculo cria uma
nova versão de trajeto e preserva os anteriores referenciados pelas decisões.
Ao tentar decidir sobre um trajeto vencido, o sistema solicita nova comparação.
Use **Tentar novamente** na fila para uma reavaliação explícita.

A rotina usa uma concessão no banco para coordenar instâncias e limita os lotes.
Por padrão reserva no máximo uma requisição por endpoint a cada 2,1 segundos e
orçamentos conservadores locais de 1.000 Directions e 500 Geocoding por janela de
24 horas. Ajuste apenas após conferir as cotas reais no painel HeiGIT. Respeita
saldo/reset informados pela API, erros de permissão e limite; não usa múltiplas
chaves para contornar cotas.

### Concluir uma análise

1. Abra **Análises de cercas** ou a categoria correspondente em **Alertas atuais**.
2. Confira cerca, rotograma, distância aproximada, fonte e data do trajeto.
3. Marque a confirmação de conferência e escolha **Confirmar vínculo da cerca**
   ou **Dispensar análise**, com justificativa opcional.
4. A decisão registra usuário autenticado, data e justificativa. Ao vincular,
   também usa o histórico e a pendência de verificação já existentes.

O sistema nunca vincula automaticamente. Há uma análise atual por par e histórico
das decisões. Rodar novamente com o mesmo contexto não reabre uma dispensa.
Alterações relevantes invalidam sugestões antigas e podem gerar nova revisão.
Itens inativos/excluídos e telas desatualizadas não podem confirmar vínculos.

### Usuários e primeiro acesso

Não existe usuário ou senha padrão. **iniciar.bat** prepara o primeiro acesso no
terminal antes de abrir o servidor. Também é possível executar
**configurar_acesso.bat** ou:

```powershell
.\.venv\Scripts\python.exe -m flask --app app preparar-acesso
.\.venv\Scripts\python.exe -m flask --app app criar-usuario
```

Depois, administradores criam, desativam e redefinem senhas em **Usuários**.
Desativação ou redefinição revoga sessões anteriores. Contas são preservadas para
manter autoria. Há limitação de tentativas de login e senhas são armazenadas como
hashes. Uma chave de sessão local é gerada em `instance/secret.key` quando não há
SECRET_KEY própria. Preserve esse arquivo, mantenha-o fora do Git e use
COOKIE_SECURE=1 na implantação com HTTPS. A proteção CSRF cobre todos os POSTs.

A integração é desativada por padrão até configurar chave e ORS_ENABLED. Não foram
feitas consultas reais com dados da empresa durante o desenvolvimento. Os testes
de integração usam respostas simuladas e bancos temporários; a prova real anterior
utilizou apenas cidades públicas de demonstração. Para MySQL, valide a migração
em uma cópia do ambiente antes de atualizar o servidor.
