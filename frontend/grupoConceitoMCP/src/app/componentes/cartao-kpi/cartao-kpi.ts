import { Component, computed, input } from '@angular/core';
import { abreviarValor } from '../../utilitarios/formatacao-moeda';

@Component({
  selector: 'app-cartao-kpi',
  imports: [],
  templateUrl: './cartao-kpi.html',
  styleUrl: './cartao-kpi.scss'
})
export class CartaoKpi {
  rotulo = input.required<string>();
  valor = input.required<number>();
  /** Deixa o número em vermelho quando negativo (ex: saldo projetado) —
   * desliga pra KPIs onde negativo não é necessariamente "ruim". */
  destacarNegativo = input(true);

  protected readonly abreviado = computed(() => abreviarValor(this.valor()));

  protected readonly emVermelho = computed(() => this.destacarNegativo() && this.valor() < 0);
}
