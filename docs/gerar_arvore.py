# -*- coding: utf-8 -*-
"""Gera os SVGs de arvore de diretorios (backend/frontend, tema claro e
escuro), reaproveitando a linguagem visual do diagrama de arquitetura
(fontes, cores, grade de fundo). Roda com `python docs/gerar_arvore.py`
(ou de dentro de docs/, `python gerar_arvore.py`) -- sem dependencia
externa, so Python 3. Escreve sempre ao lado deste arquivo.

Pra atualizar depois de mudar a estrutura de pastas: edite BACKEND/
FRONTEND abaixo (mesma forma de tupla, ver exemplos) e rode de novo --
os 4 arquivos (dark/light x backend/frontend) sao sobrescritos.
"""

import os

CANVAS_W = 1500
MARGIN_L = 40
MARGIN_R = 40
ROW_H = 26
INDENT = 22
COMENTARIO_X = 430  # coluna fixa (nao relativa a indentacao) -- evita nome
                     # de arquivo comprido em pasta funda colidir com o comentario
HEADER_H = 100
FOOTER_H = 40

DARK = {
    "bg": "#070b14", "bg_grid": "rgba(79,141,255,0.05)",
    "text": "#eaf1ff", "text_dim": "#8291b3", "icone_arquivo": "#64748b",
    "linha": "#1e2a45", "guia": "#2a3a5c",
    "root": "#4f8dff", "agent": "#b48bff", "db": "#4f8dff", "server": "#35ffa6", "tools": "#ffa63d",
    "pages": "#b48bff", "componentes": "#35e7ff", "servicos": "#35ffa6", "dadosRelatorios": "#ffa63d",
}
LIGHT = {
    "bg": "#f7f9fc", "bg_grid": "rgba(37,99,235,0.06)",
    "text": "#16202e", "text_dim": "#5b6b82", "icone_arquivo": "#64748b",
    "linha": "#dbe3ee", "guia": "#c3cedd",
    "root": "#2563eb", "agent": "#7c3aed", "db": "#2563eb", "server": "#059669", "tools": "#c2670a",
    "pages": "#7c3aed", "componentes": "#0891b2", "servicos": "#059669", "dadosRelatorios": "#c2670a",
}

