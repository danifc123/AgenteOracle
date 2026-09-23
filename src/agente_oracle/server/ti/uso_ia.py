"""Rota HTTP só-leitura do consumo de IA por provedor/modelo, por usuário e
por dia (`tools/ia/auditoria_externa.py::resumo_por_provedor`/
`resumo_por_usuario`/`resumo_diario`), mais o uso de IA especificamente nos
chamados do TI (`tools/ti/uso_ia_chamados.py::resumo_uso` — já existia,
nunca tinha rota) — base da página Tokens do TI
(`pages/modulos/ti/tokens/`) e do bloco "Consumo de IA" no lobby
(`pages/modulos/ti/home/`, atrás de `*appSoDev`). Cobre TI + RH juntos (a
auditoria é única pro processo inteiro), não só chamado. Só desenvolvedor
acessa — mesmo público que já via essa informação quando ainda era um card
dentro do diálogo de Configurações do TI (que também é "visível só para
desenvolvedores")."""

from anyio import to_thread
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_ti
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.auth import papeis, usuarios
from agente_oracle.tools.ia import auditoria_externa
from agente_oracle.tools.ia.auditoria_externa import (
    ResumoTokensDia,
    ResumoTokensProvedor,
    ResumoTokensUsuario,
)
from agente_oracle.tools.ia.cliente_protegido import USUARIO_SISTEMA
from agente_oracle.tools.ti import uso_ia_chamados

_DIAS_PADRAO = 30

# Só os domínios que hoje compartilham a escolha de provedor/modelo (ver
# tools/ia/configuracoes_provedor.py) — financeiro/auditoria ficam de fora
# de propósito.
_DOMINIOS_COBERTOS = ("ti", "rh")

_ROTULO_USUARIO_SISTEMA = "Sistema/Automático"


def _dias_da_query(bruto: str | None) -> int:
    """`bruto` ausente ou não numérico cai no padrão — nunca derruba a
    rota por causa de um `?dias=` mal formado."""
    if bruto is None:
        return _DIAS_PADRAO
    try:
        return int(bruto)
    except ValueError:
        return _DIAS_PADRAO


def _linha_para_json(linha: ResumoTokensProvedor) -> dict:
    return {
        "provedor": linha.provedor,
        "modelo": linha.modelo,
        "chamadas": linha.chamadas,
        "tokens_entrada": linha.tokens_entrada_total,
        "tokens_saida": linha.tokens_saida_total,
        "tokens_raciocinio": linha.tokens_raciocinio_total,
        "tokens_total": linha.tokens_entrada_total + linha.tokens_saida_total,
    }


def _nome_usuario(usuario_id: str, nomes_por_id: dict[str, str]) -> str:
    """`USUARIO_SISTEMA` vira um rótulo fixo (não é uma linha da tabela
    `usuarios`, não passa pelo mapa); usuário que saiu da empresa (ID no
    histórico, sumiu de `usuarios`) cai num fallback — nunca quebra a rota
    por causa de um ID órfão."""
    if usuario_id == USUARIO_SISTEMA:
        return _ROTULO_USUARIO_SISTEMA
    return nomes_por_id.get(usuario_id, f"Usuário #{usuario_id} (removido)")


def _linha_usuario_para_json(linha: ResumoTokensUsuario, nomes_por_id: dict[str, str]) -> dict:
    return {
        "usuario_id": linha.usuario_id,
        "nome": _nome_usuario(linha.usuario_id, nomes_por_id),
        "chamadas": linha.chamadas,
        "tokens_entrada": linha.tokens_entrada_total,
        "tokens_saida": linha.tokens_saida_total,
        "tokens_raciocinio": linha.tokens_raciocinio_total,
        "tokens_total": linha.tokens_entrada_total + linha.tokens_saida_total,
    }


def _linha_dia_para_json(linha: ResumoTokensDia) -> dict:
    return {
        "data": linha.data,
        "chamadas": linha.chamadas,
        "tokens_entrada": linha.tokens_entrada_total,
        "tokens_saida": linha.tokens_saida_total,
        "tokens_total": linha.tokens_entrada_total + linha.tokens_saida_total,
    }


def _chamados_ia_para_json(resumo: uso_ia_chamados.ResumoUsoIa) -> dict:
    return {
        "total_chamados": resumo.total_chamados,
        "avaliados_insuficientes": resumo.total_avaliados_insuficientes,
        "com_fallback_embedding": resumo.total_com_fallback_embedding,
        "duracao_media_ms": resumo.duracao_media_ms,
    }


def _corpo_uso_ia(dias: int) -> dict:
    resumo = auditoria_externa.resumo_por_provedor(dias)
    resumo_usuario = auditoria_externa.resumo_por_usuario(dias)
    resumo_dia = auditoria_externa.resumo_diario(dias)
    nomes_por_id = {str(usuario["id"]): usuario["nome"] for usuario in usuarios.listar_usuarios()}
    return {
        "consumo": [_linha_para_json(linha) for linha in resumo],
        "por_usuario": [_linha_usuario_para_json(linha, nomes_por_id) for linha in resumo_usuario],
        "por_dia": [_linha_dia_para_json(linha) for linha in resumo_dia],
        "tokens_hoje_por_dominio": {
            dominio: auditoria_externa.tokens_hoje(dominio) for dominio in _DOMINIOS_COBERTOS
        },
        "chamados_ia": _chamados_ia_para_json(uso_ia_chamados.resumo_uso(dias)),
    }


def _acesso_negado(usuario: dict) -> str | None:
    """Mensagem de erro se `usuario` não for desenvolvedor, `None` se pode
    passar — módulo TI sozinho (`exigir_modulo_ti`, já checado antes desta
    função) não é suficiente pra essa rota."""
    if papeis.eh_desenvolvedor(usuario.get("papeis", [])):
        return None
    return "Acesso restrito a desenvolvedores."


def registrar(mcp) -> None:
    @mcp.custom_route("/api/ti/uso-ia", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_ti)
    async def uso_ia_route(request: Request, usuario: dict) -> Response:
        """Consumo de tokens dos últimos `dias` dias (padrão 30), agrupado
        por provedor + modelo, mais o total de hoje por domínio. Só
        desenvolvedor — módulo TI sozinho não basta."""
        mensagem = _acesso_negado(usuario)
        if mensagem:
            return JSONResponse({"erro": mensagem}, status_code=403, headers=CORS_HEADERS)
        dias = _dias_da_query(request.query_params.get("dias"))
        corpo = await to_thread.run_sync(_corpo_uso_ia, dias)
        return JSONResponse(corpo, headers=CORS_HEADERS)
