import { Component, inject, input, output } from '@angular/core';
import { RotinaFinanceira } from '../../dadosRelatorios/modulos-financeiro';
import { CoresCategoria } from '../../servicos/cores-categoria';

@Component({
  selector: 'app-rotina-item',
  imports: [],
  templateUrl: './rotina-item.html',
  styleUrl: './rotina-item.scss',
})
export class RotinaItem {
  private readonly coresCategoria = inject(CoresCategoria);

  rotina = input.required<RotinaFinanceira>();
  selecionada = input(false);

  selecionar = output<void>();

  protected corCategoria(): string {
    return this.coresCategoria.obterCor(this.rotina().categoria);
  }
}
