import { Component, computed, input, signal } from '@angular/core';

type DirecaoOrdenacao = 'asc' | 'desc';

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

  protected readonly colunaOrdenada = signal<string | null>(null);
  protected readonly direcaoOrdenacao = signal<DirecaoOrdenacao>('asc');

  protected readonly dadosOrdenados = computed(() => {
    const coluna = this.colunaOrdenada();
    const linhas = this.dados();
    if (!coluna) {
      return linhas;
    }

    const direcao = this.direcaoOrdenacao() === 'asc' ? 1 : -1;
    return [...linhas].sort((a, b) => this.compararValores(a[coluna], b[coluna]) * direcao);
  });

  private compararValores(valorA: unknown, valorB: unknown): number {
    const vazioA = valorA === null || valorA === undefined || valorA === '';
    const vazioB = valorB === null || valorB === undefined || valorB === '';
    if (vazioA && vazioB) return 0;
    if (vazioA) return 1;
    if (vazioB) return -1;

    if (typeof valorA === 'number' && typeof valorB === 'number') {
      return valorA - valorB;
    }

    return String(valorA).localeCompare(String(valorB), 'pt-BR', { numeric: true, sensitivity: 'base' });
  }

  protected ordenarPor(coluna: string): void {
    if (this.colunaOrdenada() === coluna) {
      this.direcaoOrdenacao.set(this.direcaoOrdenacao() === 'asc' ? 'desc' : 'asc');
    } else {
      this.colunaOrdenada.set(coluna);
      this.direcaoOrdenacao.set('asc');
    }
  }

  protected ehNumero(valor: unknown): boolean {
    return typeof valor === 'number';
  }
}
