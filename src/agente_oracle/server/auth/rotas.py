from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.server.auth.dependencia import exigir_administrador, exigir_desenvolvedor, exigir_usuario
from agente_oracle.server.auth.rate_limit import limpar, registrar_falha, segundos_ate_liberar
from agente_oracle.server.cors import CORS_HEADERS, resposta_preflight
from agente_oracle.tools.auth import eventos_seguranca, papeis
from agente_oracle.tools.auth.token import gerar_token
from agente_oracle.tools.auth.usuarios import (
    UsuarioJaExiste,
    alterar_senha,
    atualizar_perfil,
    autenticar,
    criar_usuario,
    deletar_usuario,
    desbloquear_usuario,
    esta_bloqueado,
    listar_usuarios,
    registrar_tentativa_falha,
    senha_fraca,
)

# Limite de tamanho da foto (string base64, já com o prefixo "data:...;base64,")
# — generoso o bastante pra uma foto de perfil comum, sem deixar a tabela
# crescer sem controle.
_TAMANHO_MAXIMO_FOTO = 2_000_000

_MENSAGEM_BLOQUEADO = "Sua conta foi bloqueada após 3 tentativas de login incorretas. Contate o time de TI pra desbloquear."


def _resposta_limite_excedido(espera: int, mensagem: str) -> JSONResponse:
    return JSONResponse(
        {
            "erro": mensagem,
            # Campo numérico à parte pra tela montar uma contagem regressiva ao
            # vivo, em vez de mostrar só o texto fixo com o valor de quando a
            # resposta chegou.
            "segundos_espera": espera,
        },
        status_code=429,
        headers={**CORS_HEADERS, "Retry-After": str(espera)},
    )


