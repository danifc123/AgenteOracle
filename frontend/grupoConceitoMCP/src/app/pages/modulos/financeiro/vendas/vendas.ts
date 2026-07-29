import { Component, computed, signal } from '@angular/core';
import { Botao } from '../../../../componentes/botao/botao';
import { CartaoKpi } from '../../../../componentes/cartao-kpi/cartao-kpi';
import { GraficoSerie, SerieGrafico } from '../../../../componentes/grafico-serie/grafico-serie';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { OpcaoSelectBusca, SelectBusca } from '../../../../componentes/select-busca/select-busca';

interface ItemMes {
  mes: string;
  valor: number;
}

// Verde da marca — mesma cor primária usada no Fluxo de Caixa.
const COR_VENDAS = '#2f9e58';

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

@Component({
  selector: 'app-vendas',
  imports: [ModuloHeader, SelectBusca, Botao, GraficoSerie, CartaoKpi],
  templateUrl: './vendas.html',
  styleUrl: './vendas.scss'
})
export class Vendas {
  protected readonly filiais = signal<OpcaoSelectBusca[]>(MOCK_FILIAIS);
  protected readonly filiaisSelecionadas = signal<string[]>([]);

  protected readonly jaGerou = signal(false);
  protected readonly vendasHistorico = signal<ItemMes[]>([]);
  protected readonly vendasProjecao = signal<ItemMes[]>([]);
  protected readonly vendasAnalise = signal<string | null>(null);

  protected readonly podeGerar = computed(() => this.filiaisSelecionadas().length > 0);

  protected readonly faturamentoTotal = computed(() =>
    this.vendasHistorico().reduce((soma, item) => soma + item.valor, 0)
  );
  protected readonly mediaMensal = computed(() => {
    const historico = this.vendasHistorico();
    return historico.length ? this.faturamentoTotal() / historico.length : 0;
  });
  protected readonly projecaoProximoMes = computed(() => this.vendasProjecao()[0]?.valor ?? 0);
  protected readonly projecaoTrimestre = computed(() =>
    this.vendasProjecao().reduce((soma, item) => soma + item.valor, 0)
  );
  protected readonly variacaoProjetada = computed(() => {
    const historico = this.vendasHistorico();
    const ultimo = historico[historico.length - 1]?.valor;
    const proximo = this.projecaoProximoMes();
    if (!ultimo) {
      return 0;
    }
    return ((proximo - ultimo) / ultimo) * 100;
  });

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

  protected gerarPrevisao(): void {
    if (!this.podeGerar()) {
      return;
    }

    this.jaGerou.set(true);
    this.vendasHistorico.set(MOCK_VENDAS_HISTORICO);
    this.vendasProjecao.set(MOCK_VENDAS_PROJECAO);
    this.vendasAnalise.set(MOCK_VENDAS_ANALISE);
  }
}
