# Gestão de Rotogramas | MVP

Aplicação interna inicial em Python + Flask + SQLAlchemy, preparada para MySQL.

## O que já está implementado

- Dashboard com contagem de cercas, postos, rotogramas e pendências abertas.
- Cadastro, edição e ativação/inativação de cercas, postos e rotogramas.
- Vínculo de várias cercas e postos a cada rotograma, com proteção contra duplicidade.
- Histórico de alterações cadastrais.
- Histórico de inclusão e remoção de vínculos.
- Uma pendência individual por alteração histórica e por rotograma afetado.
- Conclusão explícita de pendência com data/hora.
- Consulta de histórico e filtro de pendências por status.

## Melhorias da interface e consultas

- Modos claro e escuro, com preferencia salva no navegador.
- Pesquisa pelo nome do posto ao associar a um rotograma.
- Ordenacao alfabetica A-Z e buscas sem diferenciar maiusculas ou acentos.
- Bloqueio de nomes duplicados nos cadastros e edicoes, incluindo registros inativos.
- Tipos de posto: Refeicao, Refeicao/Pernoite, Abastecimento,
  Abastecimento/Refeicao/Pernoite e Abastecimento/Refeicao.
- Filtros combinados de postos por rotograma, tipo, cidade, UF e status.
- Filtros de cercas por rotograma, tipo e status.
- Consulta de postos e cercas sem vinculo com rotogramas.
- Filtros de rotogramas por status e por pendencias abertas.
- Contagem de resultados e botao para limpar filtros.
- Alteracoes no tipo do posto tambem geram historico e pendencias.

## Instalacao rapida no Windows

1. Baixe o repositorio em **Code > Download ZIP** e extraia a pasta completa.
2. Com Python 3.10 ou superior instalado e internet, execute `instalar.bat`.
3. Apos a instalacao, execute `iniciar.bat`.
4. Abra <http://127.0.0.1:5000> e mantenha a janela do servidor aberta.

O instalador prepara `.venv` e instala as dependencias. Nao copie ambientes
virtuais entre computadores. Se `python` nao estiver disponivel no terminal,
verifique a instalacao ou use o comando `py`.

O banco SQLite e criado automaticamente em `instance/rotogramas.db` no primeiro
inicio. Cada computador possui sua propria copia dos dados, sem sincronizacao.
O repositorio nao inclui bancos, cadastros reais, arquivos `.env` ou ambientes
virtuais. Para transferir cadastros entre computadores, feche o sistema e copie
separadamente a pasta `instance`, preservando antes uma copia de seguranca do destino.

Ao iniciar com `python app.py`, a coluna de tipo de posto e adicionada
automaticamente a bancos antigos, preservando os registros existentes. Em outros
modos de inicializacao, execute antes `python -m flask --app app atualizar-banco`.
Postos antigos aparecem com tipo nao informado ate serem classificados na edicao.

## Requisitos

- Python 3.10 ou superior
- MySQL 8 (para o uso previsto) ou SQLite para avaliação local

## Executar localmente com SQLite

1. Abra o terminal na pasta do projeto.
2. Crie um ambiente virtual:

   ```bash
   python -m venv .venv
   ```

3. Ative o ambiente virtual.

   Windows PowerShell:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

   macOS/Linux:

   ```bash
   source .venv/bin/activate
   ```

4. Instale as dependências:

   ```bash
   pip install -r requirements.txt
   ```

5. Inicie a aplicação:

   Windows PowerShell:

   ```powershell
   $env:FLASK_DEBUG="1"
   python app.py
   ```

   macOS/Linux:

   ```bash
   FLASK_DEBUG=1 python app.py
   ```

6. Acesse `http://127.0.0.1:5000`.

Sem `DATABASE_URL`, a aplicação utiliza `sqlite:///rotogramas.db` e cria as tabelas automaticamente ao iniciar.

## Configurar MySQL

1. Crie o banco:

   ```sql
   CREATE DATABASE rotogramas
     CHARACTER SET utf8mb4
     COLLATE utf8mb4_unicode_ci;
   ```

2. Copie `.env.example` para `.env`.
3. Atualize `DATABASE_URL` com usuário, senha e host do seu MySQL.

   Exemplo:

   ```env
   DATABASE_URL=mysql+pymysql://usuario:senha@localhost:3306/rotogramas
   SECRET_KEY=coloque-uma-chave-aleatoria-longa-aqui
   FLASK_DEBUG=0
   ```

4. Execute `python app.py`. As tabelas serão criadas automaticamente nesta versão inicial.

## Regras implementadas

- Alterações em campos de cercas e postos geram histórico e pendências para todos os rotogramas vinculados.
- Cada campo alterado é um evento de histórico independente. Portanto, se dois campos forem alterados numa mesma gravação, serão criadas duas pendências por rotograma vinculado.
- Alterações dos dados gerais do rotograma ficam no histórico, mas não geram pendências.
- Inclusão ou remoção de vínculo gera histórico e uma pendência para o rotograma cuja composição mudou.
- Visualizar uma pendência não a conclui. É preciso clicar em **Marcar como verificada**.
- A aplicação não registra o usuário responsável, conforme requisito definido.

## Antes de usar em produção

Esta é uma primeira versão para desenvolvimento, não uma implantação pronta para produção. Antes de disponibilizar a aplicação na rede, implementar autenticação e autorização, proteção CSRF em formulários, logs técnicos, backup e restauração, migrações de banco (ex.: Flask-Migrate), testes automatizados e configuração segura de produção. Não use o servidor de desenvolvimento do Flask em produção.

Também vale revisar a política de pendências caso existam muitos usuários: nesta versão, a pendência é uma fila compartilhada do sistema e qualquer usuário com acesso poderá concluí-la.
