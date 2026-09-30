import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { CartaoKpi } from '../../../../../../componentes/cartao-kpi/cartao-kpi';
import { ChamadoResumo, URL_CHAMADOS } from '../chamados-resumo';

/** Autossuficiente: busca os próprios dados (`GET /api/ti/chamados`, mesma
 * rota da tela de Auditoria de Chamados) — a grade de indicadores só
 * coloca `<app-widget-chamados-total/>`, sem passar nada. */
@Component({
  selector: 'app-widget-chamados-total',
  imports: [CartaoKpi],
  templateUrl: './widget-chamados-total.html',
})
export class WidgetChamadosTotal {
  private readonly http = inject(HttpClient);

  protected readonly chamados = signal<ChamadoResumo[]>([]);
  protected readonly total = computed(() => this.chamados().length);

  constructor() {
    this.http.get<ChamadoResumo[]>(URL_CHAMADOS).subscribe({
      next: (chamados) => this.chamados.set(chamados),
    });
  }
}
