import { Component, inject } from '@angular/core';
import { CartaoKpi } from '../../../../../../componentes/cartao-kpi/cartao-kpi';
import { UsoIa } from '../../../../../../servicos/uso-ia/uso-ia';

@Component({
  selector: 'app-widget-ia-chamados-escalados',
  imports: [CartaoKpi],
  templateUrl: './widget-ia-chamados-escalados.html',
})
export class WidgetIaChamadosEscalados {
  protected readonly usoIa = inject(UsoIa);
}