BACKEND = ("src/agente_oracle/", None, True, "root", [
    ("config.py", "configurações (lidas de .env) + validação da chave de auth no startup", False, "root", []),
    ("relatorios.py", "gerador de Excel (.xlsx) compartilhado por todo relatório", False, "root", []),
    ("agent/", None, True, "agent", [
        ("core.py", "loop de tool-calling genérico (sem prompt nem schema — reaproveitável por qualquer módulo)", False, "agent", []),
        ("cli.py", "chat interativo de terminal (agente-oracle-chat)", False, "agent", []),
        ("auditoria/", "análise de qualidade de dado via IA (genérica, não sabe de nenhum módulo específico)", True, "agent", []),
        ("financeiro/", None, True, "agent", [
            ("prompt.py", "system prompt específico do Financeiro (monta o texto a partir de schema.py)", False, "agent", []),
            ("schema.py", "views financeiras liberadas pra IA — fonte única usada pelo prompt e pela whitelist de segurança", False, "agent", []),
            ("financeiro.py", "orquestração do chat do módulo Financeiro", False, "agent", []),
            ("projecoes.py", "regressão linear + análise textual da IA, usado pelas telas de Previsão", False, "agent", []),
        ]),
    ]),
    ("db/", None, True, "db", [
        ("connection.py", "duas conexões fixas: Postgres sempre (estado do sistema) + negócio/RAG (Oracle ou Postgres, conforme DB_BACKEND)", False, "db", []),
        ("views/", "definição das views curadas expostas ao agente", True, "db", []),
    ]),
    ("server/", None, True, "server", [
        ("app.py", "monta o app Starlette (CORS + headers de segurança), entrypoint (agente-oracle)", False, "server", []),
        ("cors.py", "CORSMiddleware é a única fonte de verdade de origem permitida (ver comentário no arquivo)", False, "server", []),
        ("security_headers.py", "middleware de headers de segurança padrão (X-Frame-Options, CSP, HSTS...)", False, "server", []),
        ("auth/", None, True, "server", [
            ("rotas.py", "login, CRUD de usuário, troca de senha, (des)bloqueio de conta, trilha de segurança", False, "server", []),
            ("dependencia.py", "exigir_usuario/administrador/desenvolvedor/modulo_financeiro — checagem de sessão", False, "server", []),
            ("decorador_rota.py", "@rota_protegida — decorator usado por toda rota autenticada (ver seção própria abaixo)", False, "server", []),
            ("rate_limit.py", "limite de tentativas em memória (login, troca de senha, criação de usuário)", False, "server", []),
        ]),
        ("auditoria/", None, True, "server", [
            ("rotas.py", "roda a auditoria ao vivo por módulo + histórico de achados", False, "server", []),
        ]),
        ("ferramentas/", None, True, "server", [
            ("juntar_excel.py", "upload de 2 planilhas .xlsx e junção (empilha, faz JOIN ou lado-a-lado)", False, "server", []),
        ]),
        ("financeiro/", "rotas HTTP do módulo Financeiro", True, "server", [
            ("relatorios/", "1 arquivo por relatório fixo (SQL + rotas), mais os compartilhados:", True, "server", [
                ("relatorio_customizado.py", 'rotas do construtor de relatório sob demanda ("Criar Relatório")', False, "server", []),
                ("relatorio_customizado_sql.py", "lógica pura de resolução de JOIN/montagem de SQL do item acima", False, "server", []),
                ("filiais.py, cadastros.py", "listas pros selects de filtro (filial, cliente, vendedor, produto...)", False, "server", []),
                ("filtros_sql.py", "utilitário: monta cláusula IN (...) a partir de uma lista de valores", False, "server", []),
            ]),
            ("previsao.py", "rotas de Previsão (Vendas e Fluxo de Caixa) — projeção por regressão linear", False, "server", []),
            ("historico.py", "rotas REST do histórico de relatórios gerados pela IA", False, "server", []),
            ("layouts.py", 'presets de coluna/filtro salvos por usuário na tela "Criar Relatório"', False, "server", []),
            ("categoria_cores.py", "cor personalizada por categoria (usado nos gráficos)", False, "server", []),
            ("ia.py", "registra as tools de IA + /api/financeiro/chat + /api/financeiro/relatorio/exportar", False, "server", []),
        ]),
    ]),
    ("tools/", None, True, "tools", [
        ("connectivity.py", "teste de conexão com o Oracle (genérico, qualquer módulo pode usar)", False, "tools", []),
        ("auth/", None, True, "tools", [
            ("usuarios.py", "CRUD de usuário, autenticação, bloqueio por tentativas erradas", False, "tools", []),
            ("papeis.py", "fonte única de verdade de quem acessa o quê (ver seção própria abaixo)", False, "tools", []),
            ("token.py", "geração/verificação do JWT de sessão", False, "tools", []),
            ("eventos_seguranca.py", "trilha de auditoria (login, criação/exclusão de usuário, bloqueio...)", False, "tools", []),
            ("cli.py", "agente-oracle-criar-usuario — bootstrap do primeiro admin", False, "tools", []),
        ]),
        ("auditoria/", None, True, "tools", [
            ("historico.py", "CRUD dos achados de auditoria", False, "tools", []),
            ("dispensados.py", 'achados que um usuário marcou como "não é problema"', False, "tools", []),
        ]),
        ("ferramentas/", None, True, "tools", [
            ("juntar_excel.py", "lógica pura de junção de planilha (sem HTTP)", False, "tools", []),
        ]),
        ("financeiro/", None, True, "tools", [
            ("consulta_livre.py", "SQL livre gerado pela IA, com validação de segurança", False, "tools", []),
            ("historico.py", "dedup e CRUD do histórico de relatórios do Financeiro", False, "tools", []),
        ]),
    ]),
])

