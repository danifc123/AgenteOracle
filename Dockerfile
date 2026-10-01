FROM python:3.11-slim

WORKDIR /app

# oracledb roda em modo thin por padrão (sem Instant Client nativo) — só
# precisa de ORACLE_CLIENT_LIB_DIR se o Oracle exigir Native Network
# Encryption/Data Integrity, o que não é o caso aqui. psycopg[binary] já
# vem com wheel pré-compilada, sem precisar de libpq-dev.
COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir .

# MCP_HOST=0.0.0.0 é obrigatório aqui — o padrão (127.0.0.1, ver
# .env.example) só aceita conexão de dentro do próprio container, nada de
# fora alcançaria a API. Sobrescrito pelo docker-compose.yml, mantido aqui
# só como fallback caso o container rode isolado sem compose.
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000

EXPOSE 8000

# Processo único de propósito: `server/app.py::main` sobe o poller do GLPI
# como uma task assíncrona em memória (`lifespan_com_poller`) — mais de uma
# réplica ou worker duplicaria esse poller contra o GLPI real. Nunca rodar
# isso com `--workers` ou `deploy.replicas > 1`.
CMD ["agente-oracle"]
