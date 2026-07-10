# Agente Oracle

Servidor MCP (Model Context Protocol) para integração com o banco Oracle da empresa.

**Objetivo v1:** permitir que pessoas da empresa emitam relatórios pré-definidos via um agente conectado ao MCP.
**Visão futura:** escalar com novas tools (relatórios adicionais, consultas ad-hoc, automações).

## Arquitetura

- **Transporte:** MCP via Streamable HTTP (servidor central, não local por usuário).
- **Banco:** Oracle, acesso via [`python-oracledb`](https://python-oracledb.readthedocs.io/) em modo *thin* (sem necessidade de Instant Client instalado).
- **Auth Oracle (v1):** usuário de serviço único, somente leitura. Relatórios são pré-definidos e parametrizados — não há geração livre de SQL.

```
src/agente_oracle/
├── config.py           # configurações (lidas de .env)
├── server.py            # servidor MCP (FastMCP) e registro das tools
├── db/
│   └── connection.py    # pool de conexões Oracle
└── tools/
    └── connectivity.py  # tool de teste de conectividade
```

## Setup

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

   O servidor MCP sobe em `http://127.0.0.1:8000` (configurável via `.env`).

5. Para validar a conexão, chame a tool `testar_conexao_oracle` a partir de um cliente MCP apontando para esse servidor.

## Agente local (Ollama)

Para conversar com o agente sem gastar tokens de API paga, ele roda localmente usando o [Ollama](https://ollama.com/).

1. Instale o Ollama e baixe um modelo com suporte a *tool calling*:

   ```powershell
   ollama pull qwen2.5:7b
   ```

2. Configure (opcional, já tem esses valores como padrão) no `.env`:

   ```
   OLLAMA_HOST=http://127.0.0.1:11434
   OLLAMA_MODEL=qwen2.5:7b
   ```

3. Em um terminal, suba o servidor MCP:

   ```powershell
   agente-oracle
   ```

4. Em outro terminal, suba o agente de chat (conecta no MCP acima e no Ollama local):

   ```powershell
   agente-oracle-chat
   ```

   Digite perguntas como "quais foram as últimas transações?" ou "teste a conexão com o Oracle". Digite `sair` para encerrar.

## Roadmap

- [x] Esqueleto do projeto + tool de teste de conectividade

