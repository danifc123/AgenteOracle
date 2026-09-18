import { Directive, TemplateRef, ViewContainerRef, effect, inject, input } from '@angular/core';
import { Sessao } from '../servicos/sessao';

/** Estrutural — só renderiza o conteúdo pra quem tem acesso ao módulo
 * informado (`sessao.modulos().includes(modulo)`). Mesmo espírito de
 * `SoDev`/`SoAdmin`: ponto único pra essa checagem.
 *
 * Uso: `<div *appSoModulo="'financeiro'">...</div>`. */
@Directive({ selector: '[appSoModulo]' })
export class SoModulo {
  private readonly sessao = inject(Sessao);
  private readonly templateRef = inject(TemplateRef<unknown>);
  private readonly viewContainerRef = inject(ViewContainerRef);

  readonly appSoModulo = input.required<string>();

  constructor() {
    effect(() => {
      this.viewContainerRef.clear();
      if (this.sessao.modulos().includes(this.appSoModulo())) {
        this.viewContainerRef.createEmbeddedView(this.templateRef);
      }
    });
  }
}