BACKEND_RESUMO = ("src/agente_oracle/", None, True, "root", [
    ("config.py", "configurações (lidas de .env) + validação da chave de auth no startup", False, "root", []),
    ("relatorios.py", "gerador de Excel (.xlsx) compartilhado por todo relatório", False, "root", []),
    ("agent/", "orquestração do agente de IA (prompt, schema de views liberadas, loop de chamada ao Ollama)", True, "agent", []),
    ("db/", "as duas conexões de banco (Postgres sempre + Oracle/negócio conforme DB_BACKEND)", True, "db", []),
    ("server/", "rotas HTTP — parsing de request, autenticação/autorização e formato da resposta", True, "server", []),
    ("tools/", "lógica de negócio e acesso a dado, chamada por rotas HTTP e/ou pelo agente de IA", True, "tools", []),
])

FRONTEND = ("frontend/grupoConceitoMCP/src/app/", None, True, "root", [
    ("pages/", "uma pasta por tela, incluindo pages/modulos/{financeiro,estoque}/", True, "pages", []),
    ("componentes/", "UI reutilizável entre telas (tabela, dialog, seletor de arquivo...)", True, "componentes", []),
    ("servicos/", "estado compartilhado (sessão, guards) + funções puras reaproveitadas entre páginas "
                  "(mensagens-erro.ts, download-arquivo.ts, ordenacao-tabela.ts)", True, "servicos", []),
    ("dadosRelatorios/", "configuração/metadado estático dos relatórios (dado, não lógica)", True, "dadosRelatorios", []),
])


def coletar_linhas(children, depth, prefixo, linhas):
    for i, node in enumerate(children):
        nome, comentario, eh_dir, grupo, sub = node
        eh_ultimo = i == len(children) - 1
        linhas.append({
            "depth": depth, "nome": nome, "comentario": comentario,
            "eh_dir": eh_dir, "grupo": grupo, "prefixo": list(prefixo), "eh_ultimo": eh_ultimo,
        })
        if sub:
            coletar_linhas(sub, depth + 1, prefixo + [not eh_ultimo], linhas)


def escapar(texto):
    return (texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                 .replace('"', "&quot;"))


