import { Component, computed, input } from '@angular/core';
import { abreviarValor } from '../../utilitarios/formatacao-moeda';

@Component({
  selector: 'app-cartao-kpi',
  imports: [],
  templateUrl: './cartao-kpi.html',
  styleUrl: './cartao-kpi.scss',
})
export class CartaoKpi {
  rotulo = input.required<string>();
  valor = input.required<number>();
  /** 'moeda' abrevia em Mil/Milhões/Bilhões com prefixo R$; 'percentual' só
   * formata com 1 casa decimal e sufixo %, sem abreviar (ex: variação de
   * vendas); 'numero' é uma contagem simples (ex: unidades em estoque) —
   * sem prefixo R$ e sem abreviar, só separador de milhar. */
  tipo = input<'moeda' | 'percentual' | 'numero'>('moeda');
  /** Deixa o número em vermelho quando negativo (ex: saldo projetado) —
   * desliga pra KPIs onde negativo não é necessariamente "ruim". */
  destacarNegativo = input(true);
  /** Sobrescreve o prefixo padrão de `tipo="moeda"` (sempre "R$") — pra KPI
   * em outra moeda, ex: `prefixoPersonalizado="US$"`. */
  prefixoPersonalizado = input<string | null>(null);

  protected readonly prefixo = computed(
    () => this.prefixoPersonalizado() ?? (this.tipo() === 'moeda' ? 'R$' : ''),
  );

  protected readonly abreviado = computed(() => {
    if (this.tipo() === 'percentual') {
      const numero = this.valor().toLocaleString('pt-BR', {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      });
      return { numero: `${numero}%`, unidade: null };
    }
    if (this.tipo() === 'numero') {
      return { numero: this.valor().toLocaleString('pt-BR'), unidade: null };
    }
    return abreviarValor(this.valor());
  });

  protected readonly emVermelho = computed(() => this.destacarNegativo() && this.valor() < 0);
}
