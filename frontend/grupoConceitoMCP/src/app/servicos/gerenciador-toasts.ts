import { signal } from '@angular/core';

/** Tempo que um toast fica visível antes de sumir sozinho — o item de
 * origem (notificação/erro) continua existindo no serviço até o usuário
 * interagir, só o cartão flutuante que some. */
const DURACAO_TOAST_MS = 8000;

interface ItemNotificavel {
  id: string;
  vista: boolean;
}

/** Ciclo de vida de toast compartilhado por `NotificacaoAnaliseCurriculo`
 * e `NotificacaoChatFinanceiro` — não é injetável: cada componente
 * instancia a sua com `new`, porque o `effect()` de `processar` precisa
 * rodar dentro do construtor do componente que o chama. */
export class GerenciadorToasts {
  private readonly idsJaMostrados = new Set<string>();
  readonly idsVisiveis = signal<string[]>([]);

  processar(itens: ItemNotificavel[]): void {
    for (const item of itens) {
      if (item.vista || this.idsJaMostrados.has(item.id)) {
        continue;
      }
      this.idsJaMostrados.add(item.id);
      this.idsVisiveis.update((atual) => [...atual, item.id]);
      setTimeout(() => this.remover(item.id), DURACAO_TOAST_MS);
    }
  }

  remover(id: string): void {
    this.idsVisiveis.update((atual) => atual.filter((existente) => existente !== id));
  }
}
