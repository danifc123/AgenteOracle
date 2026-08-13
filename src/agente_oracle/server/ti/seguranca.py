"""Rota de detecção de segurança do módulo TI — roda sob demanda (nunca em
background), só quando alguém do time clica no botão, mesmo espírito de
`server/auditoria/rotas.py`.

Diferença de propósito em relação à Auditoria de dado: lá, um valor já
identificado é TIRADO dos perfis antes de mandar pra IA (não faz sentido
"redescobrir" um problema de qualidade de dado que não muda sozinho). Aqui
os perfis vão pra IA sempre completos e atualizados — um padrão suspeito
de segurança pode estar PIORANDO a cada execução (mais tentativas, mais
volume), e excluir esse usuário da análise esconderia justamente a
escalada. A deduplicação acontece só na hora de MOSTRAR o achado (nunca
duplica um `(usuario, tipo)` que a IA acabou de reapontar com o que já
estava ativo de uma execução anterior — o achado novo, mais atual,
prevalece)."""

from ollama import AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.ti import perfil_login
from agente_oracle.agent.ti.deteccao_seguranca import AchadoSeguranca, detectar
from agente_oracle.config import settings
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_ti
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.tools.auth import papeis
from agente_oracle.tools.ti import acessos_dados, historico_seguranca

_DIAS_JANELA_ACESSO = 7


def _achado_para_json(achado: AchadoSeguranca) -> dict:
    return {
        "usuario": achado.usuario,
        "sistema": achado.sistema,
        "tipo": achado.tipo,
        "descricao": achado.descricao,
        "evidencia": achado.evidencia,
    }


def registrar(mcp) -> None:
    @mcp.custom_route("/api/ti/seguranca/dispensar", methods=["POST", "OPTIONS"])
    @rota_protegida("POST, OPTIONS", exigir=exigir_modulo_ti)
    async def seguranca_dispensar_route(request: Request, usuario: dict) -> Response:
        """Dispensa um achado — desativa globalmente (some da tela de todo
        mundo do TI e das próximas execuções), mesmo mecanismo de
        `/api/auditoria/dispensar`. Se o padrão persistir, a IA pode
        reencontrar e reapontar numa execução futura."""
        corpo = await request.json()
        usuario_alvo = str(corpo.get("usuario", "")).strip()
        sistema = str(corpo.get("sistema", "")).strip()
        tipo = str(corpo.get("tipo", "")).strip()

        if not (usuario_alvo and sistema and tipo):
            return JSONResponse(
                {"erro": "Informe usuario, sistema e tipo."}, status_code=400, headers=CORS_HEADERS
            )

        atualizado = historico_seguranca.definir_ativo(usuario_alvo, sistema, tipo, False)
        if not atualizado:
            return JSONResponse(
                {"erro": "Achado não encontrado no histórico."}, status_code=404, headers=CORS_HEADERS
            )

        return JSONResponse({"ok": True}, headers=CORS_HEADERS)

    @mcp.custom_route("/api/ti/seguranca/historico", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_ti)
    async def seguranca_historico_route(request: Request, usuario: dict) -> Response:
        """Lista os achados de segurança já encontrados ao longo do tempo —
        nunca expira, ao contrário de `/api/relatorios/historico`. Achado
        desativado só aparece pra quem tem o papel `desenvolvedor` — pra
        quem só tem `ti_admin`/`ti_infraestrutura`, é como se nunca tivesse
        existido (mesma regra de `/api/auditoria/historico`)."""
        registros = historico_seguranca.listar(
            incluir_desativados=papeis.eh_desenvolvedor(usuario.get("papeis", []))
        )
        return JSONResponse(registros, headers=CORS_HEADERS)

    @mcp.custom_route("/api/ti/seguranca", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_ti)
    async def seguranca_route(request: Request, usuario: dict) -> Response:
        """Roda a detecção de segurança ao vivo: agrega login/conta
        recentes do AgenteOracle e do Protheus (`agent/ti/perfil_login.py`)
        e volume de acesso a dado dos últimos dias
        (`tools/ti/acessos_dados.py`), manda pra IA
        (`agent/ti/deteccao_seguranca.py`), salva os achados novos no
        histórico e junta com os que já estavam ativos (sem duplicar
        `(usuario, sistema, tipo)` que a IA acabou de reapontar)."""
        perfis_login = perfil_login.perfil_logins()
        perfis_login_protheus = perfil_login.perfil_logins_protheus(dias=_DIAS_JANELA_ACESSO)
        perfis_acesso = acessos_dados.perfil_acessos(dias=_DIAS_JANELA_ACESSO)

        ollama_client = AsyncClient(host=settings.ollama_host)
        achados_novos = await detectar(
            ollama_client, settings.ollama_model, perfis_login, perfis_login_protheus, perfis_acesso
        )

        chaves_novas = {(achado.usuario, achado.sistema, achado.tipo) for achado in achados_novos}
        achados_ja_conhecidos = [
            achado
            for achado in historico_seguranca.achados_ativos()
            if (achado.usuario, achado.sistema, achado.tipo) not in chaves_novas
        ]

        historico_seguranca.salvar(usuario["sub"], achados_novos)

        achados = achados_novos + achados_ja_conhecidos
        return JSONResponse([_achado_para_json(achado) for achado in achados], headers=CORS_HEADERS)
