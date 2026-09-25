import { Directive, TemplateRef, ViewContainerRef, effect, inject } from '@angular/core';
import { Sessao } from '../../servicos/sessao/sessao';

/** Estrutural — só renderiza o conteúdo pra quem tem algum papel
 * administrador (`sessao.administrador()`, verdadeiro pra qualquer papel
 * `*_admin` ou `desenvolvedor` — ver `tools/auth/papeis.py::eh_administrador`
 * no backend, mesma regra). Mesmo espírito de `SoDev` (`so-dev.ts`): ponto
 * único pra essa checagem, em vez de `sessao.administrador()` espalhado. */
@Directive({ selector: '[appSoAdmin]' })
export class SoAdmin {
  private readonly sessao = inject(Sessao);
  private readonly templateRef = inject(TemplateRef<unknown>);
  private readonly viewContainerRef = inject(ViewContainerRef);

  constructor() {
    effect(() => {
      this.viewContainerRef.clear();
      if (this.sessao.administrador()) {
        this.viewContainerRef.createEmbeddedView(this.templateRef);
      }
    });
  }
}
