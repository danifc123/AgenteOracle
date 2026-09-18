import { Component, effect, inject } from '@angular/core';
import { AnaliseCurriculo, ErroAnalise, NotificacaoAnalise } from '../../servicos/analise-curriculo/analise-curriculo';
import { GerenciadorToasts } from '../../servicos/gerenciador-toasts/gerenciador-toasts';

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

  private readonly toasts = new GerenciadorToasts();
  protected readonly idsToastsVisiveis = this.toasts.idsVisiveis;

  constructor() {
    effect(() => {
      this.toasts.processar(this.analise.notificacoes());
      this.toasts.processar(this.analise.erros());
    });
  }

  protected descartar(notificacaoId: string): void {
    this.analise.marcarComoVista(notificacaoId);
    this.toasts.remover(notificacaoId);
  }

  protected descartarErro(erroId: string): void {
    this.analise.marcarErroComoVisto(erroId);
    this.toasts.remover(erroId);
  }

  protected descricaoToast(notificacao: NotificacaoAnalise): string {
    switch (notificacao.situacao) {
      case 'atualizado':
        return `${notificacao.candidatoNome}: candidato atualizado.`;
      case 'sem_alteracao':
        return `${notificacao.candidatoNome}: candidato já está atualizado.`;
      default:
        return `${notificacao.candidatoNome} entrou no pool de candidatos.`;
    }
  }

  protected erroPorId(erroId: string): ErroAnalise | null {
    return this.analise.erros().find((item) => item.id === erroId) ?? null;
  }

  protected notificacaoPorId(notificacaoId: string): NotificacaoAnalise | null {
    return this.analise.notificacoes().find((item) => item.id === notificacaoId) ?? null;
  }

  protected rotuloAndamento(): string {
    const total = this.analise.emAndamento().length;
    return total === 1 ? 'Analisando 1 currículo...' : `Analisando ${total} currículos...`;
  }

  protected verResultado(notificacaoId: string): void {
    this.toasts.remover(notificacaoId);
    this.analise.abrirResultado(notificacaoId);
  }
}
