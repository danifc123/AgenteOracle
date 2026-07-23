import { Component, input, output } from '@angular/core';
import { RotinaFinanceira, corCategoria } from '../../dadosRelatorios/modulos-financeiro';

@Component({
  selector: 'app-rotina-item',
  imports: [],
  templateUrl: './rotina-item.html',
  styleUrl: './rotina-item.scss'
})
export class RotinaItem {
  rotina = input.required<RotinaFinanceira>();
  selecionada = input(false);

  selecionar = output<void>();

  protected corCategoria(): string {
    return corCategoria(this.rotina().categoria);
  }
}
