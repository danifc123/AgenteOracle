import { Component, computed, signal } from '@angular/core';
import { Botao } from '../../../../componentes/botao/botao';
import { FatiaRosca, GraficoRosca } from '../../../../componentes/grafico-rosca/grafico-rosca';
import { GraficoSerie, SerieGrafico } from '../../../../componentes/grafico-serie/grafico-serie';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { OpcaoSelectBusca, SelectBusca } from '../../../../componentes/select-busca/select-busca';

interface ItemMes {
  mes: string;
  valor: number;
}

interface ItemFluxoMes {
  mes: string;
  a_receber: number;
  a_pagar: number;
}

// Cores da marca (mesmo verde/laranja da logo do Grupo Conceito) — verde
// como cor primária/principal de cada gráfico, laranja como secundária.
const COR_PRIMARIA = '#2f9e58';
const COR_SECUNDARIA = '#e8871e';

const COR_VENDAS = COR_PRIMARIA;
const COR_A_RECEBER = COR_PRIMARIA;
const COR_A_PAGAR = COR_SECUNDARIA;

// Dados de mentira só pra construir/ajustar os componentes visuais — troca
// pra dados reais da API assim que o layout estiver aprovado.
const MOCK_FILIAIS: OpcaoSelectBusca[] = [
  { valor: '0101', rotulo: '0101 - Matriz' },
  { valor: '0102', rotulo: '0102 - Filial Sul' }
];

const MOCK_VENDAS_HISTORICO: ItemMes[] = [
  { mes: '2025-08', valor: 62000 },
  { mes: '2025-09', valor: 145000 },
  { mes: '2025-10', valor: 118000 },
  { mes: '2025-11', valor: 58000 },
  { mes: '2025-12', valor: 172000 },
  { mes: '2026-01', valor: 129000 },
  { mes: '2026-02', valor: 6000 },
  { mes: '2026-03', valor: 193000 },
  { mes: '2026-04', valor: 84000 },
  { mes: '2026-05', valor: 97000 },
  { mes: '2026-06', valor: 22000 },
  { mes: '2026-07', valor: 26000 }
];

const MOCK_VENDAS_PROJECAO: ItemMes[] = [
  { mes: '2026-08', valor: 63000 },
  { mes: '2026-09', valor: 57000 },
  { mes: '2026-10', valor: 51000 }
];

const MOCK_VENDAS_ANALISE =
  'O faturamento aumentou significativamente nos últimos meses, com picos em setembro de 2025 e março de 2026. ' +
  'Os próximos três meses estão projetados para uma queda gradual.';

const MOCK_FLUXO_MESES: ItemFluxoMes[] = [
  { mes: 'vencido', a_receber: 448450.25, a_pagar: 27934.93 },
  { mes: '2026-07', a_receber: 0, a_pagar: 0 },
  { mes: '2026-08', a_receber: 0, a_pagar: 22000 },
  { mes: '2026-09', a_receber: 0, a_pagar: 18500 },
  { mes: '2026-10', a_receber: 0, a_pagar: 15200 },
  { mes: '2026-11', a_receber: 0, a_pagar: 19800 },
  { mes: '2026-12', a_receber: 0, a_pagar: 24100 }
];

const MOCK_FLUXO_ANALISE =
  "A tendência revela uma redução significativa no valor de contas a pagar e a receber no período após o " +
  "vencimento. Em comparação com os valores 'vencidos', não há nenhuma parcela a receber projetada nos próximos " +
  'meses — vale investigar se há títulos futuros que ainda não entraram no sistema.';

const MOCK_TOTAL_A_RECEBER = 81402812.78;
const MOCK_FATIAS_A_RECEBER: FatiaRosca[] = [
  { nome: 'No período', valor: MOCK_TOTAL_A_RECEBER * 0.4202, cor: COR_PRIMARIA },
  { nome: 'Fora do período', valor: MOCK_TOTAL_A_RECEBER * 0.5798, cor: COR_SECUNDARIA }
];

