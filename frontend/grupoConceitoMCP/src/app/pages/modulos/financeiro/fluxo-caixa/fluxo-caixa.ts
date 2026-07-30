import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { Botao } from '../../../../componentes/botao/botao';
import { CartaoKpi } from '../../../../componentes/cartao-kpi/cartao-kpi';
import { FatiaRosca, GraficoRosca } from '../../../../componentes/grafico-rosca/grafico-rosca';
import { GraficoSerie, SerieGrafico } from '../../../../componentes/grafico-serie/grafico-serie';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { OpcaoSelectBusca, SelectBusca } from '../../../../componentes/select-busca/select-busca';

interface Filial {
  codigo: string;
  nome: string;
}

interface ItemFluxoMes {
  mes: string;
  a_receber: number;
  a_pagar: number;
}

interface FatiaApi {
  nome: string;
  valor: number;
}

interface RespostaFluxoCaixa {
  meses: ItemFluxoMes[];
  total_a_receber: number;
  total_a_pagar: number;
  fatias_a_receber: FatiaApi[];
  fatias_a_pagar: FatiaApi[];
  analise: string;
}

// Cores da marca (mesmo verde/laranja da logo do Grupo Conceito) — verde
// como cor primária/principal, laranja como secundária. A API só devolve
// {nome, valor} pra cada fatia — a cor é atribuída aqui pela ordem (1ª fatia
// = "No período" = primária, 2ª = "Fora do período" = secundária).
const COR_PRIMARIA = '#2f9e58';
const COR_SECUNDARIA = '#e8871e';
const CORES_FATIAS = [COR_PRIMARIA, COR_SECUNDARIA];

@Component({
  selector: 'app-fluxo-caixa',
  imports: [ModuloHeader, SelectBusca, Botao, GraficoSerie, GraficoRosca, CartaoKpi],
  templateUrl: './fluxo-caixa.html',
  styleUrl: './fluxo-caixa.scss'
})
export class FluxoCaixa {
  private readonly http = inject(HttpClient);

  protected readonly filiais = signal<OpcaoSelectBusca[]>([]);
  protected readonly filiaisSelecionadas = signal<string[]>([]);

  protected readonly jaGerou = signal(false);
  protected readonly carregando = signal(false);
  protected readonly erro = signal<string | null>(null);
  protected readonly fluxoMeses = signal<ItemFluxoMes[]>([]);
  protected readonly fluxoAnalise = signal<string | null>(null);
  protected readonly fatiasAReceber = signal<FatiaRosca[]>([]);
  protected readonly fatiasAPagar = signal<FatiaRosca[]>([]);

  protected readonly podeGerar = computed(() => this.filiaisSelecionadas().length > 0 && !this.carregando());

  protected readonly totalAReceber = computed(() =>
    this.fatiasAReceber().reduce((soma, fatia) => soma + fatia.valor, 0)
  );
  protected readonly totalAPagar = computed(() => this.fatiasAPagar().reduce((soma, fatia) => soma + fatia.valor, 0));
  protected readonly vencidoAReceber = computed(() => this.fluxoMeses().find((item) => item.mes === 'vencido')?.a_receber ?? 0);
  protected readonly vencidoAPagar = computed(() => this.fluxoMeses().find((item) => item.mes === 'vencido')?.a_pagar ?? 0);
  protected readonly saldoProjetado = computed(() => this.totalAReceber() - this.totalAPagar());

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

  constructor() {
    this.carregarFiliais();
  }

  private carregarFiliais(): void {
    this.http.get<Filial[]>(`${MCP_API_BASE_URL}/api/financeiro/filiais`).subscribe({
      next: (filiais) => {
        this.filiais.set(filiais.map((filial) => ({ valor: filial.codigo, rotulo: filial.nome })));
      },
      error: () => {
        this.filiais.set([]);
      }
    });
  }

  private colorirFatias(fatias: FatiaApi[]): FatiaRosca[] {
    return fatias.map((fatia, indice) => ({ ...fatia, cor: CORES_FATIAS[indice] ?? COR_PRIMARIA }));
  }

  protected gerarPrevisao(): void {
    if (!this.podeGerar()) {
      return;
    }

    this.carregando.set(true);
    this.erro.set(null);

    this.http
      .get<RespostaFluxoCaixa>(`${MCP_API_BASE_URL}/api/financeiro/previsao/fluxo-caixa`, {
        params: { filial: this.filiaisSelecionadas().join(',') }
      })
      .subscribe({
        next: (resposta) => {
          this.jaGerou.set(true);
          this.fluxoMeses.set(resposta.meses);
          this.fluxoAnalise.set(resposta.analise);
          this.fatiasAReceber.set(this.colorirFatias(resposta.fatias_a_receber));
          this.fatiasAPagar.set(this.colorirFatias(resposta.fatias_a_pagar));
          this.carregando.set(false);
        },
        error: (erro: HttpErrorResponse) => {
          this.erro.set(
            erro.error?.erro ?? 'Não foi possível gerar a previsão. Verifique se o servidor está em execução.'
          );
          this.carregando.set(false);
        }
      });
  }
}
