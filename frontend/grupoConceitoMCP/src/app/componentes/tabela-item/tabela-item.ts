import { Component, input, output } from '@angular/core';
import { ViewFinanceira } from '../../dadosRelatorios/views-financeiras';

@Component({
  selector: 'app-tabela-item',
  imports: [],
  templateUrl: './tabela-item.html',
  styleUrl: './tabela-item.scss'
})
export class TabelaItem {
  tabela = input.required<ViewFinanceira>();
  aberta = input(false);
  colunasSelecionadas = input<string[]>([]);

  alternarAberta = output<void>();
  alternarColuna = output<string>();

  protected estaSelecionada(chave: string): boolean {
    return this.colunasSelecionadas().includes(chave);
  }
}
