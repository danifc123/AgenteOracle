import { Component, inject } from '@angular/core';
import { CartaoKpi } from '../../../../../../componentes/cartao-kpi/cartao-kpi';
import { UsoIa } from '../../../../../../servicos/uso-ia/uso-ia';

@Component({
  selector: 'app-widget-ia-chamados-avaliados',
  imports: [CartaoKpi],
  templateUrl: './widget-ia-chamados-avaliados.html',
})
export class WidgetIaChamadosAvaliados {
  protected readonly usoIa = inject(UsoIa);
}
