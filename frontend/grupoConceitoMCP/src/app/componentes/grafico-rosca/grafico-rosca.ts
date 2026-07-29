import { Component, computed, input } from '@angular/core';

export interface FatiaRosca {
  nome: string;
  valor: number;
  cor: string;
}

interface SegmentoDesenhado {
  nome: string;
  cor: string;
  valor: number;
  percentual: number;
  dasharray: string;
  dashoffset: number;
  rotuloX: number;
  rotuloY: number;
}

const TAMANHO = 200;
const CENTRO = TAMANHO / 2;
const RAIO = 68;
const ESPESSURA = 26;
const CIRCUNFERENCIA = 2 * Math.PI * RAIO;
/** Pequeno vão entre fatias vizinhas (2-3px na cor de fundo) — não deixa os
 * segmentos se fundirem visualmente numa fatia só quando as cores são próximas. */
const VAO_ENTRE_FATIAS = 3;

function formatarMoeda(valor: number): string {
  return valor.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
}

@Component({
  selector: 'app-grafico-rosca',
  imports: [],
  templateUrl: './grafico-rosca.html',
  styleUrl: './grafico-rosca.scss'
})
export class GraficoRosca {
  titulo = input<string>('');
  fatias = input.required<FatiaRosca[]>();

  protected readonly TAMANHO = TAMANHO;
  protected readonly CENTRO = CENTRO;
  protected readonly RAIO = RAIO;
  protected readonly ESPESSURA = ESPESSURA;

  protected readonly valorTotal = computed(() => this.fatias().reduce((soma, fatia) => soma + fatia.valor, 0));

  /** Cada fatia vira um círculo com stroke-dasharray/-dashoffset — técnica
   * clássica de "donut em SVG" sem precisar calcular arco/path manualmente.
   * O grupo que envolve os círculos gira -90° (ver .html) pra fatia começar
   * às 12h em vez de 3h; os rótulos de percentual, por serem <text> soltos
   * fora desse grupo, calculam o próprio ângulo já "a partir do topo". */
  protected readonly segmentos = computed<SegmentoDesenhado[]>(() => {
    const total = this.valorTotal();
    if (!total) {
      return [];
    }

    const temVaos = this.fatias().length > 1;
    let acumulado = 0;
    return this.fatias().map((fatia) => {
      const fracao = fatia.valor / total;
      const comprimentoArco = Math.max(fracao * CIRCUNFERENCIA - (temVaos ? VAO_ENTRE_FATIAS : 0), 0);
      const anguloMedio = (acumulado + fracao / 2) * 2 * Math.PI;
      const dashoffset = -acumulado * CIRCUNFERENCIA;
      acumulado += fracao;

      return {
        nome: fatia.nome,
        cor: fatia.cor,
        valor: fatia.valor,
        percentual: fracao * 100,
        dasharray: `${comprimentoArco} ${CIRCUNFERENCIA - comprimentoArco}`,
        dashoffset,
        rotuloX: CENTRO + RAIO * Math.sin(anguloMedio),
        rotuloY: CENTRO - RAIO * Math.cos(anguloMedio)
      };
    });
  });

  protected formatarMoeda(valor: number): string {
    return formatarMoeda(valor);
  }

  protected formatarPercentual(valor: number): string {
    return `${valor.toFixed(valor < 10 ? 1 : 0)}%`;
  }
}