const MOCK_TOTAL_A_PAGAR = 353462555.21;
const MOCK_FATIAS_A_PAGAR: FatiaRosca[] = [
  { nome: 'No período', valor: MOCK_TOTAL_A_PAGAR * 0.3005, cor: COR_PRIMARIA },
  { nome: 'Fora do período', valor: MOCK_TOTAL_A_PAGAR * 0.6995, cor: COR_SECUNDARIA }
];

@Component({
  selector: 'app-previsoes',
  imports: [ModuloHeader, SelectBusca, Botao, GraficoSerie, GraficoRosca],
  templateUrl: './previsoes.html',
  styleUrl: './previsoes.scss'
})
export class Previsoes {
  protected readonly filiais = signal<OpcaoSelectBusca[]>(MOCK_FILIAIS);
  protected readonly filiaisSelecionadas = signal<string[]>([]);

  protected readonly jaGerou = signal(false);
  protected readonly vendasHistorico = signal<ItemMes[]>([]);
  protected readonly vendasProjecao = signal<ItemMes[]>([]);
  protected readonly vendasAnalise = signal<string | null>(null);
  protected readonly fluxoMeses = signal<ItemFluxoMes[]>([]);
  protected readonly fluxoAnalise = signal<string | null>(null);
  protected readonly fatiasAReceber = signal<FatiaRosca[]>([]);
  protected readonly fatiasAPagar = signal<FatiaRosca[]>([]);

  protected readonly podeGerar = computed(() => this.filiaisSelecionadas().length > 0);

  protected readonly seriesVendas = computed<SerieGrafico[]>(() => {
    const historico = this.vendasHistorico();
    if (!historico.length) {
      return [];
    }

    const serieHistorico: SerieGrafico = {
      nome: 'Faturamento realizado',
      cor: COR_VENDAS,
      pontos: historico.map((item) => ({ rotulo: item.mes, valor: item.valor }))
    };

    const projecao = this.vendasProjecao();
    if (!projecao.length) {
      return [serieHistorico];
    }

    const ultimoHistorico = historico[historico.length - 1];
    const serieProjecao: SerieGrafico = {
      nome: 'Projeção',
      cor: COR_VENDAS,
      tracejada: true,
      // Começa repetindo o último ponto real, pra linha tracejada continuar
      // visualmente a partir de onde o histórico parou, em vez de boiar solta.
      pontos: [
        { rotulo: ultimoHistorico.mes, valor: ultimoHistorico.valor },
        ...projecao.map((item) => ({ rotulo: item.mes, valor: item.valor }))
      ]
    };

    return [serieHistorico, serieProjecao];
  });

  protected readonly seriesFluxoCaixa = computed<SerieGrafico[]>(() => {
    const meses = this.fluxoMeses();
    if (!meses.length) {
      return [];
    }

    return [
      { nome: 'A Receber', cor: COR_A_RECEBER, pontos: meses.map((item) => ({ rotulo: item.mes, valor: item.a_receber })) },
      { nome: 'A Pagar', cor: COR_A_PAGAR, pontos: meses.map((item) => ({ rotulo: item.mes, valor: item.a_pagar })) }
    ];
  });

  protected gerarPrevisao(): void {
    if (!this.podeGerar()) {
      return;
    }

    this.jaGerou.set(true);
    this.vendasHistorico.set(MOCK_VENDAS_HISTORICO);
    this.vendasProjecao.set(MOCK_VENDAS_PROJECAO);
    this.vendasAnalise.set(MOCK_VENDAS_ANALISE);
    this.fluxoMeses.set(MOCK_FLUXO_MESES);
    this.fluxoAnalise.set(MOCK_FLUXO_ANALISE);
    this.fatiasAReceber.set(MOCK_FATIAS_A_RECEBER);
    this.fatiasAPagar.set(MOCK_FATIAS_A_PAGAR);
  }
}
