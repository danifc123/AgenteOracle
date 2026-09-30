import { Component, computed, inject } from '@angular/core';
import { CartaoKpi } from '../../../../../../componentes/cartao-kpi/cartao-kpi';
import { UsoIa } from '../../../../../../servicos/uso-ia/uso-ia';

/** Só lê os signals de `UsoIa` — nunca chama `.carregar()` nem monta o
 * polling sozinho, isso continua sendo responsabilidade da Home única (ver
 * `pages/home/home.ts`), senão cada widget de IA aberto ao mesmo tempo
 * dispararia seu próprio polling redundante. */
@Component({
  selector: 'app-widget-ia-tokens-hoje',
  imports: [CartaoKpi],
  templateUrl: './widget-ia-tokens-hoje.html',
})
export class WidgetIaTokensHoje {
  protected readonly usoIa = inject(UsoIa);

  protected readonly tokensHojeTotal = computed(() =>
    Object.values(this.usoIa.tokensHojePorDominio()).reduce((total, valor) => total + valor, 0),
  );
}
