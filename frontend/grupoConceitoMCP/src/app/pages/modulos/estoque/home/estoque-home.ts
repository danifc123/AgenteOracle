import { Component } from '@angular/core';
import { CartaoKpi } from '../../../../componentes/cartao-kpi/cartao-kpi';
import { FatiaRosca, GraficoRosca } from '../../../../componentes/grafico-rosca/grafico-rosca';
import { GraficoSerie, SerieGrafico } from '../../../../componentes/grafico-serie/grafico-serie';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';

const COR_VALOR = '#2f9e58';
const COR_MEDIA = '#e8871e';

/** Valor de fechamento mensal mockado (últimos 12 meses, mais recente por
 * último) — troca pra dado real assim que existir a consulta de estoque. */
const VALORES_FECHAMENTO_MENSAL = [
  10800000, 19300000, 15900000, 14600000, 13200000, 20600000, 18700000, 20900000, 15600000,
  11400000, 10900000, 9800000,
];

function gerarRotulosMensais(quantidade: number): string[] {
  const agora = new Date();
  return Array.from({ length: quantidade }, (_, indice) => {
    const data = new Date(agora.getFullYear(), agora.getMonth() - (quantidade - 1 - indice), 1);
    return `${data.getFullYear()}-${String(data.getMonth() + 1).padStart(2, '0')}`;
  });
}

function construirSeriesEvolucaoEstoque(): SerieGrafico[] {
  const rotulos = gerarRotulosMensais(VALORES_FECHAMENTO_MENSAL.length);
  const media =
    VALORES_FECHAMENTO_MENSAL.reduce((soma, valor) => soma + valor, 0) /
    VALORES_FECHAMENTO_MENSAL.length;

  return [
    {
      nome: 'Valor',
      cor: COR_VALOR,
      pontos: rotulos.map((rotulo, indice) => ({
        rotulo,
        valor: VALORES_FECHAMENTO_MENSAL[indice],
      })),
    },
    {
      nome: 'Média',
      cor: COR_MEDIA,
      linhaSobreposta: true,
      pontos: rotulos.map((rotulo) => ({ rotulo, valor: media })),
    },
  ];
}

/** Home do time de Estoque — mostrada em `/` pra quem só tem o módulo
 * Estoque, e pra desenvolvedor quando troca pro Estoque no seletor do
 * layout. Dado 100% mockado por enquanto: ainda não existe view de estoque
 * no Oracle (mesmo estágio inicial de `pages/modulos/estoque/estoque.ts`) —
 * troca pra dado real assim que a consulta existir. A grade
 * (`.grade-graficos`) já é responsiva a mais cartões, pra próximos gráficos
 * entrarem sem precisar mexer no layout. */
@Component({
  selector: 'app-estoque-home',
  imports: [CartaoKpi, GraficoRosca, GraficoSerie, ModuloHeader],
  templateUrl: './estoque-home.html',
  styleUrl: './estoque-home.scss',
})
export class EstoqueHome {
  protected readonly quantidadeProdutos = 215302;
  protected readonly valorTotalEstoque = 11026774.69;
  protected readonly valorEmDolar = 3041487.73;

  protected readonly seriesEvolucaoEstoque: SerieGrafico[] = construirSeriesEvolucaoEstoque();

  /** Bucket por dias até o vencimento — quanto mais perto (30 dias), mais
   * urgente: gradiente vermelho -> laranja -> verde -> cinza, mesmas cores
   * já usadas nos badges de status de `estoque.scss`. */
  protected readonly fatiasLotes: FatiaRosca[] = [
    { nome: '30 dias', valor: 8, cor: '#9a2f2f' },
    { nome: '60 dias', valor: 15, cor: '#e8871e' },
    { nome: '90 dias', valor: 22, cor: '#2f9e58' },
    { nome: '120 dias', valor: 30, cor: '#b8c7bd' },
  ];
}