def registrar(mcp) -> None:
    @mcp.custom_route("/api/auth/login", methods=["POST", "OPTIONS"])
    async def login_route(request: Request) -> Response:
        """Endpoint HTTP usado pela tela de login do frontend."""
        if request.method == "OPTIONS":
            return resposta_preflight()

        corpo = await request.json()
        usuario = str(corpo.get("usuario", "")).strip()
        senha = str(corpo.get("senha", ""))

        # Checado antes até do rate limit: uma conta já bloqueada sempre
        # devolve a mensagem específica, em vez de às vezes cair no 429
        # genérico dependendo de qual dos dois contadores está mais "fresco"
        # (o bloqueio persistente não expira sozinho; o rate limit sim).
        if usuario and esta_bloqueado(usuario):
            return JSONResponse({"erro": _MENSAGEM_BLOQUEADO}, status_code=403, headers=CORS_HEADERS)

        chave_bloqueio = usuario or "desconhecido"
        espera = segundos_ate_liberar(chave_bloqueio)
        if espera is not None:
            return _resposta_limite_excedido(
                espera, f"Você errou a senha muitas vezes seguidas. Por segurança, tente de novo em {espera} segundos."
            )

        dados = autenticar(usuario, senha) if usuario and senha else None
        if dados is None:
            registrar_falha(chave_bloqueio)
            if usuario:
                eventos_seguranca.registrar("login_falha", usuario_afetado=usuario)
                if registrar_tentativa_falha(usuario):
                    return JSONResponse({"erro": _MENSAGEM_BLOQUEADO}, status_code=403, headers=CORS_HEADERS)
            return JSONResponse({"erro": "Usuário ou senha inválidos."}, status_code=401, headers=CORS_HEADERS)

        limpar(chave_bloqueio)
        eventos_seguranca.registrar("login_sucesso", usuario_afetado=dados["usuario"])
        token = gerar_token(dados["id"], dados["usuario"], dados["nome"], dados["papeis"])
        return JSONResponse(
            {
                "token": token,
                "usuario": dados["usuario"],
                "nome": dados["nome"],
                "foto": dados.get("foto"),
                "papeis": dados["papeis"],
                # Calculados aqui só pra UI decidir o que mostrar (sidebar) — a
                # autorização de verdade em cada rota é sempre recalculada a
                # partir de `papeis`, nunca confia num campo guardado no token.
                "administrador": papeis.eh_administrador(dados["papeis"]),
                "modulos": papeis.modulos_liberados(dados["papeis"]),
            },
            headers=CORS_HEADERS,
        )

    @mcp.custom_route("/api/auth/papeis", methods=["GET", "OPTIONS"])
    async def listar_papeis_route(request: Request) -> Response:
        """Endpoint HTTP usado pela tela de administração de usuários, pra
        popular o seletor de papéis do formulário de cadastro."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_administrador(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        return JSONResponse(
            [{"slug": papel.slug, "rotulo": papel.rotulo} for papel in papeis.PAPEIS_DISPONIVEIS],
            headers=CORS_HEADERS,
        )

    @mcp.custom_route("/api/auth/usuarios", methods=["GET", "POST", "OPTIONS"])
    async def usuarios_route(request: Request) -> Response:
        """Endpoint HTTP usado pela tela de administração de usuários: lista
        (GET) e cadastra (POST) usuários — restrito a administradores."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, POST, OPTIONS")

        usuario_ou_erro = exigir_administrador(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        if request.method == "GET":
            return JSONResponse(listar_usuarios(), headers=CORS_HEADERS)

        # Namespace própria ("criar_usuario:") pra não compartilhar contador
        # com o rate limit do login — limita quantas contas um mesmo admin
        # consegue criar num intervalo curto (proteção contra abuso em caso
        # de token de admin comprometido), independente de cada tentativa
        # dar certo ou não.
        chave_rate_limit = f"criar_usuario:{usuario_ou_erro['usuario']}"
        espera = segundos_ate_liberar(chave_rate_limit)
        if espera is not None:
            return _resposta_limite_excedido(espera, f"Muitas contas criadas em pouco tempo. Tente de novo em {espera} segundos.")
        registrar_falha(chave_rate_limit)

        corpo = await request.json()
        usuario = str(corpo.get("usuario", "")).strip()
        senha = str(corpo.get("senha", ""))
        nome = str(corpo.get("nome", "")).strip()
        papeis_pedidos = [str(papel).strip() for papel in corpo.get("papeis", []) if str(papel).strip()]

        if not usuario or not senha or not nome or not papeis_pedidos:
            return JSONResponse(
                {"erro": "Preencha usuário, nome, senha e ao menos um papel."}, status_code=400, headers=CORS_HEADERS
            )

        erro_senha = senha_fraca(senha)
        if erro_senha:
            return JSONResponse({"erro": erro_senha}, status_code=400, headers=CORS_HEADERS)

        slugs_validos = {papel.slug for papel in papeis.PAPEIS_DISPONIVEIS}
        if not set(papeis_pedidos).issubset(slugs_validos):
            return JSONResponse({"erro": "Papel inválido."}, status_code=400, headers=CORS_HEADERS)

        papeis_de_quem_cria = usuario_ou_erro.get("papeis", [])
        if not all(papeis.pode_atribuir_papel(papeis_de_quem_cria, papel) for papel in papeis_pedidos):
            return JSONResponse(
                {"erro": "Você não tem permissão pra atribuir um dos papéis selecionados."},
                status_code=403,
                headers=CORS_HEADERS,
            )

        try:
            usuario_criado = criar_usuario(usuario, senha, nome, papeis_pedidos)
        except UsuarioJaExiste as erro:
            return JSONResponse({"erro": str(erro)}, status_code=400, headers=CORS_HEADERS)

        eventos_seguranca.registrar(
            "usuario_criado",
            usuario_afetado=usuario,
            realizado_por=usuario_ou_erro["usuario"],
            detalhes={"papeis": papeis_pedidos},
        )
        return JSONResponse(
            {chave: valor for chave, valor in usuario_criado.items() if chave != "senha_hash"},
            status_code=201,
            headers=CORS_HEADERS,
        )

    @mcp.custom_route("/api/auth/perfil", methods=["PATCH", "OPTIONS"])
    async def atualizar_perfil_route(request: Request) -> Response:
        """Autoatendimento: usuário logado atualiza o próprio nome e/ou foto
        — nunca o de outra pessoa (o alvo é sempre quem está no token)."""
        if request.method == "OPTIONS":
            return resposta_preflight("PATCH, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        corpo = await request.json()
        nome = corpo.get("nome")
        foto = corpo.get("foto")

        nome = nome.strip() if isinstance(nome, str) else None
        if nome == "":
            return JSONResponse({"erro": "Nome não pode ficar em branco."}, status_code=400, headers=CORS_HEADERS)

        if isinstance(foto, str) and len(foto) > _TAMANHO_MAXIMO_FOTO:
            return JSONResponse({"erro": "Imagem muito grande."}, status_code=400, headers=CORS_HEADERS)
        foto = foto if isinstance(foto, str) else None

        if nome is None and foto is None:
            return JSONResponse({"erro": "Nada pra atualizar."}, status_code=400, headers=CORS_HEADERS)

        perfil = atualizar_perfil(usuario_ou_erro["usuario"], nome=nome, foto=foto)
        return JSONResponse(
            {"usuario": perfil["usuario"], "nome": perfil["nome"], "foto": perfil.get("foto")},
            headers=CORS_HEADERS,
        )

    @mcp.custom_route("/api/auth/senha", methods=["PATCH", "OPTIONS"])
    async def alterar_senha_route(request: Request) -> Response:
        """Autoatendimento: usuário logado troca a própria senha, confirmando
        a senha atual antes."""
        if request.method == "OPTIONS":
            return resposta_preflight("PATCH, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        # Namespace própria ("senha:") pra não compartilhar contador com o
        # rate limit do login — sem isso, alguém com um token roubado (ainda
        # válido) mas sem saber a senha atual podia tentar adivinhá-la à
        # vontade nessa rota.
        chave_rate_limit = f"senha:{usuario_ou_erro['usuario']}"
        espera = segundos_ate_liberar(chave_rate_limit)
        if espera is not None:
            return _resposta_limite_excedido(espera, f"Muitas tentativas. Tente de novo em {espera} segundos.")

        corpo = await request.json()
        senha_atual = str(corpo.get("senha_atual", ""))
        senha_nova = str(corpo.get("senha_nova", ""))

        if not senha_nova or senha_nova == senha_atual:
            return JSONResponse(
                {"erro": "Informe uma senha nova diferente da atual."}, status_code=400, headers=CORS_HEADERS
            )

        erro_senha = senha_fraca(senha_nova)
        if erro_senha:
            return JSONResponse({"erro": erro_senha}, status_code=400, headers=CORS_HEADERS)

        sucesso = alterar_senha(usuario_ou_erro["usuario"], senha_atual, senha_nova)
        if not sucesso:
            registrar_falha(chave_rate_limit)
            return JSONResponse({"erro": "Senha atual incorreta."}, status_code=400, headers=CORS_HEADERS)

        limpar(chave_rate_limit)
        return JSONResponse({"ok": True}, headers=CORS_HEADERS)

    @mcp.custom_route("/api/auth/usuarios/{id}", methods=["DELETE", "OPTIONS"])
    async def apagar_usuario_route(request: Request) -> Response:
        """Endpoint HTTP usado pela tela de administração de usuários pra
        apagar um usuário — restrito a administradores."""
        if request.method == "OPTIONS":
            return resposta_preflight("DELETE, OPTIONS")

        usuario_ou_erro = exigir_administrador(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        id_usuario = request.path_params["id"]
        if id_usuario == usuario_ou_erro.get("sub"):
            return JSONResponse(
                {"erro": "Você não pode apagar o seu próprio usuário."}, status_code=400, headers=CORS_HEADERS
            )

        try:
            id_numerico = int(id_usuario)
        except ValueError:
            return JSONResponse({"erro": "Usuário não encontrado."}, status_code=404, headers=CORS_HEADERS)

        usuario_apagado = deletar_usuario(id_numerico)
        if usuario_apagado is None:
            return JSONResponse({"erro": "Usuário não encontrado."}, status_code=404, headers=CORS_HEADERS)

        eventos_seguranca.registrar(
            "usuario_apagado", usuario_afetado=usuario_apagado, realizado_por=usuario_ou_erro["usuario"]
        )
        return JSONResponse({"ok": True}, headers=CORS_HEADERS)

    @mcp.custom_route("/api/auth/usuarios/{id}/desbloquear", methods=["PATCH", "OPTIONS"])
    async def desbloquear_usuario_route(request: Request) -> Response:
        """Desbloqueia uma conta travada após 3 tentativas de login erradas
        seguidas — restrito ao time de TI (papel `desenvolvedor`)."""
        if request.method == "OPTIONS":
            return resposta_preflight("PATCH, OPTIONS")

        usuario_ou_erro = exigir_desenvolvedor(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        try:
            id_numerico = int(request.path_params["id"])
        except ValueError:
            return JSONResponse({"erro": "Usuário não encontrado."}, status_code=404, headers=CORS_HEADERS)

        usuario_desbloqueado = desbloquear_usuario(id_numerico)
        if usuario_desbloqueado is None:
            return JSONResponse({"erro": "Usuário não encontrado."}, status_code=404, headers=CORS_HEADERS)

        eventos_seguranca.registrar(
            "conta_desbloqueada", usuario_afetado=usuario_desbloqueado, realizado_por=usuario_ou_erro["usuario"]
        )
        return JSONResponse({"ok": True}, headers=CORS_HEADERS)

    @mcp.custom_route("/api/auth/eventos-seguranca", methods=["GET", "OPTIONS"])
    async def eventos_seguranca_route(request: Request) -> Response:
        """Trilha de auditoria de login/administração de contas — restrita
        ao time de TI (papel `desenvolvedor`), pra investigar incidentes."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_desenvolvedor(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        return JSONResponse(eventos_seguranca.listar(), headers=CORS_HEADERS)
