import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { Botao } from '../../../../componentes/botao/botao';
import { CartaoKpi } from '../../../../componentes/cartao-kpi/cartao-kpi';
import { EstadoVazio } from '../../../../componentes/estado-vazio/estado-vazio';
import { GraficoSerie, SerieGrafico } from '../../../../componentes/grafico-serie/grafico-serie';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { OpcaoSelectBusca, SelectBusca } from '../../../../componentes/select-busca/select-busca';
import { mensagemErro } from '../../../../servicos/mensagens-erro';

interface Filial {
  codigo: string;
  nome: string;
}

interface ItemHistorico {
  mes: string;
  valor: number;
}

interface ItemBanda {
  mes: string;
  p10: number;
  mediana: number;
  p90: number;
  minimo: number;
  maximo: number;
}

interface RespostaSimulacao {
  historico: ItemHistorico[];
  bandas: ItemBanda[];
  probabilidade_caixa_negativo: number;
}

const COR_PRIMARIA = '#2f9e58';
const COR_SECUNDARIA = '#e8871e';
const MESES_EXIBICAO_HISTORICO = 12;

/** MÓDULO FINANCEIRO — TELA "SIMULAÇÃO DE CENÁRIOS MONTE CARLO" (2026-08)
 *
 * Item "Simulação de Cenários Monte Carlo" da planilha de demandas de IA
 * do FP&A. Sem IA de propósito (mesmo espírito de `previsao.py`/Fluxo de
 * Caixa): em vez de uma linha de tendência única, o backend
 * (`agent/financeiro/simulacao_monte_carlo.py`) reamostra (bootstrap) a
 * variação histórica real do caixa líquido pra gerar uma distribuição de
 * cenários — aqui só plotamos as bandas P10/mediana/P90 já calculadas. */
@Component({
  selector: 'app-simulacao-monte-carlo',
  imports: [Botao, CartaoKpi, EstadoVazio, GraficoSerie, ModuloHeader, SelectBusca],
  templateUrl: './simulacao-monte-carlo.html',
  styleUrl: './simulacao-monte-carlo.scss',
})
export class SimulacaoMonteCarlo {
  private readonly http = inject(HttpClient);

  protected readonly filiais = signal<OpcaoSelectBusca[]>([]);
  protected readonly filiaisSelecionadas = signal<string[]>([]);
  protected readonly simulando = signal(false);
  protected readonly jaSimulou = signal(false);
  protected readonly erro = signal<string | null>(null);

  protected readonly historico = signal<ItemHistorico[]>([]);
  protected readonly bandas = signal<ItemBanda[]>([]);
  protected readonly probabilidadeCaixaNegativo = signal(0);

  protected readonly probabilidadeCaixaNegativoPercentual = computed(
    () => this.probabilidadeCaixaNegativo() * 100,
  );

  protected readonly ultimaBanda = computed<ItemBanda | null>(() => {
    const bandas = this.bandas();
    return bandas.length ? bandas[bandas.length - 1] : null;
  });

  protected readonly seriesSimulacao = computed<SerieGrafico[]>(() => {
    const historico = this.historico();
    const bandas = this.bandas();
    if (!historico.length) {
      return [];
    }

    const historicoExibido = historico.slice(-MESES_EXIBICAO_HISTORICO);
    const ultimoHistorico = historico[historico.length - 1];
    // O primeiro ponto de cada banda repete o último mês do histórico, só
    // pra a linha projetada "sair" visualmente de onde o histórico parou,
    // em vez de aparecer flutuando solta no gráfico com um buraco no meio.
    const pontoDePartida = { rotulo: ultimoHistorico.mes, valor: ultimoHistorico.valor };

    return [
      {
        nome: 'Histórico',
        cor: COR_PRIMARIA,
        pontos: historicoExibido.map((item) => ({ rotulo: item.mes, valor: item.valor })),
      },
      {
        nome: 'Mediana projetada',
        cor: COR_SECUNDARIA,
        pontos: [pontoDePartida, ...bandas.map((banda) => ({ rotulo: banda.mes, valor: banda.mediana }))],
      },
      {
        nome: 'Otimista (P90)',
        cor: COR_SECUNDARIA,
        tracejada: true,
        pontos: [pontoDePartida, ...bandas.map((banda) => ({ rotulo: banda.mes, valor: banda.p90 }))],
      },
      {
        nome: 'Pessimista (P10)',
        cor: COR_SECUNDARIA,
        tracejada: true,
        pontos: [pontoDePartida, ...bandas.map((banda) => ({ rotulo: banda.mes, valor: banda.p10 }))],
      },
    ];
  });

  constructor() {
    this.carregarFiliais();
  }

  protected simular(): void {
    if (!this.filiaisSelecionadas().length || this.simulando()) {
      return;
    }

    this.simulando.set(true);
    this.erro.set(null);

    this.http
      .get<RespostaSimulacao>(`${MCP_API_BASE_URL}/api/financeiro/fpa/simulacao-monte-carlo`, {
        params: { filial: this.filiaisSelecionadas().join(',') },
      })
      .subscribe({
        next: (resposta) => {
          this.historico.set(resposta.historico);
          this.bandas.set(resposta.bandas);
          this.probabilidadeCaixaNegativo.set(resposta.probabilidade_caixa_negativo);
          this.jaSimulou.set(true);
          this.simulando.set(false);
        },
        error: (erro: HttpErrorResponse) => {
          this.erro.set(mensagemErro(erro, 'Não foi possível simular os cenários.'));
          this.simulando.set(false);
        },
      });
  }

  private carregarFiliais(): void {
    this.http.get<Filial[]>(`${MCP_API_BASE_URL}/api/financeiro/filiais`).subscribe({
      next: (filiais) => {
        this.filiais.set(filiais.map((filial) => ({ valor: filial.codigo, rotulo: filial.nome })));
      },
      error: () => this.filiais.set([]),
    });
  }
}
