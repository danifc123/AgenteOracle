# Agente para o banco da Conceito Agricola - Engenheiro de Software Daniel Faria

Sistema para o departamento financeiro consultar o banco Oracle da empresa através
de um agente de IA (via MCP) e de um painel web (Angular).

**Objetivo:** permitir que qualquer pessoa do time financeiro converse em português
com o agente — peça relatórios prontos ou dados que ainda não têm tela pronta — e
também navegue pelos relatórios fixos do módulo Financeiro no navegador.

## Arquitetura

```
Oracle DB  ←→  Backend Python (MCP + REST)  ←→  Agente de IA (Ollama local)
                        ↑    ↑
                        │    └──→  histórico de relatórios gerados pela IA (mesmo banco, tabela relatorios_historico)
                        └──→  Frontend Angular (REST direto, sem IA)
```

- **Transporte do agente:** [MCP](https://modelcontextprotocol.io/) via Streamable HTTP — servidor central expõe *tools* que qualquer cliente MCP (o chat deste projeto, ou outro agente) pode descobrir e chamar.
- **Transporte do frontend:** rotas REST comuns (`/api/...`) no mesmo servidor, sem passar pelo protocolo MCP nem pelo LLM — usadas para telas que não precisam de IA.
- **Banco — dois bancos, dois propósitos fixos** (veja `db/connection.py`):
  - **Postgres**: sempre este banco (configs `POSTGRES_*`), independente de `DB_BACKEND` — guarda o estado do próprio sistema: usuários (`usuarios`), trilha de auditoria de login/administração (`eventos_seguranca`), histórico de relatórios gerados (`relatorios_historico`), layouts salvos (`relatorio_layouts`), cores de categoria (`categoria_cores`) e histórico de achados de auditoria (`auditoria_historico`).
  - **Oracle (ou Postgres local de teste)**: dado de negócio/RAG financeiro — as *views* do Protheus consultadas por `executar_consulta_financeira` e pelas rotas fixas de relatório. Controlado por `DB_BACKEND`: `oracle` em produção; `postgres` localmente (contra *views* de teste), já que o Oracle real de produção não é acessível fora do ambiente de produção.
- **Histórico de relatórios:** guardado numa tabela (`relatorios_historico`) sempre no Postgres — guarda todo relatório que a IA gera pela tool `executar_consulta_financeira`, usado para não repetir a mesma consulta. Relatório não fixado expira em 15h — veja `tools/financeiro/historico.py`.
- **LLM:** [Ollama](https://ollama.com/) rodando local (sem custo de API paga).
- **Auth Oracle:** usuário de serviço único (autenticação no banco, diferente do login de usuário do sistema — ver [Autenticação, papéis e segurança](#autenticação-papéis-e-segurança)), banco de teste/desenvolvimento.

### Consultas fixas x consultas livres

- **Tools/rotas fixas**: SQL pré-definido no código para cada relatório do módulo Financeiro, sem participação da IA — ver `server/financeiro/relatorios/`. A lista completa de rotinas do módulo está em `frontend/grupoConceitoMCP/src/app/dadosRelatorios/modulos-financeiro.ts`; nem toda rotina listada ali tem rota fixa implementada ainda (aparece como "Em breve" na tela até ganhar uma).
- **`executar_consulta_financeira`**: a IA gera o SQL (`SELECT`) na hora, para perguntas sem tela/tool pronta, usando só as *views* financeiras curadas listadas em `agent/financeiro/schema.py` (não as tabelas reais do TOTVS) — veja [Segurança do SQL livre](#segurança-do-sql-livre). O resultado é salvo/reaproveitado via o histórico.

## Estrutura do projeto

Três camadas no backend, cada uma com uma responsabilidade só — vale mais
entender esse princípio do que decorar a árvore de arquivos abaixo (que
cresce a cada relatório novo):

- **`server/`** — rotas HTTP (Starlette, registradas via `@mcp.custom_route`
  dentro de uma função `registrar(mcp)` por módulo). Só cuida de parsing de
  request, autenticação/autorização e formato da resposta.
- **`tools/`** — lógica de negócio e acesso a dado. Funções chamadas tanto
  pelas rotas HTTP (`server/`) quanto, quando expostas como MCP tool, pelo
  próprio agente de IA (ex: `executar_consulta_financeira`).
- **`agent/`** — orquestração do agente de IA em si (prompt, schema de views
  liberadas pra IA, loop de chamada ao Ollama).

```
src/agente_oracle/
├── config.py                 # configurações (lidas de .env) + validação da chave de auth no startup
├── relatorios.py              # gerador de Excel (.xlsx) compartilhado por todo relatório
├── agent/
│   ├── core.py                 # loop de tool-calling genérico (sem prompt nem schema — reaproveitável por qualquer módulo)
│   ├── cli.py                   # chat interativo de terminal (agente-oracle-chat)
│   ├── auditoria/               # análise de qualidade de dado via IA (genérica, não sabe de nenhum módulo específico)
│   └── financeiro/
│       ├── prompt.py              # system prompt específico do Financeiro (monta o texto a partir de schema.py)
│       ├── schema.py              # views financeiras liberadas pra IA — fonte única usada pelo prompt e pela whitelist de segurança
│       ├── financeiro.py          # orquestração do chat do módulo Financeiro
│       └── projecoes.py           # regressão linear + análise textual da IA, usado pelas telas de Previsão
├── db/
│   ├── connection.py           # duas conexões fixas: Postgres sempre (estado do sistema) + negócio/RAG (Oracle ou Postgres, conforme DB_BACKEND)
│   └── views/                   # definição das views curadas expostas ao agente
├── server/
│   ├── app.py                   # monta o app Starlette (CORS + headers de segurança), entrypoint (agente-oracle)
│   ├── cors.py                   # CORSMiddleware é a única fonte de verdade de origem permitida (ver comentário no arquivo)
│   ├── security_headers.py       # middleware de headers de segurança padrão (X-Frame-Options, CSP, HSTS...)
│   ├── auth/
│   │   ├── rotas.py                # login, CRUD de usuário, troca de senha, (des)bloqueio de conta, trilha de segurança
│   │   ├── dependencia.py          # exigir_usuario/administrador/desenvolvedor/modulo_financeiro — checagem de sessão
│   │   ├── decorador_rota.py       # @rota_protegida — decorator usado por toda rota autenticada (ver seção própria abaixo)
│   │   └── rate_limit.py           # limite de tentativas em memória (login, troca de senha, criação de usuário)
│   ├── auditoria/
│   │   └── rotas.py                # roda a auditoria ao vivo por módulo + histórico de achados
│   ├── ferramentas/
│   │   └── juntar_excel.py         # upload de 2 planilhas .xlsx e junção (empilha, faz JOIN ou lado-a-lado)
│   └── financeiro/                 # rotas HTTP do módulo Financeiro
│       ├── relatorios/               # 1 arquivo por relatório fixo (SQL + rotas), mais os compartilhados:
│       │   ├── relatorio_customizado.py      # rotas do construtor de relatório sob demanda ("Criar Relatório")
│       │   ├── relatorio_customizado_sql.py  # lógica pura de resolução de JOIN/montagem de SQL do item acima
│       │   ├── filiais.py, cadastros.py      # listas pros selects de filtro (filial, cliente, vendedor, produto...)
│       │   └── filtros_sql.py                # utilitário: monta cláusula IN (...) a partir de uma lista de valores
│       ├── previsao.py             # rotas de Previsão (Vendas e Fluxo de Caixa) — projeção por regressão linear
│       ├── historico.py            # rotas REST do histórico de relatórios gerados pela IA
│       ├── layouts.py              # presets de coluna/filtro salvos por usuário na tela "Criar Relatório"
│       ├── categoria_cores.py      # cor personalizada por categoria (usado nos gráficos)
│       └── ia.py                   # registra as tools de IA + /api/financeiro/chat + /api/financeiro/relatorio/exportar
└── tools/
    ├── connectivity.py         # teste de conexão com o Oracle (genérico, qualquer módulo pode usar)
    ├── auth/
    │   ├── usuarios.py            # CRUD de usuário, autenticação, bloqueio por tentativas erradas
    │   ├── papeis.py               # fonte única de verdade de quem acessa o quê (ver seção própria abaixo)
    │   ├── token.py                 # geração/verificação do JWT de sessão
    │   ├── eventos_seguranca.py     # trilha de auditoria (login, criação/exclusão de usuário, bloqueio...)
    │   └── cli.py                    # agente-oracle-criar-usuario — bootstrap do primeiro admin
    ├── auditoria/
    │   ├── historico.py            # CRUD dos achados de auditoria
    │   └── dispensados.py           # achados que um usuário marcou como "não é problema"
    ├── ferramentas/
    │   └── juntar_excel.py         # lógica pura de junção de planilha (sem HTTP)
    └── financeiro/
        ├── consulta_livre.py       # SQL livre gerado pela IA, com validação de segurança
        └── historico.py             # dedup e CRUD do histórico de relatórios do Financeiro

frontend/grupoConceitoMCP/src/app/
├── pages/                     # uma pasta por tela, incluindo pages/modulos/{financeiro,estoque}/
├── componentes/                # UI reutilizável entre telas (tabela, dialog, seletor de arquivo...)
├── servicos/                    # estado compartilhado (sessão, guards) + funções puras reaproveitadas
│                                  # entre páginas (mensagens-erro.ts, download-arquivo.ts, ordenacao-tabela.ts)
└── dadosRelatorios/              # configuração/metadado estático dos relatórios (dado, não lógica)
```

### Módulo Estoque

O frontend já tem as telas do módulo Estoque, mas ainda não existe backend
correspondente (sem rotas em `server/`, sem tools em `tools/`) — é trabalho
futuro conhecido, não uma lacuna acidental.

## Setup do backend

1. Crie e ative um ambiente virtual:

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

2. Instale o projeto em modo editável:

   ```powershell
   pip install -e ".[dev]"
   ```

3. Copie o arquivo de variáveis de ambiente e preencha as credenciais dos dois bancos — `POSTGRES_*` (sempre usado, estado do sistema) e `ORACLE_*`/`DB_BACKEND` (dado de negócio/RAG financeiro; `DB_BACKEND=postgres` localmente, contra *views* de teste, se não tiver acesso ao Oracle real):

   ```powershell
   copy .env.example .env
   ```

4. Rode o servidor:

   ```powershell
   agente-oracle
   ```

   Sobe em `http://127.0.0.1:8000` (configurável via `.env`), expondo tanto o endpoint MCP (`/mcp`) quanto as rotas REST (`/api/...`).

5. Para validar a conexão, chame a tool `testar_conexao_oracle` a partir de um cliente MCP, ou teste a rota REST:

   ```powershell
   curl http://127.0.0.1:8000/api/relatorios/historico
   ```

## Frontend (Angular)

```powershell
cd frontend/grupoConceitoMCP
npm install
npm start
```

Sobe em `http://localhost:4200`. Precisa do backend rodando para funcionar. Telas
principais: **Início**, **Financeiro** (Assistente IA, Fluxo de Caixa, Vendas,
Criar Relatório, Específico Grupo Conceito), **Histórico de relatórios**,
**Auditoria**, **Usuários** (administração, só pra quem tem papel
administrador), **Juntar Excel**. **Estoque** existe no menu mas ainda é
placeholder (ver [Módulo Estoque](#módulo-estoque) acima).

## Rotas REST expostas pelo backend

Cada módulo em `server/` registra as próprias rotas dentro de uma função
`registrar(mcp)` — a lista completa e sempre atual está no próprio código
(`grep -r "custom_route" src/agente_oracle/server` lista todas de uma vez);
manter uma tabela separada aqui historicamente ficou desatualizada assim que
um relatório novo era adicionado, então não vale reproduzir. Os grupos
principais:

- `/api/auth/*` — login, CRUD de usuário, perfil, senha, papéis, (des)bloqueio de conta, trilha de segurança (ver [Autenticação e papéis](#autenticação-papéis-e-segurança))
- `/api/financeiro/*` — chat com a IA, previsão (Vendas/Fluxo de Caixa), relatório customizado, os relatórios fixos (`financeiro/relatorios/*.py`), layouts salvos, cores de categoria
- `/api/relatorios/historico*` — histórico de relatórios gerados pela IA (fixar, apagar, baixar em Excel)
- `/api/auditoria*` — auditoria de qualidade de dado (rodar ao vivo, histórico, dispensar achado)
- `/api/ferramentas/juntar-excel*` — upload e junção de duas planilhas

## Autenticação, papéis e segurança

Login próprio do sistema (JWT, sem depender de IdP externo) — ver
`tools/auth/`, `server/auth/`.

- **Papéis**: `tools/auth/papeis.py` é a fonte única de verdade de quem
  acessa o quê (`desenvolvedor`, `financeiro_admin`, `financeiro`,
  `estoque_admin`, `estoque`, `rh_admin`, `rh`) — nunca `if papel == "x"`
  espalhado pelo código. `desenvolvedor` tem `acesso_total` (todo módulo,
  presente ou futuro) e também funciona como "time de TI": só quem tem esse
  papel pode desbloquear uma conta ou ver a trilha de eventos de segurança.
- **Bloqueio de conta**: 3 tentativas de login erradas seguidas bloqueiam a
  conta até um `desenvolvedor` desbloquear pela tela Usuários — separado do
  rate limit (5 tentativas/3min, em memória, se autolimpa sozinho) que
  protege contra automação mesmo pra usuário inexistente.
- **Trilha de auditoria de segurança**: toda ação sensível (login
  falho/bem-sucedido, criação/exclusão de usuário, bloqueio/desbloqueio) fica
  registrada em `eventos_seguranca` (`GET /api/auth/eventos-seguranca`,
  restrito a `desenvolvedor`).
- **Toda rota autenticada usa o mesmo decorator** —
  `server/auth/decorador_rota.py:rota_protegida` — que cuida do preflight
  `OPTIONS` e da checagem de login/autorização (`exigir_usuario` por
  padrão, ou uma variante como `exigir_administrador`/
  `exigir_desenvolvedor`/`exigir_modulo_financeiro`), deixando a função da
  rota só com a lógica de negócio, recebendo o usuário já resolvido:

  ```python
  @mcp.custom_route("/api/financeiro/algo", methods=["GET", "OPTIONS"])
  @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
  async def minha_rota(request: Request, usuario: dict) -> Response:
      ...
  ```

  (`/api/auth/login` é a única rota que foge desse padrão — por definição,
  ainda não há usuário logado nela.)
- **Primeiro usuário**: não existe tela de auto-cadastro — o primeiro admin
  é criado via `agente-oracle-criar-usuario` (script de terminal), dali em
  diante outros usuários são criados pela tela Usuários.

## Agente local (Ollama)

O LLM roda localmente, sem custo de API.

1. Instale o Ollama e baixe um modelo com suporte a *tool calling*:

   ```powershell
   ollama pull qwen2.5:7b
   ```

2. Configure (opcional, já tem esses valores como padrão) no `.env`:

   ```
   OLLAMA_HOST=http://127.0.0.1:11434
   OLLAMA_MODEL=qwen2.5:7b
   ```

3. Com o servidor MCP rodando (`agente-oracle`), converse via terminal:

   ```powershell
   agente-oracle-chat
   ```

   Ou via navegador, na tela **Assistente IA** do frontend (`http://localhost:4200/financeiro/chat`).

   Digite `sair` para encerrar o chat de terminal.

## Segurança do SQL livre

A tool `executar_consulta_financeira` deixa a IA gerar SQL dinamicamente, então todo
SQL passa por validação antes de rodar (`tools/financeiro/consulta_livre.py`):

- Só aceita instruções `SELECT` (bloqueia `INSERT/UPDATE/DELETE/DROP/ALTER/CREATE`, blocos PL/SQL, `DBMS_*`/`UTL_*`, etc.).
- Só permite as *views* financeiras curadas listadas em `VIEWS_DISPONIVEIS` (`agent/financeiro/schema.py`) — nunca as tabelas reais do TOTVS. Essa lista é a fonte única tanto do texto de schema que vai no prompt da IA quanto da whitelist (`TABELAS_PERMITIDAS`, em `tools/financeiro/consulta_livre.py`), pra nunca ficar um SQL que o prompt promete mas a validação rejeita (ou o contrário). Enquanto uma view não estiver na lista, nenhuma consulta que a use é aceita.
- Bloqueia múltiplas instruções encadeadas (`;`).
- Aplica limite automático de linhas (`FETCH FIRST 200 ROWS ONLY` no Oracle, ou o `LIMIT` que a própria IA já tiver colocado quando o banco é Postgres) e timeout de 10s na conexão.

## Views curadas do Financeiro (Oracle) — modelo de "papel" em STAGE.PESSOA

As views que alimentam `VIEWS_DISPONIVEIS` (`agent/financeiro/schema.py`) são definidas
em `db/views/*.sql` — hoje `financeiro_science.sql`, em cima do banco de negócio/RAG
real (`SCIENCE_PROD`, schema `STAGE`, o ETL/BI da empresa; `financeiro.sql` é a versão
anterior, em cima do Oracle transacional do Protheus, mantida só de referência).
Ninguém roda `CREATE VIEW` automaticamente — o SQL é escrito aqui e aplicado manualmente
por quem tiver permissão (hoje, via DBA/SQL Developer), porque a política do projeto é
nunca alterar/criar nada nesses bancos por conta própria (só leitura).

**Por que `SA1010`/`SA2010`/`SA3010` aparecem espalhados nos `JOIN`s**: no `STAGE`,
`PESSOA` é um cadastro único (nome, CNPJ/CPF, endereço) compartilhado por cliente,
fornecedor e vendedor — só que o `CODIGO` dessa tabela **não é único sozinho**. A mesma
pessoa pode aparecer mais de uma vez em `PESSOA` com o mesmo código, uma vez por
"papel" — ex: um produtor que é cliente (compra insumo) E fornecedor (vende grão) da
mesma empresa gera duas linhas com o mesmo `CODIGO`, uma vinda de `SA1010` (clientes no
Protheus) e outra de `SA2010` (fornecedores). `PESSOA.SOURCETABLE` guarda de qual tabela
Protheus aquela linha veio — por isso todo `JOIN` com `PESSOA` também filtra esse campo:

```sql
LEFT JOIN STAGE.pessoa p
    ON p.codigo = cr.codigopessoa AND p.sourcetable = 'SA1010'  -- só o papel "cliente"
```

Sem esse filtro, o `JOIN` casa com as duas linhas e duplica o resultado (testado: sem o
filtro, 9.873 clientes viravam 12.242 linhas — 24% de duplicação). Os três valores
usados nas views atuais: `SA1010` = papel cliente, `SA2010` = papel fornecedor, `SA3010`
= papel vendedor (só usado em `vw_faturamento.vendedor_nome`). Uma view nova que junte
com `PESSOA` **sempre** precisa desse filtro de papel — esquecer é o tipo de bug que não
aparece em teste com poucos dados, só quando alguém do mundo real acumula mais de um
papel.

## Testes

```powershell
# Backend — não precisa de banco (mock/sem I/O real)
python -m pytest tests/unit -q

# Backend — precisa de Postgres local rodando (DB_BACKEND=postgres no .env)
python -m pytest tests/integration -q -m integration

# Frontend
cd frontend/grupoConceitoMCP
npm test       # vitest — hoje cobre só um punhado de componentes/serviços
npm run e2e    # cypress
```

`tests/unit/` espelha a estrutura de `src/agente_oracle/` e não toca banco
nenhum. `tests/integration/` (marcado `@pytest.mark.integration`, excluído
por padrão via `addopts` do `pyproject.toml`) sobe rotas de verdade contra um
Postgres local — pula sozinho se não achar um rodando. O frontend tem
cobertura de teste bem menor que o backend hoje (a maioria dos componentes
não tem `.spec.ts`) — ao mexer numa tela sem teste, validar manualmente
(`ng build` + testar no navegador) é o caminho, não um substituto perfeito
mas o que o projeto usa hoje.

## Lint e formatação

```powershell
# Backend (ruff)
ruff check src tests
ruff format src tests

# Frontend
cd frontend/grupoConceitoMCP
npm run lint      # ESLint — TypeScript + templates Angular
npm run format    # Prettier
```

Nenhuma dessas ferramentas roda automaticamente (não existe pipeline de CI
configurado neste repositório) — rodar manualmente antes de abrir PR é o que
mantém o padrão até isso mudar.

## Convenções de clean code do projeto

Além do lint/formatação automáticos, o projeto segue algumas convenções que
nenhuma ferramenta cobre sozinha — vale manter em qualquer código novo:

- **Camadas do backend**: `server/` só HTTP (parsing de request,
  autenticação, forma da resposta), `tools/` só lógica de
  negócio/acesso a dado, `agent/` só orquestração de IA — nunca misturar
  (ver [Estrutura do projeto](#estrutura-do-projeto)). Rota autenticada
  nova usa o decorator `@rota_protegida(metodos,
  exigir=...)` (`server/auth/decorador_rota.py`), nunca repete o bloco de
  `OPTIONS`+autenticação na mão.
- **Frontend**: lógica repetida em 2+ componentes vira função pura em
  `servicos/`, nunca copiada entre componentes. Ação destrutiva (apagar
  algo) usa o componente `ConfirmacaoDialog`
  (`componentes/confirmacao-dialog/`), nunca `confirm()` nativo do
  navegador.
- **Ordem de método/função dentro de um arquivo ou classe**: as
  públicas/`protected` em ordem alfabética entre si; uma auxiliar privada
  usada por um único método fica logo depois dele (aninhada, não solta em
  outro canto do arquivo); uma auxiliar usada por 2+ métodos (ou por
  nenhum) vira um bloco alfabético antes das públicas que dependem dela.
  Propriedades, `signal`/`computed`, `constructor` e *lifecycle hooks*
  (`ngOnInit`, etc.) não entram nessa reordenação — ficam sempre na
  posição convencional (topo da classe / logo após as propriedades).
- **Extensibilidade via dado declarativo**, não `if/else` espalhado pelo
  código — mesmo espírito de `tools/auth/papeis.py`/`MODULOS_CONHECIDOS`:
  um módulo novo (RH, Compras...) é uma entrada de dado nova, não uma
  edição em N lugares diferentes.
- **Preferir cálculo determinístico a dependência de IA** quando o
  resultado precisa ser confiável/preciso (ex: as projeções de
  Vendas/Fluxo de Caixa são 100% estatística, regressão linear — sem
  Ollama envolvido; IA fica reservada pra onde o resultado *é* texto ou
  julgamento qualitativo, como o chat e os achados de Auditoria).
- **Mudança que é só reorganização** (sem alterar lógica) deve resultar
  num diff com inserções = remoções (`git diff --numstat`) — se não
  bater, alguma coisa mudou além da posição do código, vale investigar
  antes de seguir.