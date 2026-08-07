from starlette.responses import JSONResponse

# Vazio de propósito — NÃO colocar "Access-Control-Allow-Origin: *" aqui.
# `CORSMiddleware` (adicionado em `server/app.py:main()`) é a ÚNICA fonte de
# verdade pra esse header, restrito às origens de `Settings.allowed_origins`.
# Antes, cada rota espalhava `**CORS_HEADERS` com um `*` fixo — como
# `MutableHeaders` só REESCREVE o header quando a origem da requisição já
# está na lista permitida, uma origem NÃO permitida simplesmente mantinha o
# `*` da rota intocado, ou seja, a restrição do middleware nunca era
# aplicada de verdade pra origem nenhuma. Mantido como dict vazio (em vez de
# apagar todo `**CORS_HEADERS` espalhado pelas ~24 rotas que importam isso)
# pra ser um fix de uma linha só, sem risco de quebrar alguma rota esquecida.
CORS_HEADERS: dict[str, str] = {}


def resposta_preflight(metodos: str = "POST, OPTIONS") -> JSONResponse:
    return JSONResponse(
        {},
        headers={
            **CORS_HEADERS,
            "Access-Control-Allow-Methods": metodos,
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        },
    )
