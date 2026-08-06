import { Injectable, signal } from '@angular/core';

/** Qual "home" de módulo está sendo mostrada na rota `/` — só importa pra
 * desenvolvedor (único papel que pode ter mais de um módulo liberado hoje);
 * pra todo mundo, `HomeRoteador` decide sozinho pelo módulo liberado, sem
 * olhar isso. Existe como serviço próprio (não dentro de `Sessao`, que é
 * sobre identidade/autenticação, não preferência de tela) pra o seletor no
 * layout (`SeletorHomeDev`) e o roteador da home poderem compartilhar o
 * mesmo estado sem um ser filho do outro. */
@Injectable({ providedIn: 'root' })
export class HomeSelecionada {
  readonly modulo = signal('financeiro');

  selecionar(modulo: string): void {
    this.modulo.set(modulo);
  }
}
