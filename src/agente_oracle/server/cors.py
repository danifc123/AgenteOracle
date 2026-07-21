from starlette.responses import JSONResponse

CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}


def resposta_preflight(metodos: str = "POST, OPTIONS") -> JSONResponse:
    return JSONResponse(
        {},
        headers={
            **CORS_HEADERS,
            "Access-Control-Allow-Methods": metodos,
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        },
    )
