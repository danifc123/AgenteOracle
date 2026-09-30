import { Component, inject } from '@angular/core';
import { CartaoKpi } from '../../../../../../componentes/cartao-kpi/cartao-kpi';
import { UsoIa } from '../../../../../../servicos/uso-ia/uso-ia';

@Component({
  selector: 'app-widget-ia-categoria-nao-corrigida',
  imports: [CartaoKpi],
  templateUrl: './widget-ia-categoria-nao-corrigida.html',
})
export class WidgetIaCategoriaNaoCorrigida {
  protected readonly usoIa = inject(UsoIa);
}
