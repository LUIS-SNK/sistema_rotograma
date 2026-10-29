# Histórico de versões

## 2.2.0 — em teste na branch feature/integracao-api

- Notificações agrupadas por nova cerca, com todos os rotogramas sugeridos por mesmo município ou divisa municipal.
- Tela própria de Notificações, com alerta no Dashboard, contador por cerca, filtros e busca.
- Decisões independentes por rotograma; alerta encerrado somente após concluir todas as sugestões.
- Pendências cadastrais preservadas em sua lista original, sem sugestões municipais misturadas.
- Base local padronizada por código IBGE, obtida das APIs públicas de Localidades e Malhas.
- Atualização da base por comando/BAT, preservando a base anterior em falhas.
- Confirmação manual de vínculo ou dispensa, com responsável informado, justificativa e histórico.
- Deduplicação, revalidação de referências, controle de concorrência e CSRF nas decisões novas.
- Cobertura municipal incompleta e grafia não encontrada sinalizadas sem bloquear cadastro.
- Migração aditiva; sem importação de GeoJSON ou sugestões retroativas em massa.
- Botão de tema apenas no Dashboard; preferência mantida nas demais telas.


## 2.0.0 — 28/10/2026

### Validade e regularização
- Data de referência manual em postos e rotogramas, independente da criação.
- Vencimento calculado em 24 meses de calendário, com tratamento de 29 de fevereiro.
- Referências futuras são rejeitadas; referências retroativas são aceitas.
- Avisos a partir de um mês de calendário antes do vencimento.
- Regularização com nova referência e auditoria; respeita inativações manuais.
- Rotogramas vencidos são sinalizados, sem inativação automática.

### Verificação interna e alertas
- Verificação na inicialização e a cada 15 minutos, sem Agendador de Tarefas.
- Funciona enquanto o servidor estiver executando, mesmo sem usuários conectados.
- Recupera vencimentos ocorridos enquanto o servidor estava desligado.
- Inativa postos vencidos e registra data, operação e motivo no histórico.
- Concessão no banco e controle de versão impedem processamento concorrente indevido.
- Alertas atuais calculados sem duplicação; atualização ao corrigir a causa.
- Pendências de composição identificam cada posto ou cerca inativo, vencido ou excluído.
- Verificações manuais anteriores continuam independentes e não são encerradas automaticamente.

### Gestão e interface
- Exclusão lógica com confirmação, visualização dos vínculos afetados e preservação do histórico.
- Registros excluídos ficam fora das listas padrão e indisponíveis para novos vínculos.
- Filtros de validade, excluídos, motivos de inativação e problemas de composição.
- Cidade e UF nas cercas, obrigatórias em novos cadastros; seleção entre 27 UFs oficiais.
- Localização exibida como Cidade – UF e incluída em buscas e filtros.
- Registro antigo sem referência ou localização continua sem dados inventados.
- Telas de consulta de cercas e postos, regularização, alertas e confirmação de exclusão.
- Modos claro e escuro preservados.

### Banco, operação e validação
- Migração Alembic versionada e aditiva; backup automático pré-migração em SQLite.
- Controle otimista de versões e aviso de conflito ao editar telas desatualizadas.
- Inicialização por Waitress em iniciar.bat, com rotina interna habilitada.
- atualizar.bat para instalar dependências e aplicar migração em instalações existentes.
- 23 testes automatizados aprovados para datas, alertas, regularização, exclusão, concorrência e migrações.
- Verificador confirmado em servidor real sem requisições HTTP, sem duplicar histórico nos ciclos seguintes.
- Interface e prévia de ano bissexto verificadas nos temas claro e escuro.
- Migração validada em cópia completa do banco anterior, preservando todos os valores existentes.

### Limites conhecidos
- O verificador não executa enquanto o computador e a aplicação estiverem desligados.
- O intervalo padrão pode ser ajustado por INTERVALO_VERIFICACAO_SEGUNDOS.
- A implantação padrão usa um processo de servidor com múltiplas threads.
- Para MySQL, manter backup externo e executar as migrações antes de iniciar múltiplos processos.
- Login e permissões de acesso continuam fora desta atualização.

## 1.0.0 — 27/10/2026
- Cadastros, vínculos, histórico e pendências de verificação.
- Tipos de posto, buscas combinadas, ordenação e proteção contra nomes duplicados.
- Tema claro/escuro e instalador Windows.
