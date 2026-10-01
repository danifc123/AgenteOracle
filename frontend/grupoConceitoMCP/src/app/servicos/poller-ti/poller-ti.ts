import {
  HttpClient,
  HttpDownloadProgressEvent,
  HttpEventType,
  HttpResponse,
} from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Subscription } from 'rxjs';
import { EtapaProcesso } from '../../componentes/painel-processo/painel-processo';
import { MCP_API_BASE_URL } from '../../app-config';

interface RespostaStatusPoller {
  etapas: EtapaProcesso[];
  ultima_rodada_em: string | null;
  proxima_rodada_em: string | null;
  erro: string | null;
}

const LIMITE_LINHAS_LOG = 200;

/** Status ao vivo do poller do GLPI (`server/ti/chamados.py::_executar_uma_rodada`)
 * — alimenta o `app-painel-processo` da Auditoria de Chamados. Aberto pro
 * módulo TI inteiro (`exigir_modulo_ti` no backend), não só desenvolvedor. */
@Injectable({ providedIn: 'root' })
export class PollerTi {
  private readonly http = inject(HttpClient);

  readonly etapas = signal<EtapaProcesso[]>([]);
  readonly ultimaRodadaEm = signal<string | null>(null);
  readonly proximaRodadaEm = signal<string | null>(null);
  readonly erro = signal<string | null>(null);
  readonly logs = signal<string[]>([]);

  private assinaturaLogs: Subscription | null = null;

  carregar(): void {
    this.http.get<RespostaStatusPoller>(`${MCP_API_BASE_URL}/api/ti/poller/status`).subscribe({
      next: (resposta) => {
        this.etapas.set(resposta.etapas);
        this.ultimaRodadaEm.set(resposta.ultima_rodada_em);
        this.proximaRodadaEm.set(resposta.proxima_rodada_em);
        this.erro.set(resposta.erro);
      },
    });
  }

  /** Abre a conexão de log ao vivo (`/api/ti/poller/logs`) — diferente de
   * `gerarPrevisaoStream` (`servicos/previsao-stream/`), essa NUNCA
   * resolve: fica aberta até `fecharStreamDeLogs()` cancelar a inscrição
   * de verdade (fecha a requisição HTTP). Mesma técnica de leitura
   * incremental (`observe:'events'`/`partialText`) pelo mesmo motivo de
   * lá — `EventSource` nativo não manda o header `Authorization`. Linha
   * vazia (heartbeat do backend) é ignorada. Chamar de novo com uma
   * conexão já aberta não faz nada (evita abrir duas). */
  abrirStreamDeLogs(): void {
    if (this.assinaturaLogs) {
      return;
    }
    let comprimentoVisto = 0;
    let bufferPendente = '';

    this.assinaturaLogs = this.http
      .request('GET', `${MCP_API_BASE_URL}/api/ti/poller/logs`, {
        observe: 'events',
        responseType: 'text',
        reportProgress: true,
      })
      .subscribe({
        next: (evento) => {
          let textoCompleto: string | null = null;
          if (evento.type === HttpEventType.DownloadProgress) {
            textoCompleto = (evento as HttpDownloadProgressEvent).partialText ?? '';
          } else if (evento.type === HttpEventType.Response) {
            textoCompleto = (evento as HttpResponse<string>).body ?? '';
          }
          if (textoCompleto === null) {
            return;
          }

          const trechoNovo = textoCompleto.slice(comprimentoVisto);
          comprimentoVisto = textoCompleto.length;
          const partes = (bufferPendente + trechoNovo).split('\n');
          bufferPendente = partes.pop() ?? '';

          const novas = partes.filter((linha) => linha.trim());
          if (novas.length) {
            this.logs.update((atual) => [...atual, ...novas].slice(-LIMITE_LINHAS_LOG));
          }
        },
      });
  }

  fecharStreamDeLogs(): void {
    this.assinaturaLogs?.unsubscribe();
    this.assinaturaLogs = null;
    this.logs.set([]);
  }
}
