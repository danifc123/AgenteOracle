# Árvore de Diretórios

Visão completa da estrutura de pastas e arquivos do projeto — backend
(`src/agente_oracle/`) e frontend (`frontend/grupoConceitoMCP/src/app/`).
Complementa a versão em texto que fica no [README](README.md#estrutura-do-projeto),
com um pouco mais de contexto por arquivo.

← [Voltar ao README](README.md)

## Backend

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/arvore-backend-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/arvore-backend-light.svg">
  <img src="docs/arvore-backend-dark.svg" alt="Árvore de diretórios do backend (src/agente_oracle/): config.py e relatorios.py na raiz; agent/ com o loop de tool-calling e a orquestração de IA por módulo; db/ com as duas conexões de banco; server/ com as rotas HTTP; tools/ com a lógica de negócio e acesso a dado." width="100%">
</picture>

## Frontend

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/arvore-frontend-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/arvore-frontend-light.svg">
  <img src="docs/arvore-frontend-dark.svg" alt="Árvore de diretórios do frontend (frontend/grupoConceitoMCP/src/app/): pages/, componentes/, servicos/ e dadosRelatorios/." width="100%">
</picture>

---

Gerados por `docs/gerar_arvore.py` a partir dos dados de cada árvore
declarados no próprio script (sem dependência externa, só Python) — depois
de mudar a estrutura de pastas, edite os dados no topo do arquivo e rode:

```powershell
python docs/gerar_arvore.py
```

Isso regenera os quatro `.svg` (dark/light × backend/frontend) direto em
`docs/`.
