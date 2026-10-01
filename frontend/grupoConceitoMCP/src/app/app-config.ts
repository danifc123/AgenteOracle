// Vazio de propósito — sempre relativo ao próprio host que serviu o
// frontend. Em produção, o Nginx do container do frontend faz proxy de
// `/api` pro backend (mesma origem, sem CORS); no dev local, `ng serve`
// faz o mesmo via `proxy.conf.json`. Nunca aponte isso pra um host fixo —
// quebra assim que o navegador do usuário não for a própria máquina do
// backend (era o caso até aqui: `http://127.0.0.1:8000`, que só funciona
// rodando tudo na mesma máquina).
export const MCP_API_BASE_URL = '';
