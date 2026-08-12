import { Component, effect, inject, signal } from '@angular/core';
import { AnaliseCurriculo, NotificacaoAnalise } from '../../servicos/analise-curriculo';

/** Duração que um toast fica visível antes de sumir sozinho — a notificação
 * em si continua existindo no serviço (não vista) até o usuário interagir,
 * só o cartão flutuante que some (ver docstring da classe, abaixo). */
const DURACAO_TOAST_MS = 8000;

/** Sino fixo do layout (mesmo papel de `NotificacaoAuditoria`), mas com um
 * comportamento a mais: além de ficar disponível pra consulta, um novo
 * resultado de análise aparece sozinho como um toast (pop-up) no canto
 * inferior direito, em qualquer tela do sistema — é o "avisa quando
 * terminar" que o RH pediu, já que a análise roda em segundo plano
 * (`AnaliseCurriculo.iniciarAnalise`) enquanto o usuário navega livremente.
 *
 * Um toast que some sozinho (sem o usuário interagir) NÃO marca a
 * notificação como vista — ela continua contando pra bolinha vermelha do
 * link "RH" na sidebar, pra quem não estava olhando a tela nesse momento
 * não perder o resultado. */
@Component({
  selector: 'app-notificacao-analise-curriculo',
  imports: [],
  templateUrl: './notificacao-analise-curriculo.html',
  styleUrl: './notificacao-analise-curriculo.scss',
})
export class NotificacaoAnaliseCurriculo {
  protected readonly analise = inject(AnaliseCurriculo);

  private readonly idsJaMostrados = new Set<string>();
  protected readonly idsToastsVisiveis = signal<string[]>([]);

  constructor() {
    effect(() => {
      for (const notificacao of this.analise.notificacoes()) {
        if (notificacao.vista || this.idsJaMostrados.has(notificacao.id)) {
          continue;
        }
        this.idsJaMostrados.add(notificacao.id);
        this.idsToastsVisiveis.update((atual) => [...atual, notificacao.id]);
        setTimeout(() => this.removerToast(notificacao.id), DURACAO_TOAST_MS);
      }
    });
  }

  protected descartar(notificacaoId: string): void {
    this.analise.marcarComoVista(notificacaoId);
    this.removerToast(notificacaoId);
  }

  protected notificacaoPorId(notificacaoId: string): NotificacaoAnalise | null {
    return this.analise.notificacoes().find((item) => item.id === notificacaoId) ?? null;
  }

  protected rotuloAndamento(): string {
    const total = this.analise.emAndamento().length;
    return total === 1 ? 'Analisando 1 currículo...' : `Analisando ${total} currículos...`;
  }

  protected verResultado(notificacaoId: string): void {
    this.removerToast(notificacaoId);
    this.analise.abrirResultado(notificacaoId);
  }

  private removerToast(notificacaoId: string): void {
    this.idsToastsVisiveis.update((atual) => atual.filter((item) => item !== notificacaoId));
  }
}
