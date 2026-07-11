# Agente Oracle

Sistema para o departamento financeiro consultar o banco Oracle da empresa através
de um agente de IA (via MCP) e de um painel web (Angular).

**Objetivo:** permitir que qualquer pessoa do time financeiro converse em português
com o agente — peça relatórios prontos ou dados que ainda não têm tela pronta — e
também navegue por telas fixas (transações) no navegador.

## Arquitetura

```
Oracle DB  ←→  Backend Python (MCP + REST)  ←→  Agente de IA (Ollama local)
                        ↑
                        └──→  Frontend Angular (REST direto, sem IA)
```

- **Transporte do agente:** [MCP](https://modelcontextprotocol.io/) via Streamable HTTP — servidor central expõe *tools* que qualquer cliente MCP (o chat deste projeto, ou outro agente) pode descobrir e chamar.
- **Transporte do frontend:** rotas REST comuns (`/api/...`) no mesmo servidor, sem passar pelo protocolo MCP nem pelo LLM — usadas para telas que não precisam de IA (tabela de transações, exportação).
- **Banco:** Oracle, acesso via [`python-oracledb`](https://python-oracledb.readthedocs.io/) em modo *thin* (sem necessidade de Instant Client instalado).
- **LLM:** [Ollama](https://ollama.com/) rodando local (sem custo de API paga).
- **Auth Oracle:** usuário de serviço único, banco de teste/desenvolvimento.

### Consultas fixas x consultas livres

- **Tools/rotas fixas** (`listar_transacoes_json`, `/api/transacoes`, exportação): SQL pré-definido no código, sem participação da IA.
- **`executar_consulta_financeira`**: a IA gera o SQL (`SELECT`) na hora, para perguntas sem tela/tool pronta (ex: "orçado x realizado por categoria"). Passa por validações de segurança antes de rodar no banco — veja [Segurança do SQL livre](#segurança-do-sql-livre).

## Estrutura do projeto

```
src/agente_oracle/
├── config.py               # configurações (lidas de .env)
├── relatorios.py            # gerador de Excel (.xlsx) compartilhado
├── agent/
│   ├── core.py               # prompt de sistema + loop de tool-calling (compartilhado entre CLI e /api/chat)
│   └── cli.py                 # chat interativo de terminal (agente-oracle-chat)
├── db/
│   └── connection.py         # pool de conexões Oracle
├── server/
│   └── server.py              # servidor MCP (FastMCP) + rotas REST (/api/...)
└── tools/
    ├── connectivity.py       # teste de conexão com o Oracle
    ├── financeiro.py          # consultas fixas de transações (JSON e Excel)
    └── consulta_livre.py      # SQL livre gerado pela IA, com validação de segurança

frontend/grupoConceitoMCP/    # Angular — menu lateral, tela de transações, chat
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

3. Copie o arquivo de variáveis de ambiente e preencha com as credenciais do Oracle de dev/teste:

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

## Rotas REST expostas pelo backend

| Rota | Método | Uso |
|---|---|---|
| `/api/transacoes` | GET | Lista transações em JSON, para a tabela do frontend |
| `/api/transacoes/exportar` | GET | Baixa o relatório de transações em Excel |
| `/api/chat` | POST | `{mensagem, historico}` → `{resposta, consultas}` — conversa com o agente |
| `/api/relatorio/exportar` | POST | `{sql}` → arquivo Excel — reexecuta uma consulta (normalmente uma que a IA gerou) e baixa o resultado |

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

## Modelagem do banco

O DDL de referência está em [`consultas.sql`](consultas.sql). Tabelas:

1. `CONTAS_BANCARIAS` — contas/caixas da empresa
2. `CATEGORIAS_FINANCEIRAS` — categorias de receita/despesa
3. `FORNECEDORES_CLIENTES` — entidades externas
4. `TRANSACOES` — lançamentos financeiros (entradas/saídas)
5. `FATURAS` — faturas vinculadas às transações
6. `CENTROS_CUSTO` — áreas/departamentos internos que geram gasto
7. `ORCAMENTOS` — valor previsto por categoria/mês (orçado x realizado)

[`scripts/seed_dados_extra.py`](scripts/seed_dados_extra.py) popula o banco de teste
com dados extras (é idempotente: cria tabelas/coluna só se não existirem, e não
duplica dados se rodado de novo).

## Roadmap

- [x] Esqueleto do projeto + tool de teste de conectividade
- [x] Consulta fixa de transações (JSON + Excel) com INNER JOIN
- [x] Frontend Angular com menu lateral, tela de transações e chat
- [x] Chat com IA local (Ollama) via MCP, com histórico e exportação de relatório
- [x] SQL livre gerado pela IA, com validação de segurança
- [x] Modelagem estendida (centros de custo, orçamentos)
