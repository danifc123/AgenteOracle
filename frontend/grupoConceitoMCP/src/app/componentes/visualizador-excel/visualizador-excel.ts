import { Component, computed, input } from '@angular/core';

@Component({
  selector: 'app-visualizador-excel',
  imports: [],
  templateUrl: './visualizador-excel.html',
  styleUrl: './visualizador-excel.scss'
})
export class VisualizadorExcel {
  dados = input.required<Record<string, unknown>[]>();

  protected readonly colunas = computed(() => {
    const linhas = this.dados();
    return linhas.length ? Object.keys(linhas[0]) : [];
  });

  protected ehNumero(valor: unknown): boolean {
    return typeof valor === 'number';
  }
}
