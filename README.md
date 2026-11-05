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


## Em desenvolvimento — sugestões municipais (v2.2)

Branch: `feature/integracao-api`. A `main` continua na versão 2.0. Esta atualização
não reinstala a integração ORS anterior e não importa o GeoJSON da empresa.

Ao cadastrar uma nova cerca ativa, o sistema procura rotogramas ativos que já
possuem cercas ativas e não excluídas no mesmo município/UF ou em municípios que
compartilham um segmento de divisa. A relação geográfica gera uma **notificação por nova cerca**, reunindo os rotogramas sugeridos em
**Notificações**; nunca confirma a rota real nem cria vínculos automaticamente.
Rotogramas sem cercas vinculadas nesses municípios não são identificados.

A nova cerca gera no máximo uma sugestão atual por rotograma. Várias cercas de
referência não multiplicam notificações. Um reprocessamento não reabre uma decisão
concluída para o mesmo município da cerca. Cadastros antigos não são incluídos em
massa: a migração cria apenas as duas tabelas novas, sem gerar sugestões retroativas.

### Conferir uma sugestão

1. Abra **Notificações**, pelo menu ou pelo aviso no Dashboard. Cada cerca possui um alerta com todos os rotogramas sugeridos.
2. Na notificação da cerca, veja os rotogramas sugeridos, a relação de mesma cidade ou divisa e a cerca de referência de cada sugestão. Abra **Analisar este rotograma**.
3. Informe o responsável e, opcionalmente, uma justificativa.
4. Confirme a revisão e escolha **Confirmar vínculo da cerca** ou **Dispensar sugestão**.
5. Consulte as decisões no filtro **Concluídas** em Notificações e no histórico, tipo
   **Sugestao Municipal**. Decisão, nome informado, data UTC, justificativa e a
   evidência revalidada ficam registrados. Não existe autenticação de identidade
   nesta versão: o responsável é informado pelo próprio operador.

As ações novas têm token CSRF e controle de versão. Cercas/rotogramas inativos ou
excluídos não podem confirmar sugestões; alterações de município e remoção da
referência encerram sugestões que perderam a justificativa. Um vínculo feito pelo
fluxo manual também encerra a sugestão como vínculo já existente. Decisões são
atômicas com o vínculo e o histórico. Pendências cadastrais anteriores mantêm seu
fluxo de verificação em **Pendências**, sem sugestões municipais nessa lista.
Cada decisão conclui somente o rotograma analisado; o alerta da cerca permanece
aberto até todas as sugestões serem concluídas. O menu e o Dashboard contam
notificações por cerca, enquanto cada alerta informa os rotogramas ainda abertos.
As sugestões antigas já salvas são agrupadas automaticamente, sem apagar histórico
ou recriar dados. Há filtros por situação e busca por cerca, município ou rotograma.

### API e base local

`dados/municipios_ibge.json.gz` acompanha o projeto: 5.571 municípios na consulta de
Localidades utilizada. A lista de vizinhos foi derivada da malha TopoJSON nacional
simplificada do IBGE, identificando arcos de divisa compartilhados, inclusive entre
UFs. Contato apenas por ponto, distância entre sedes e proximidade de estrada não
são tratados como divisa. A consulta da malha retornou 5.570 geometrias: Boa Esperança
do Norte/MT não estava representada. Um arco ambíguo compartilhado por três áreas
foi excluído da inferência e os municípios envolvidos sinalizados para revisão.
A base registra data de obtenção, fontes e cobertura por município. Ela é auxiliar,
não uma certificação dos limites municipais atuais.

Fontes públicas (sem chave):
- https://servicodados.ibge.gov.br/api/docs/localidades
- https://servicodados.ibge.gov.br/api/docs/malhas?versao=3

Para atualizar a base, execute **atualizar_municipios.bat** no servidor ou:

```powershell
.\.venv\Scripts\python.exe -m flask --app app atualizar-municipios
```

O download usa somente os endereços públicos fixos do IBGE; não envia cadastros da
empresa. A substituição da base é atômica: falhas de rede/validação mantêm o arquivo
anterior. Cercas novas usam o banco e a base local, sem chamadas de rede no cadastro.
Se a base estiver ausente/inválida, a comparação textual normalizada de Cidade/UF
continua e a vizinhança fica pendente. Grafias não encontradas e cobertura incompleta
aparecem em **Notificações**, com atalho para corrigir o cadastro e reprocessar.

