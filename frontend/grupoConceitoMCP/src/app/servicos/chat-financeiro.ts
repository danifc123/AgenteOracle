import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { MCP_API_BASE_URL } from '../app-config';
import { ConsultaUsada, MensagemChat } from '../pages/modulos/financeiro/chat/mensagens/chat-mensagens';
import { baixarBlob, extrairNomeArquivo } from './download-arquivo';
import { mensagemErro } from './mensagens-erro';

interface RespostaChat {
  resposta: string;
  consultas: ConsultaUsada[];
}

export interface NotificacaoChat {
  id: string;
  vista: boolean;
}

export interface ErroChat {
  id: string;
  mensagem: string;
  vista: boolean;
}

/** CHAT DO FINANCEIRO EM SEGUNDO PLANO (2026-08)
 *
 * Mesmo papel que `AnaliseCurriculo` cumpre pro RH: `enviarMensagem` dispara
 * o POST e devolve o controle na hora — a tela não precisa ficar montada
 * esperando. O `subscribe` só atualiza `mensagens`/`notificacoes`/`erros`
 * quando o backend responde de verdade, então sair do chat no meio de uma
 * pergunta não perde a resposta: ela chega aqui de qualquer forma, e
 * `NotificacaoChatFinanceiro` (montado uma vez em `layout.html`) mostra um
 * toast com ação "Ver conversa" quando isso acontece.
 *
 * `enviando` é a ÚNICA fonte de verdade do guard "não é full-duplex" (só uma
 * pergunta em voo por vez) — antes vivia como signal local de `Chat`, então
 * sair da tela não bloqueava mais nada; agora bloqueia em qualquer lugar,
 * inclusive se o usuário voltar pro chat antes da resposta chegar. */
@Injectable({ providedIn: 'root' })
export class ChatFinanceiro {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  readonly mensagens = signal<MensagemChat[]>([]);
  readonly enviando = signal(false);
  readonly baixandoSql = signal<string | null>(null);
  readonly notificacoes = signal<NotificacaoChat[]>([]);
  readonly erros = signal<ErroChat[]>([]);

  abrirConversa(notificacaoId: string): void {
    this.marcarComoVista(notificacaoId);
    this.router.navigateByUrl('/financeiro/chat');
  }

  baixarRelatorio(sql: string, titulo: string): void {
    if (this.baixandoSql()) {
      return;
    }
    this.baixandoSql.set(sql);

    this.http
      .post(
        `${MCP_API_BASE_URL}/api/financeiro/relatorio/exportar`,
        { sql, titulo },
        { observe: 'response', responseType: 'blob' },
      )
      .subscribe({
        next: (resposta) => {
          const blob = resposta.body;
          this.baixandoSql.set(null);
          if (!blob) {
            return;
          }
          const nomeArquivo = extrairNomeArquivo(
            resposta.headers.get('content-disposition'),
            'relatorio.xlsx',
          );
          baixarBlob(blob, nomeArquivo);
        },
        error: () => this.baixandoSql.set(null),
      });
  }

  enviarMensagem(texto: string): void {
    if (!texto || this.enviando()) {
      return;
    }

    const historico = this.mensagens().map(({ role, content }) => ({ role, content }));

    this.mensagens.update((atual) => [...atual, { role: 'user', content: texto }]);
    this.enviando.set(true);

    this.http
      .post<RespostaChat>(`${MCP_API_BASE_URL}/api/financeiro/chat`, { mensagem: texto, historico })
      .subscribe({
        next: (resultado) => this.concluirEnvio(resultado),
        error: (erro: HttpErrorResponse) => this.falharEnvio(erro),
      });
  }

  marcarComoVista(notificacaoId: string): void {
    this.notificacoes.update((atual) =>
      atual.map((item) => (item.id === notificacaoId ? { ...item, vista: true } : item)),
    );
  }

  marcarErroComoVisto(erroId: string): void {
    this.erros.update((atual) => atual.map((item) => (item.id === erroId ? { ...item, vista: true } : item)));
  }

  // concluirEnvio e falharEnvio só são usadas por enviarMensagem, logo
  // depois dela (nessa ordem — sucesso e falha do mesmo POST).
  private concluirEnvio(resultado: RespostaChat): void {
    const id = `notif-chat-${Date.now()}`;
    this.mensagens.update((atual) => [
      ...atual,
      { role: 'assistant', content: resultado.resposta, consultas: resultado.consultas },
    ]);
    this.enviando.set(false);
    this.notificacoes.update((atual) => [...atual, { id, vista: false }]);
  }

  private falharEnvio(erro: HttpErrorResponse): void {
    const id = `erro-chat-${Date.now()}`;
    this.enviando.set(false);
    this.erros.update((atual) => [
      ...atual,
      {
        id,
        mensagem: mensagemErro(
          erro,
          'Não foi possível falar com o agente. Verifique se o servidor e o Ollama estão em execução.',
        ),
        vista: false,
      },
    ]);
  }
}
