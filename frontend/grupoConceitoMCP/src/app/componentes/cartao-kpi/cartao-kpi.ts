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
  /** 'moeda' abrevia em Mil/Milhões/Bilhões com prefixo R$; 'percentual' só
   * formata com 1 casa decimal e sufixo %, sem abreviar (ex: variação de vendas). */
  tipo = input<'moeda' | 'percentual'>('moeda');
  /** Deixa o número em vermelho quando negativo (ex: saldo projetado) —
   * desliga pra KPIs onde negativo não é necessariamente "ruim". */
  destacarNegativo = input(true);

  protected readonly prefixo = computed(() => (this.tipo() === 'percentual' ? '' : 'R$'));

  protected readonly abreviado = computed(() => {
    if (this.tipo() === 'percentual') {
      const numero = this.valor().toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
      return { numero: `${numero}%`, unidade: null };
    }
    return abreviarValor(this.valor());
  });

  protected readonly emVermelho = computed(() => this.destacarNegativo() && this.valor() < 0);
}
