import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { Botao } from '../../../../componentes/botao/botao';
import { CartaoKpi } from '../../../../componentes/cartao-kpi/cartao-kpi';
import { GraficoSerie, SerieGrafico } from '../../../../componentes/grafico-serie/grafico-serie';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { OpcaoSelectBusca, SelectBusca } from '../../../../componentes/select-busca/select-busca';

interface Filial {
  codigo: string;
  nome: string;
}

interface ItemMes {
  mes: string;
  valor: number;
}

interface RespostaVendas {
  historico: ItemMes[];
  projecao: ItemMes[];
  analise: string;
}

// Verde da marca — mesma cor primária usada no Fluxo de Caixa.
const COR_VENDAS = '#2f9e58';

@Component({
  selector: 'app-vendas',
  imports: [ModuloHeader, SelectBusca, Botao, GraficoSerie, CartaoKpi],
  templateUrl: './vendas.html',
  styleUrl: './vendas.scss'
})
export class Vendas {
  private readonly http = inject(HttpClient);

  protected readonly filiais = signal<OpcaoSelectBusca[]>([]);
  protected readonly filiaisSelecionadas = signal<string[]>([]);

  protected readonly jaGerou = signal(false);
  protected readonly carregando = signal(false);
  protected readonly erro = signal<string | null>(null);
  protected readonly vendasHistorico = signal<ItemMes[]>([]);
  protected readonly vendasProjecao = signal<ItemMes[]>([]);
  protected readonly vendasAnalise = signal<string | null>(null);

  protected readonly podeGerar = computed(() => this.filiaisSelecionadas().length > 0 && !this.carregando());

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

  protected gerarPrevisao(): void {
    if (!this.podeGerar()) {
      return;
    }

    this.carregando.set(true);
    this.erro.set(null);

    this.http
      .get<RespostaVendas>(`${MCP_API_BASE_URL}/api/financeiro/previsao/vendas`, {
        params: { filial: this.filiaisSelecionadas().join(',') }
      })
      .subscribe({
        next: (resposta) => {
          this.jaGerou.set(true);
          this.vendasHistorico.set(resposta.historico);
          this.vendasProjecao.set(resposta.projecao);
          this.vendasAnalise.set(resposta.analise);
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