Use o nome oficial do município e a UF. A comparação ignora acentos, caixa e espaços
repetidos, mas não adivinha abreviações, distritos ou erros de digitação. Município
vizinho significa divisa na malha utilizada, não distância real entre cercas.

### Atualização e validação

Feche o servidor, execute **atualizar.bat** e depois **iniciar.bat**. A migração
`20261029_02` é aditiva e preserva o banco existente. `BACKUP_ANTES_MIGRACAO=0` desativa
o backup automático de migração em SQLite quando isso for desejado; o padrão é 1.
Configurações e bases com dados de usuários continuam fora do Git. A chave ORS antiga
não é usada nesta funcionalidade.

Execute os testes com `.\.venv\Scripts\python.exe -m unittest discover -s tests -q`.
Os testes usam banco em memória e não fazem chamadas de API. A implantação em MySQL
requer validação da migração em seu ambiente específico.


## Faixa direta com pontas arredondadas — testes na mesma branch

A faixa acrescenta uma terceira forma de sugerir rotogramas, sem consultar estradas:
um ponto de cerca é comparado ao segmento direto entre origem e destino, com um
raio ao redor de todo o segmento e das pontas (cápsula). O modelo de distância é
esférico, em quilômetros, com raio terrestre médio de 6.371,0088 km; não é cálculo
rodoviário nem levantamento geodésico de precisão.

### Como testar Santos → Goiânia / Araras

1. Crie ou edite um rotograma com Origem **Santos**, UF **SP**, Destino **Goiânia**,
   UF **GO**. Ative **sugestões pela faixa deste rotograma** e informe raio **40 km**.
2. Na consulta do rotograma, confira o esquema da faixa e a precisão dos extremos.
3. Cadastre uma **nova cerca ativa em Araras/SP**. Coordenadas da cerca são opcionais,
   mas são preferíveis quando conhecidas. A ausência de cercas previamente vinculadas
   ao rotograma não impede a comparação pela faixa.
4. Abra **Notificações**: o rotograma aparecerá se o ponto usado para a nova cerca
   estiver dentro da faixa. O motivo informa distância à linha, raio e precisão.
5. Analise e confirme o vínculo ou dispense. Nada é vinculado automaticamente.

Com os centros aproximados da base distribuída, Araras ficou a aproximadamente
31,68 km da linha direta Santos–Goiânia: entra em 40 km, mas não em 30 km. Coordenadas
mais precisas podem produzir outro resultado. Isso é um teste geométrico, não uma
confirmação de passagem pela cidade ou pela cerca.

### Coordenadas e limites

- Cercas aceitam latitude/longitude opcionais. Origem/destino também têm UF e pares
  opcionais de coordenadas. Os pares devem estar completos, finitos e dentro dos
  intervalos geográficos; o formulário aceita ponto ou vírgula decimal.
- Coordenadas informadas têm prioridade. Sem elas, a base local inclui o centro do
  retângulo envolvente da extensão municipal, derivado da malha IBGE. Esse ponto
  pode estar longe da sede urbana ou da cerca: é apenas uma referência aproximada,
  não geocodificação de endereço e não localização exata.
- Nomes oficiais completos são reconhecidos com UF. Sem UF, somente nomes exatos
  e não ambíguos são aceitos. Textos como `GUARIBA/SP (BONFIM)` permitem identificar
  o município, mas não o terminal. Textos livres não reconhecidos ficam sinalizados;
  use coordenadas para identificar o local efetivo.
- A base contém centros aproximados de 5.570 municípios. Atualize-a com
  **atualizar_municipios.bat**. Sem base ou cobertura, coordenadas informadas ainda
  permitem calcular a faixa, enquanto as comparações municipais podem ficar pendentes.
- O raio é configurável por rotograma, maior que zero e até 200 km. O padrão é 30 km
  (`FAIXA_RAIO_KM=30` no servidor). Raio de 30 km significa até 30 km para cada lado
  e nas pontas, resultando em cerca de 60 km de largura na parte central.
- Rotogramas anteriores à migração ficam com a faixa desativada até que seja ativada
  na edição. Novos formulários já oferecem a opção marcada. Não existe vínculo ou
  alerta retroativo em massa de cercas antigas sem histórico de comparação.
- Configurações e coordenadas relevantes alteradas revalidam as sugestões. Decisões
  concluídas para uma faixa idêntica não são reabertas. Mudança material na faixa
  de uma sugestão geométrica pode gerar nova análise, preservando o histórico anterior.
- Uma relação municipal e a faixa no mesmo rotograma resultam em uma única sugestão,
  com os motivos disponíveis. Inativações, vínculos manuais e decisões continuam
  protegidos por revalidação e controle de versão.

