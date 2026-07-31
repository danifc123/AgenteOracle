import { HttpClient, HttpDownloadProgressEvent, HttpEventType, HttpResponse } from '@angular/common/http';

interface LinhaEtapa {
  tipo: 'etapa';
  id: string;
}

interface LinhaResultado<T> {
  tipo: 'resultado';
  dados: T;
}

const MENSAGEM_ERRO_PADRAO = 'Não foi possível gerar a previsão. Verifique se o servidor está em execução.';

/** `gerarPrevisaoStream` usa `responseType: 'text'`, então o corpo de um
 * erro HTTP chega como string crua (não vem parseado em objeto como nas
 * chamadas `.get<T>()` normais) — essa função faz esse parse manualmente
 * pra extrair a mensagem `{"erro": "..."}` que o backend devolve. */
export function mensagemErroPrevisao(erro: unknown): string {
  const corpoBruto = (erro as { error?: unknown } | null)?.error;
  if (typeof corpoBruto !== 'string') {
    return MENSAGEM_ERRO_PADRAO;
  }
  try {
    const corpo = JSON.parse(corpoBruto) as { erro?: string };
    return corpo.erro ?? MENSAGEM_ERRO_PADRAO;
  } catch {
    return MENSAGEM_ERRO_PADRAO;
  }
}

/** Consome uma rota de previsão que responde em NDJSON (uma linha JSON por
 * etapa concluída, terminando em `{"tipo":"resultado","dados":...}`) — usa
 * `HttpClient` com `observe:'events'` em vez de `EventSource` nativo do
 * browser, porque o `EventSource` não permite enviar o header
 * `Authorization: Bearer ...` que o `authInterceptor` injeta em toda
 * chamada. Cada evento de progresso traz o texto acumulado até agora
 * (`partialText`) — só o trecho novo desde a última leitura é reprocessado,
 * e qualquer linha ainda incompleta no fim do trecho novo fica guardada em
 * `bufferPendente` até completar num evento seguinte. */
export function gerarPrevisaoStream<T>(
  http: HttpClient,
  url: string,
  params: Record<string, string>,
  aoEtapaConcluida: (id: string) => void
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    let comprimentoVisto = 0;
    let bufferPendente = '';

    const processarTexto = (textoCompleto: string): void => {
      const trechoNovo = textoCompleto.slice(comprimentoVisto);
      comprimentoVisto = textoCompleto.length;
      if (!trechoNovo) {
        return;
      }

      const partes = (bufferPendente + trechoNovo).split('\n');
      bufferPendente = partes.pop() ?? '';

      for (const linha of partes) {
        if (!linha.trim()) {
          continue;
        }
        const objeto = JSON.parse(linha) as LinhaEtapa | LinhaResultado<T>;
        if (objeto.tipo === 'etapa') {
          aoEtapaConcluida(objeto.id);
        } else {
          resolve(objeto.dados);
        }
      }
    };

    http.request('GET', url, { params, observe: 'events', responseType: 'text', reportProgress: true }).subscribe({
      next: (evento) => {
        if (evento.type === HttpEventType.DownloadProgress) {
          processarTexto((evento as HttpDownloadProgressEvent).partialText ?? '');
        } else if (evento.type === HttpEventType.Response) {
          processarTexto((evento as HttpResponse<string>).body ?? '');
        }
      },
      error: (erro) => reject(erro)
    });
  });
}
