import { Component, computed, input, signal } from '@angular/core';
import { IconeOrdenacao } from '../icone-ordenacao/icone-ordenacao';
import { compararValores, DirecaoOrdenacao, proximaDirecao } from '../../servicos/ordenacao-tabela';

@Component({
  selector: 'app-visualizador-excel',
  imports: [IconeOrdenacao],
  templateUrl: './visualizador-excel.html',
  styleUrl: './visualizador-excel.scss',
})
export class VisualizadorExcel {
  dados = input.required<Record<string, unknown>[]>();

  protected readonly colunas = computed(() => {
    const linhas = this.dados();
    return linhas.length ? Object.keys(linhas[0]) : [];
  });

  protected readonly colunaOrdenada = signal<string | null>(null);
  protected readonly direcaoOrdenacao = signal<DirecaoOrdenacao>(null);

  protected readonly dadosOrdenados = computed(() => {
    const coluna = this.colunaOrdenada();
    const direcao = this.direcaoOrdenacao();
    const linhas = this.dados();
    if (!coluna || !direcao) {
      return linhas;
    }

    const sinal = direcao === 'asc' ? 1 : -1;
    return [...linhas].sort((a, b) => compararValores(a[coluna], b[coluna]) * sinal);
  });

  protected direcaoDaColuna(coluna: string): DirecaoOrdenacao {
    return this.colunaOrdenada() === coluna ? this.direcaoOrdenacao() : null;
  }

  protected ehNumero(valor: unknown): boolean {
    return typeof valor === 'number';
  }

  protected ordenarPor(coluna: string): void {
    if (this.colunaOrdenada() === coluna) {
      this.direcaoOrdenacao.set(proximaDirecao(this.direcaoOrdenacao()));
    } else {
      this.colunaOrdenada.set(coluna);
      this.direcaoOrdenacao.set('asc');
    }
  }
}