Na opção de faixa reta, não é necessário fornecer chave ORS. Na opção por estradas,
a integração descrita abaixo envia as localizações necessárias ao OpenRouteService. A importação do GeoJSON continua sendo
uma funcionalidade separada; este incremento não importa o arquivo da empresa.

Feche o servidor, execute **atualizar.bat** e **iniciar.bat**. A migração aditiva
`20261029_03` acrescenta os campos sem substituir o banco ou recriar dados. Colunas
compatíveis que já existam de testes anteriores são reaproveitadas. MySQL deve ser
validado no ambiente de implantação.


## Percurso editável pelas estradas — atualização de 05/11/2026

No cadastro/edição, selecione **Rota pelas estradas com ajustes no mapa**. Informe
origem/destino e UF e clique em **Calcular rota**. Uma nova origem/destino também
agenda o cálculo ao terminar de preencher o campo. Clique na linha para acrescentar
um ponto de passagem e arraste o marcador. Soltar o marcador recalcula o percurso.
Os marcadores O/D também podem ser arrastados, preenchendo as coordenadas dos extremos.
Remova passagens pela lista abaixo do mapa. Até 48 passagens intermediárias.

Escolha a margem em **Raio da faixa (km)**. Por exemplo, 0,5 significa 500 metros
para cada lado do percurso e nas pontas. O padrão oferecido para novos cadastros
é 2 km. A margem muda a área sombreada sem chamar a API. O contorno desenhado
é uma aproximação visual. A análise calcula a menor distância geográfica aos
segmentos do percurso completo, sem simplificá-lo.

**Salvar rotograma** confirma o percurso e suas passagens. Alterar origem/destino
exige novo cálculo antes de salvar no modo por estradas. O histórico registra a
troca do percurso e da margem. As notificações em aberto são reavaliadas.
Os vínculos continuam dependendo da confirmação do usuário.

Para rotogramas em modo por estradas, a sugestão depende exclusivamente da faixa
do percurso salvo. Relações de mesma cidade/vizinhança não contornam esse filtro.
Rotogramas existentes continuam no modo anterior até a edição explícita.
Não há conversão ou recálculo automático em massa dos percursos existentes.

Configure `ORS_API_KEY` no `.env` local e mantenha `ROTAS_ENABLED=1`. A chave
fica no servidor e não aparece no HTML nem é enviada ao navegador. São enviados
ao OpenRouteService apenas os nomes municipais para localizar os extremos e as
coordenadas dos extremos/passagens para calcular o percurso. As análises de novas
cercas usam o banco local e não fazem chamadas à API.

O cache de trajetos dura 7 dias para novos cálculos idênticos. A localização de
cidades fica em cache por 180 dias. Percursos já aprovados permanecem salvos e
não expiram nem são substituídos por atualização do cache. Os limites locais
`ROTAS_LIMITE_DIA=500` e `ROTAS_LIMITE_MINUTO=10` contam consultas externas de
localização e percurso. Ajuste-os conforme as cotas efetivas da sua conta ORS.
Não há repetição automática de consultas que falharem.

Sem conexão/cota/chave, o cálculo mostra um aviso e não salva um percurso incompleto.
É possível manter um percurso previamente aprovado sem recalculá-lo ou escolher a
faixa reta para concluir o cadastro. Os cadastros de cercas continuam funcionando.

Coordenadas dos extremos têm prioridade. Sem elas, cidades reconhecidas na base
IBGE são buscadas no geocodificador ORS com validação de nome, UF e país. Cidades
ambíguas precisam de coordenadas. Essa posição é aproximada. Cercas e postos sem
coordenadas continuam aparecendo pelo centro aproximado municipal, e podem estar
longe do local efetivo. Use coordenadas de cercas para margens estreitas.

O perfil Caminhão é uma estimativa, sem parâmetros particulares de peso, altura
ou carga. Não use esta ferramenta como autorização de circulação ou navegação.

Feche o servidor e execute `atualizar.bat` e `iniciar.bat`. A migração aditiva
`20261105_04` acrescenta o percurso JSON, a seleção de modo e as tabelas técnicas
de cache/limites. Não exclui cadastros, vínculos ou históricos. A interface usa
Leaflet 1.9.4, Turf 7.2.0 e tiles OpenStreetMap. Internet é necessária para o
mapa de fundo e novos cálculos. Nenhum pacote Python adicional é necessário.

Testes em memória: `.venv\Scripts\python.exe -m unittest discover -s tests`.
