import { Component, input, output } from '@angular/core';
import { ViewFinanceira } from '../../dadosRelatorios/views-financeiras';

@Component({
  selector: 'app-tabela-item',
  imports: [],
  templateUrl: './tabela-item.html',
  styleUrl: './tabela-item.scss',
})
export class TabelaItem {
  tabela = input.required<ViewFinanceira>();
  aberta = input(false);
  colunasSelecionadas = input<string[]>([]);
  /** Sem relacionamento (direto ou indireto) com as tabelas já selecionadas
   * no relatório — fica desabilitada pra não deixar o usuário montar uma
   * combinação que o backend vai recusar na hora de gerar. */
  bloqueada = input(false);

  alternarAberta = output<void>();
  alternarColuna = output<string>();

  protected estaSelecionada(chave: string): boolean {
    return this.colunasSelecionadas().includes(chave);
  }
}