def gerar_svg(raiz, titulo_eyebrow, paleta):
    nome_raiz, _, _, _, filhos = raiz
    linhas = []
    coletar_linhas(filhos, 1, [], linhas)

    altura = HEADER_H + (len(linhas) + 1) * ROW_H + FOOTER_H
    partes = []
    partes.append(f'<svg viewBox="0 0 {CANVAS_W} {altura}" xmlns="http://www.w3.org/2000/svg">')
    partes.append(f"""  <style>
    <![CDATA[
    @import url('https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
    text {{ font-family: 'IBM Plex Sans', 'Segoe UI', sans-serif; }}
    .eyebrow {{ font-family: 'IBM Plex Mono', 'JetBrains Mono', ui-monospace, monospace; font-size: 12px; letter-spacing: 0.24em; fill: {paleta["root"]}; opacity: 0.85; }}
    .raiz {{ font-family: 'Chakra Petch', 'Segoe UI', sans-serif; font-weight: 700; font-size: 22px; fill: {paleta["text"]}; }}
    .pasta {{ font-family: 'IBM Plex Mono', 'JetBrains Mono', ui-monospace, monospace; font-weight: 600; font-size: 13px; }}
    .arquivo {{ font-family: 'IBM Plex Mono', 'JetBrains Mono', ui-monospace, monospace; font-size: 13px; fill: {paleta["text"]}; }}
    .comentario {{ font-family: 'IBM Plex Sans', 'Segoe UI', sans-serif; font-size: 12.5px; fill: {paleta["text_dim"]}; }}
    .guia {{ stroke: {paleta["guia"]}; stroke-width: 1.2; }}
    ]]>
  </style>
  <defs>
    <g id="ic-pasta"><path d="M2 5.5a1.5 1.5 0 0 1 1.5-1.5h3.4l1.3 1.6h6.3A1.5 1.5 0 0 1 16 7.1v6.4A1.5 1.5 0 0 1 14.5 15h-11A1.5 1.5 0 0 1 2 13.5Z"/></g>
    <g id="ic-arquivo"><path d="M4 2.5h6l3.5 3.5v9A1.5 1.5 0 0 1 12 16.5H4A1.5 1.5 0 0 1 2.5 15V4A1.5 1.5 0 0 1 4 2.5Z"/><path d="M10 2.5V6h3.5"/></g>
    <pattern id="grade-fundo-arvore" width="34" height="34" patternUnits="userSpaceOnUse">
      <path d="M34 0H0V34" fill="none" stroke="{paleta["bg_grid"]}" stroke-width="1" />
    </pattern>
  </defs>
""")
    partes.append(f'  <rect x="0" y="0" width="{CANVAS_W}" height="{altura}" fill="{paleta["bg"]}" />')
    partes.append(f'  <rect x="0" y="0" width="{CANVAS_W}" height="{altura}" fill="url(#grade-fundo-arvore)" />')

    partes.append(f'  <text class="eyebrow" x="{MARGIN_L}" y="34">{escapar(titulo_eyebrow)}</text>')
    partes.append(f'  <use href="#ic-pasta" x="{MARGIN_L}" y="52" width="22" height="22" fill="none" stroke="{paleta["root"]}" stroke-width="1.4" />')
    partes.append(f'  <text class="raiz" x="{MARGIN_L + 30}" y="68">{escapar(nome_raiz)}</text>')
    partes.append(f'  <line x1="{MARGIN_L}" y1="{HEADER_H - 12}" x2="{CANVAS_W - MARGIN_R}" y2="{HEADER_H - 12}" stroke="{paleta["linha"]}" stroke-width="1" />')

    for idx, linha in enumerate(linhas):
        y = HEADER_H + idx * ROW_H
        y_meio = y + ROW_H / 2
        depth = linha["depth"]
        cor = paleta[linha["grupo"]]

        # linhas-guia dos ancestrais (continuam para baixo quando o ancestral ainda tem irmao depois)
        for col, continua in enumerate(linha["prefixo"]):
            if continua:
                x = MARGIN_L + col * INDENT + 8
                partes.append(f'    <line class="guia" x1="{x}" y1="{y}" x2="{x}" y2="{y + ROW_H}" />')

        # conector do proprio item (canto ou T)
        x_col = MARGIN_L + (depth - 1) * INDENT + 8
        partes.append(f'    <line class="guia" x1="{x_col}" y1="{y}" x2="{x_col}" y2="{y_meio if linha["eh_ultimo"] else y + ROW_H}" />')
        partes.append(f'    <line class="guia" x1="{x_col}" y1="{y_meio}" x2="{x_col + 14}" y2="{y_meio}" />')

        x_icone = x_col + 18
        x_nome = x_icone + 20
        if linha["eh_dir"]:
            partes.append(f'    <use href="#ic-pasta" x="{x_icone}" y="{y_meio - 8}" width="16" height="16" fill="none" stroke="{cor}" stroke-width="1.5" />')
            partes.append(f'    <text class="pasta" x="{x_nome}" y="{y_meio + 4}" fill="{cor}">{escapar(linha["nome"])}</text>')
        else:
            partes.append(f'    <use href="#ic-arquivo" x="{x_icone}" y="{y_meio - 8}" width="15" height="15" fill="none" stroke="{paleta["icone_arquivo"]}" stroke-width="1.3" />')
            partes.append(f'    <text class="arquivo" x="{x_nome}" y="{y_meio + 4}">{escapar(linha["nome"])}</text>')

        if linha["comentario"]:
            partes.append(f'    <text class="comentario" x="{COMENTARIO_X}" y="{y_meio + 4}"># {escapar(linha["comentario"])}</text>')

    partes.append("</svg>")
    return "\n".join(partes)


if __name__ == "__main__":
    pasta = os.path.dirname(os.path.abspath(__file__))
    arvores = [
        (BACKEND, "ESTRUTURA DO PROJETO — BACKEND", "arvore-backend"),
        (BACKEND_RESUMO, "ESTRUTURA DO PROJETO — BACKEND", "arvore-backend-resumo"),
        (FRONTEND, "ESTRUTURA DO PROJETO — FRONTEND", "arvore-frontend"),
    ]
    for raiz, titulo, prefixo_arquivo in arvores:
        for sufixo, paleta in (("dark", DARK), ("light", LIGHT)):
            caminho = os.path.join(pasta, f"{prefixo_arquivo}-{sufixo}.svg")
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(gerar_svg(raiz, titulo, paleta))
            print(f"escrito: {caminho}")
    print("OK")
