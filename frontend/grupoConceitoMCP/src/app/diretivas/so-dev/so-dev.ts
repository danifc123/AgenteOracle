import { Directive, TemplateRef, ViewContainerRef, effect, inject } from '@angular/core';
import { Sessao } from '../../servicos/sessao/sessao';

/** Estrutural — só renderiza o conteúdo pra quem tem o papel `desenvolvedor`
 * (`sessao.ehDesenvolvedor()`). Ponto único pra essa checagem: antes dela,
 * cada tela/componente que precisava disso chamava `sessao.ehDesenvolvedor()`
 * direto no `@if`, sem nenhuma garantia de que um lugar novo usaria a
 * checagem certa (achado real, auditando o app inteiro: 3 componentes
 * compartilhados e 2 páginas já faziam isso cada um do seu jeito).
 *
 * Uso: `<div *appSoDev>...</div>` ou `<ng-container *appSoDev>...</ng-container>`
 * quando só precisa esconder sem criar um elemento novo. */
@Directive({ selector: '[appSoDev]' })
export class SoDev {
  private readonly sessao = inject(Sessao);
  private readonly templateRef = inject(TemplateRef<unknown>);
  private readonly viewContainerRef = inject(ViewContainerRef);

  constructor() {
    effect(() => {
      this.viewContainerRef.clear();
      if (this.sessao.ehDesenvolvedor()) {
        this.viewContainerRef.createEmbeddedView(this.templateRef);
      }
    });
  }
}
