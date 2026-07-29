import { Component, computed, signal } from '@angular/core';
import { Botao } from '../../../../componentes/botao/botao';
import { FatiaRosca, GraficoRosca } from '../../../../componentes/grafico-rosca/grafico-rosca';
import { GraficoSerie, SerieGrafico } from '../../../../componentes/grafico-serie/grafico-serie';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { OpcaoSelectBusca, SelectBusca } from '../../../../componentes/select-busca/select-busca';

interface ItemFluxoMes {
  mes: string;
  a_receber: number;
  a_pagar: number;
}

// Cores da marca (mesmo verde/laranja da logo do Grupo Conceito) — verde
// como cor primária/principal, laranja como secundária.
const COR_PRIMARIA = '#2f9e58';
const COR_SECUNDARIA = '#e8871e';

// Dados de mentira só pra construir/ajustar os componentes visuais — troca
// pra dados reais da API assim que o layout estiver aprovado.
const MOCK_FILIAIS: OpcaoSelectBusca[] = [
  { valor: '0101', rotulo: '0101 - Matriz' },
  { valor: '0102', rotulo: '0102 - Filial Sul' }
];

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
  selector: 'app-fluxo-caixa',
  imports: [ModuloHeader, SelectBusca, Botao, GraficoSerie, GraficoRosca],
  templateUrl: './fluxo-caixa.html',
  styleUrl: './fluxo-caixa.scss'
})
export class FluxoCaixa {
  protected readonly filiais = signal<OpcaoSelectBusca[]>(MOCK_FILIAIS);
  protected readonly filiaisSelecionadas = signal<string[]>([]);

  protected readonly jaGerou = signal(false);
  protected readonly fluxoMeses = signal<ItemFluxoMes[]>([]);
  protected readonly fluxoAnalise = signal<string | null>(null);
  protected readonly fatiasAReceber = signal<FatiaRosca[]>([]);
  protected readonly fatiasAPagar = signal<FatiaRosca[]>([]);

  protected readonly podeGerar = computed(() => this.filiaisSelecionadas().length > 0);

  protected readonly seriesFluxoCaixa = computed<SerieGrafico[]>(() => {
    const meses = this.fluxoMeses();
    if (!meses.length) {
      return [];
    }

    return [
      { nome: 'A Receber', cor: COR_PRIMARIA, pontos: meses.map((item) => ({ rotulo: item.mes, valor: item.a_receber })) },
      { nome: 'A Pagar', cor: COR_SECUNDARIA, pontos: meses.map((item) => ({ rotulo: item.mes, valor: item.a_pagar })) }
    ];
  });

  protected gerarPrevisao(): void {
    if (!this.podeGerar()) {
      return;
    }

    this.jaGerou.set(true);
    this.fluxoMeses.set(MOCK_FLUXO_MESES);
    this.fluxoAnalise.set(MOCK_FLUXO_ANALISE);
    this.fatiasAReceber.set(MOCK_FATIAS_A_RECEBER);
    this.fatiasAPagar.set(MOCK_FATIAS_A_PAGAR);
  }
}
