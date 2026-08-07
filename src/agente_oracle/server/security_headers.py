"""Headers de segurança padrão aplicados em TODA resposta — middleware (não
header espalhado rota a rota, mesma lição do bug de CORS: header colocado
manualmente em cada rota é fácil de esquecer numa rota nova; middleware
central não tem como esquecer).

Esse backend é uma API só (nunca serve HTML de verdade — o frontend Angular
é servido/hospedado à parte), então o valor real dos headers abaixo é
defesa em profundidade: se algum dia uma resposta acabar sendo interpretada
como página (erro de proxy, navegação direta a uma URL da API, etc.), esses
headers evitam que o navegador tente "adivinhar" o tipo de conteúdo, evitam
embutir a resposta num `<iframe>` de outro site (clickjacking), e travam
qualquer script/conteúdo ativo por padrão (`Content-Security-Policy`).
`Strict-Transport-Security` não tem efeito nenhum enquanto o acesso for só
HTTP (dentro da rede da empresa) — mas já fica pronto pra quando o deploy
passar a usar HTTPS, sem precisar lembrar de adicionar depois."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_HEADERS_PADRAO = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}


class HeadersDeSegurancaMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        resposta = await call_next(request)
        for chave, valor in _HEADERS_PADRAO.items():
            resposta.headers.setdefault(chave, valor)
        return resposta
