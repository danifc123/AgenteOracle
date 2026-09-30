import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { FatiaRosca, GraficoRosca } from '../../../../../../componentes/grafico-rosca/grafico-rosca';
import { ChamadoResumo, URL_CHAMADOS, contarPorStatus } from '../chamados-resumo';

@Component({
  selector: 'app-widget-chamados-por-status',
  imports: [GraficoRosca],
  templateUrl: './widget-chamados-por-status.html',
  styleUrl: './widget-chamados-por-status.scss',
})
export class WidgetChamadosPorStatus {
  private readonly http = inject(HttpClient);

  protected readonly chamados = signal<ChamadoResumo[]>([]);
  protected readonly fatias = computed<FatiaRosca[]>(() => contarPorStatus(this.chamados()));

  constructor() {
    this.http.get<ChamadoResumo[]>(URL_CHAMADOS).subscribe({
      next: (chamados) => this.chamados.set(chamados),
    });
  }
}
