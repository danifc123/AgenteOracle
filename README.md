# Agente Oracle

Sistema para o departamento financeiro consultar o banco Oracle da empresa através
de um agente de IA (via MCP) e de um painel web (Angular).

**Objetivo:** permitir que qualquer pessoa do time financeiro converse em português
com o agente — peça relatórios prontos ou dados que ainda não têm tela pronta — e
também navegue por telas fixas (transações) no navegador.

## Arquitetura

```
Oracle DB  ←→  Backend Python (MCP + REST)  ←→  Agente de IA (Ollama local)
                        ↑    ↑
                        │    └──→  MongoDB (histórico de relatórios gerados pela IA)
                        └──→  Frontend Angular (REST direto, sem IA)
```

- **Transporte do agente:** [MCP](https://modelcontextprotocol.io/) via Streamable HTTP — servidor central expõe *tools* que qualquer cliente MCP (o chat deste projeto, ou outro agente) pode descobrir e chamar.
- **Transporte do frontend:** rotas REST comuns (`/api/...`) no mesmo servidor, sem passar pelo protocolo MCP nem pelo LLM — usadas para telas que não precisam de IA (tabela de transações, exportação).
- **Banco:** Oracle, acesso via [`python-oracledb`](https://python-oracledb.readthedocs.io/) em modo *thin* (sem necessidade de Instant Client instalado).
- **Histórico de relatórios:** MongoDB — guarda todo relatório que a IA gera pela tool `executar_consulta_financeira`, e é usado para não repetir a mesma consulta no Oracle — veja [Histórico de relatórios](#histórico-de-relatórios-mongodb).
- **LLM:** [Ollama](https://ollama.com/) rodando local (sem custo de API paga).
- **Auth Oracle:** usuário de serviço único, banco de teste/desenvolvimento.

### Consultas fixas x consultas livres

- **Tools/rotas fixas** (`listar_transacoes_json`, `/api/transacoes`, exportação): SQL pré-definido no código, sem participação da IA.
- **`executar_consulta_financeira`**: a IA gera o SQL (`SELECT`) na hora, para perguntas sem tela/tool pronta (ex: "orçado x realizado por categoria"). Passa por validações de segurança antes de rodar no banco — veja [Segurança do SQL livre](#segurança-do-sql-livre) — e o resultado é salvo/reaproveitado via o histórico em Mongo.

## Estrutura do projeto

```
src/agente_oracle/
├── config.py               # configurações (lidas de .env)
├── relatorios.py            # gerador de Excel (.xlsx) compartilhado
├── agent/
│   ├── core.py               # prompt de sistema + loop de tool-calling (compartilhado entre CLI e /api/chat)
│   └── cli.py                 # chat interativo de terminal (agente-oracle-chat)
├── db/
│   ├── connection.py         # pool de conexões Oracle
│   └── mongo.py               # conexão com o MongoDB (histórico de relatórios)
├── server/
│   └── server.py              # servidor MCP (FastMCP) + rotas REST (/api/...)
└── tools/
    ├── connectivity.py       # teste de conexão com o Oracle
    ├── financeiro.py          # consultas fixas de transações (JSON e Excel)
    ├── consulta_livre.py      # SQL livre gerado pela IA, com validação de segurança
    └── historico.py           # dedup e CRUD do histórico de relatórios no Mongo

frontend/grupoConceitoMCP/    # Angular — menu lateral, tela de transações, chat, histórico
scripts/
└── seed_dados_extra.py       # popula o banco de teste com dados extras

consultas.sql                 # modelagem/DDL de referência de todas as tabelas
```

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

3. Copie o arquivo de variáveis de ambiente e preencha com as credenciais do Oracle de dev/teste.
   Se seu MongoDB não estiver em `mongodb://localhost:27017` (padrão), ajuste também `MONGO_URI`/`MONGO_DB`:

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
   curl http://127.0.0.1:8000/api/transacoes
   ```

## Frontend (Angular)

```powershell
cd frontend/grupoConceitoMCP
npm install
npm start
```

Sobe em `http://localhost:4200`. Precisa do backend (`agente-oracle`) rodando para funcionar. Telas:

- **Início** — página inicial.
- **Financeiro → Transações** — tabela alimentada por `GET /api/transacoes`, com exportação em Excel.
- **Assistente IA** — chat com o agente (usa `POST /api/chat`); respostas que rodaram SQL mostram a consulta usada e um botão para baixar o resultado em Excel.
- **Histórico de relatórios** — lista os relatórios já gerados pela IA (`GET /api/relatorios/historico`), com botões para baixar em Excel (sem rodar de novo no Oracle) ou apagar do histórico.

## Rotas REST expostas pelo backend

| Rota | Método | Uso |
|---|---|---|
| `/api/transacoes` | GET | Lista transações em JSON, para a tabela do frontend |
| `/api/transacoes/exportar` | GET | Baixa o relatório de transações em Excel |
| `/api/chat` | POST | `{mensagem, historico}` → `{resposta, consultas}` — conversa com o agente |
| `/api/relatorio/exportar` | POST | `{sql}` → arquivo Excel — reexecuta uma consulta (normalmente uma que a IA gerou) e baixa o resultado |
| `/api/relatorios/historico` | GET | Lista os relatórios salvos no histórico (sem os dados das linhas) |
| `/api/relatorios/historico/{id}/exportar` | GET | Baixa em Excel um relatório salvo, a partir do dado já armazenado no Mongo |
| `/api/relatorios/historico/{id}` | DELETE | Apaga um relatório do histórico (ele volta a poder ser gerado de novo pela IA) |

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

   Ou via navegador, na tela **Assistente IA** do frontend (`http://localhost:4200/chat`).

   Digite `sair` para encerrar o chat de terminal.

## Segurança do SQL livre

A tool `executar_consulta_financeira` deixa a IA gerar SQL dinamicamente, então todo
SQL passa por validação antes de rodar (`tools/consulta_livre.py`):

- Só aceita instruções `SELECT` (bloqueia `INSERT/UPDATE/DELETE/DROP/ALTER/CREATE`, blocos PL/SQL, `DBMS_*`/`UTL_*`, etc.).
- Só permite as tabelas financeiras conhecidas (rejeita `USER_TABLES`, `V$...` ou qualquer tabela fora da whitelist).
- Bloqueia múltiplas instruções encadeadas (`;`).
- Aplica limite automático de linhas (`FETCH FIRST 200 ROWS ONLY`) e timeout de 10s na conexão.

## Histórico de relatórios (MongoDB)

Todo relatório que a IA gera pela tool `executar_consulta_financeira` é salvo no MongoDB
(`tools/historico.py`), guardando SQL, título, colunas e linhas do resultado.

- **Deduplicação semântica (camada principal):** antes de gerar SQL novo, a IA é instruída
  (`SYSTEM_PROMPT` em `agent/core.py`) a chamar primeiro a tool `listar_relatorios_gerados`,
  que devolve título, SQL e **dados completos** de todos os relatórios já salvos. A própria IA
  compara o pedido do usuário com o que já existe — mesmo que o SQL de um pedido repetido saia
  escrito de um jeito diferente (ordem de colunas, formatação) — e, se achar equivalente,
  responde direto com os dados já salvos, sem rodar nada no Oracle. Essa comparação semântica é
  feita pela IA porque dois SQLs com a mesma intenção nem sempre são textualmente idênticos.
- **Deduplicação exata (rede de segurança):** independente da IA verificar o histórico antes,
  `executar_consulta_financeira` também nunca roda no Oracle um SQL que já exista salvo com o
  texto exatamente igual (comparado por hash, normalizando espaços) — protege contra o caso da
  IA esquecer o passo acima ou gerar duas vezes o SQL idêntico.
- Esse cache não expira sozinho: um relatório só volta a poder ser gerado de novo se for
  apagado do histórico (tela **Histórico de relatórios**, ou `DELETE /api/relatorios/historico/{id}`).
- **Importante:** como o cache é permanente, se os dados de origem no Oracle mudarem (novas
  transações, por exemplo), um relatório já salvo **não é atualizado automaticamente** —
  é preciso apagá-lo do histórico para que a IA gere uma versão nova.
- O índice único em `hash_sql` (criado em `db/mongo.py`) garante que nunca existam dois
  documentos para o mesmo SQL, mesmo com chamadas concorrentes.
- **Limite conhecido:** como `listar_relatorios_gerados` devolve os dados completos de todos os
  relatórios salvos (para a IA conseguir responder sem uma segunda chamada), o histórico cresce
  no contexto enviado ao modelo a cada pergunta. Funciona bem para o volume atual de relatórios;
  se o histórico crescer muito, vale revisitar (ex: paginar ou resumir os mais antigos).

## Modelagem do banco

O DDL de referência está em [`consultas.sql`](consultas.sql). Tabelas:

1. `CONTAS_BANCARIAS` — contas/caixas da empresa
2. `CATEGORIAS_FINANCEIRAS` — categorias de receita/despesa
3. `FORNECEDORES_CLIENTES` — entidades externas
4. `TRANSACOES` — lançamentos financeiros (entradas/saídas)
5. `FATURAS` — faturas vinculadas às transações
6. `CENTROS_CUSTO` — áreas/departamentos internos que geram gasto
7. `ORCAMENTOS` — valor previsto por categoria/mês (orçado x realizado)