# Agente para o banco da TOTVS

Sistema para o departamento financeiro consultar o banco Oracle da empresa através
de um agente de IA (via MCP) e de um painel web (Angular).

**Objetivo:** permitir que qualquer pessoa do time financeiro converse em português
com o agente — peça relatórios prontos ou dados que ainda não têm tela pronta — e
também navegue pelos relatórios fixos do módulo Financeiro no navegador.

## Arquitetura

```
Oracle DB  ←→  Backend Python (MCP + REST)  ←→  Agente de IA (Ollama local)
                        ↑    ↑
                        │    └──→  MongoDB (histórico de relatórios gerados pela IA)
                        └──→  Frontend Angular (REST direto, sem IA)
```

- **Transporte do agente:** [MCP](https://modelcontextprotocol.io/) via Streamable HTTP — servidor central expõe *tools* que qualquer cliente MCP (o chat deste projeto, ou outro agente) pode descobrir e chamar.
- **Transporte do frontend:** rotas REST comuns (`/api/...`) no mesmo servidor, sem passar pelo protocolo MCP nem pelo LLM — usadas para telas que não precisam de IA.
- **Banco:** Oracle, acesso via [`python-oracledb`](https://python-oracledb.readthedocs.io/) em modo *thin* (sem necessidade de Instant Client instalado).
- **Histórico de relatórios:** MongoDB — guarda todo relatório que a IA gera pela tool `executar_consulta_financeira`, e é usado para não repetir a mesma consulta no Oracle — veja [Histórico de relatórios](#histórico-de-relatórios-mongodb).
- **LLM:** [Ollama](https://ollama.com/) rodando local (sem custo de API paga).
- **Auth Oracle:** usuário de serviço único, banco de teste/desenvolvimento.

### Consultas fixas x consultas livres

- **Tools/rotas fixas**: SQL pré-definido no código para cada relatório do módulo Financeiro, sem participação da IA. Ainda a implementar — veja a lista de relatórios em `frontend/grupoConceitoMCP/src/app/dadosRelatorios/modulos-financeiro.ts`.
- **`executar_consulta_financeira`**: a IA gera o SQL (`SELECT`) na hora, para perguntas sem tela/tool pronta. Passa por validações de segurança antes de rodar no banco — veja [Segurança do SQL livre](#segurança-do-sql-livre) — e o resultado é salvo/reaproveitado via o histórico em Mongo. Fica sem nenhuma tabela liberada até o schema real do banco (TOTVS) ser importado.

## Estrutura do projeto

```
src/agente_oracle/
├── config.py               # configurações (lidas de .env)
├── relatorios.py            # gerador de Excel (.xlsx) compartilhado
├── agent/
│   ├── core.py               # loop de tool-calling genérico (sem prompt nem schema — reaproveitável por qualquer módulo)
│   ├── cli.py                 # chat interativo de terminal (agente-oracle-chat) — hoje usa o prompt do Financeiro
│   └── financeiro/
│       └── prompt.py            # system prompt + schema conhecido pela IA, específicos do Financeiro
├── db/
│   ├── connection.py         # pool de conexões Oracle
│   └── mongo.py               # conexão com o MongoDB (histórico de relatórios)
├── server/
│   ├── app.py                 # cria o servidor MCP (FastMCP), registra os módulos, entrypoint (agente-oracle)
│   ├── cors.py                 # headers/preflight CORS compartilhados entre as rotas
│   └── financeiro/             # rotas HTTP do módulo Financeiro
│       ├── relatorios/             # 1 arquivo por relatório fixo (SQL + rotas): fluxo_caixa_realizado.py (FINR01), duplicata_mercantil.py (FINR04), baixa_produtos.py (CAG06R04)
│       │   ├── filiais.py            # lista as filiais (SA6010) pro seletor múltiplo da tela
│       │   ├── cadastros.py           # lista clientes/lojas/vendedores/prefixos/tipos pros selects com busca dos filtros
│       │   └── filtros_sql.py         # utilitário: monta cláusula IN (...) a partir de uma lista de valores
│       ├── historico.py           # rotas REST do histórico de relatórios gerados pela IA
│       └── ia.py                   # registra as tools de IA + /api/chat + /api/relatorio/exportar
└── tools/
    ├── connectivity.py       # teste de conexão com o Oracle (genérico, qualquer módulo pode usar)
    └── financeiro/
        ├── consulta_livre.py    # SQL livre gerado pela IA para dados financeiros, com validação de segurança
        └── historico.py          # dedup e CRUD do histórico de relatórios do Financeiro no Mongo

frontend/grupoConceitoMCP/    # Angular — menu lateral, módulos financeiros, chat, histórico
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
   curl http://127.0.0.1:8000/api/relatorios/historico
   ```

## Frontend (Angular)

```powershell
cd frontend/grupoConceitoMCP
npm install
npm start
```

Sobe em `http://localhost:4200`. Precisa do backend (`agente-oracle`) rodando para funcionar. Telas:

- **Início** — página inicial.
- **Financeiro → Específico Grupo Conceito** — lista os relatórios do módulo (ex: Fluxo de Caixa Realizado, Boleto, FINR10...); cada um aparece como "Em breve" até ter uma tool/rota fixa implementada.
- **Assistente IA** — chat com o agente (usa `POST /api/chat`); respostas que rodaram SQL mostram a consulta usada e um botão para baixar o resultado em Excel.
- **Histórico de relatórios** — lista os relatórios já gerados pela IA (`GET /api/relatorios/historico`), com botão de bandeira para fixar/desfixar (relatório fixado não expira), botão para baixar em Excel (sem rodar de novo no Oracle) e botão para apagar do histórico.

## Rotas REST expostas pelo backend

| Rota | Método | Uso |
|---|---|---|
| `/api/chat` | POST | `{mensagem, historico}` → `{resposta, consultas}` — conversa com o agente |
| `/api/relatorio/exportar` | POST | `{sql}` → arquivo Excel — reexecuta uma consulta (normalmente uma que a IA gerou) e baixa o resultado |
| `/api/relatorios/historico` | GET | Lista os relatórios salvos no histórico (sem os dados das linhas) |
| `/api/relatorios/historico/{id}/exportar` | GET | Baixa em Excel um relatório salvo, a partir do dado já armazenado no Mongo |
| `/api/relatorios/historico/{id}` | PATCH | `{fixado: bool}` → fixa/desfixa um relatório (fixado não expira pelo TTL) |
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
SQL passa por validação antes de rodar (`tools/financeiro/consulta_livre.py`):

- Só aceita instruções `SELECT` (bloqueia `INSERT/UPDATE/DELETE/DROP/ALTER/CREATE`, blocos PL/SQL, `DBMS_*`/`UTL_*`, etc.).
- Só permite as tabelas da whitelist (`TABELAS_PERMITIDAS`, em `tools/financeiro/consulta_livre.py`) — hoje vazia, aguardando a importação do schema real do banco (TOTVS), então toda consulta é rejeitada até essa lista ser preenchida.
- Bloqueia múltiplas instruções encadeadas (`;`).
- Aplica limite automático de linhas (`FETCH FIRST 200 ROWS ONLY`) e timeout de 10s na conexão.