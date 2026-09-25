import { Component, effect, inject } from '@angular/core';
import { ChatFinanceiro, ErroChat, NotificacaoChat } from '../../servicos/chat-financeiro/chat-financeiro';
import { GerenciadorToasts } from '../../servicos/gerenciador-toasts/gerenciador-toasts';

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

  private readonly toasts = new GerenciadorToasts();
  protected readonly idsToastsVisiveis = this.toasts.idsVisiveis;

  constructor() {
    effect(() => {
      this.toasts.processar(this.chat.notificacoes());
      this.toasts.processar(this.chat.erros());
    });
  }

  protected descartar(notificacaoId: string): void {
    this.chat.marcarComoVista(notificacaoId);
    this.toasts.remover(notificacaoId);
  }

  protected descartarErro(erroId: string): void {
    this.chat.marcarErroComoVisto(erroId);
    this.toasts.remover(erroId);
  }

  protected erroPorId(erroId: string): ErroChat | null {
    return this.chat.erros().find((item) => item.id === erroId) ?? null;
  }

  protected notificacaoPorId(notificacaoId: string): NotificacaoChat | null {
    return this.chat.notificacoes().find((item) => item.id === notificacaoId) ?? null;
  }

  protected verConversa(notificacaoId: string): void {
    this.toasts.remover(notificacaoId);
    this.chat.abrirConversa(notificacaoId);
  }
}
