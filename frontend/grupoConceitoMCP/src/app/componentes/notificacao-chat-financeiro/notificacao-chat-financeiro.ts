import { Component, effect, inject, signal } from '@angular/core';
import { ChatFinanceiro, ErroChat, NotificacaoChat } from '../../servicos/chat-financeiro';

/** Duração que um toast fica visível antes de sumir sozinho — a notificação
 * em si continua existindo no serviço (não vista) até o usuário interagir,
 * só o cartão flutuante que some (ver docstring da classe, abaixo). */
const DURACAO_TOAST_MS = 8000;

/** Popup (canto inferior direito) avisando quando o agente termina de
 * responder — mesmo papel de `NotificacaoAnaliseCurriculo` pro RH, aqui pro
 * chat do Financeiro (`ChatFinanceiro.enviarMensagem`), que agora roda
 * independente da tela estar montada ou não. Aparece só quando a resposta
 * fica pronta (nunca já ao enviar) — o botão de enviar desabilitado já
 * avisa que tem algo em andamento, sem precisar de outro popup nesse
 * meio-tempo. */
@Component({
  selector: 'app-notificacao-chat-financeiro',
  imports: [],
  templateUrl: './notificacao-chat-financeiro.html',
  styleUrl: './notificacao-chat-financeiro.scss',
})
export class NotificacaoChatFinanceiro {
  protected readonly chat = inject(ChatFinanceiro);

  private readonly idsJaMostrados = new Set<string>();
  protected readonly idsToastsVisiveis = signal<string[]>([]);

  constructor() {
    effect(() => {
      for (const notificacao of this.chat.notificacoes()) {
        if (notificacao.vista || this.idsJaMostrados.has(notificacao.id)) {
          continue;
        }
        this.idsJaMostrados.add(notificacao.id);
        this.idsToastsVisiveis.update((atual) => [...atual, notificacao.id]);
        setTimeout(() => this.removerToast(notificacao.id), DURACAO_TOAST_MS);
      }
      for (const erro of this.chat.erros()) {
        if (erro.vista || this.idsJaMostrados.has(erro.id)) {
          continue;
        }
        this.idsJaMostrados.add(erro.id);
        this.idsToastsVisiveis.update((atual) => [...atual, erro.id]);
        setTimeout(() => this.removerToast(erro.id), DURACAO_TOAST_MS);
      }
    });
  }

  // removerToast é usada por descartar, descartarErro E verConversa —
  // compartilhada, fica antes das três.
  private removerToast(notificacaoId: string): void {
    this.idsToastsVisiveis.update((atual) => atual.filter((item) => item !== notificacaoId));
  }

  protected descartar(notificacaoId: string): void {
    this.chat.marcarComoVista(notificacaoId);
    this.removerToast(notificacaoId);
  }

  protected descartarErro(erroId: string): void {
    this.chat.marcarErroComoVisto(erroId);
    this.removerToast(erroId);
  }

  protected erroPorId(erroId: string): ErroChat | null {
    return this.chat.erros().find((item) => item.id === erroId) ?? null;
  }

  protected notificacaoPorId(notificacaoId: string): NotificacaoChat | null {
    return this.chat.notificacoes().find((item) => item.id === notificacaoId) ?? null;
  }

  protected verConversa(notificacaoId: string): void {
    this.removerToast(notificacaoId);
    this.chat.abrirConversa(notificacaoId);
  }
}
