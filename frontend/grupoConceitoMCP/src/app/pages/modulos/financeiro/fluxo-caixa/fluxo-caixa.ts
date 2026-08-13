import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { Botao } from '../../../../componentes/botao/botao';
import { CartaoKpi } from '../../../../componentes/cartao-kpi/cartao-kpi';
import { EstadoVazio } from '../../../../componentes/estado-vazio/estado-vazio';
import { FatiaRosca, GraficoRosca } from '../../../../componentes/grafico-rosca/grafico-rosca';
import { GraficoSerie, SerieGrafico } from '../../../../componentes/grafico-serie/grafico-serie';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { OpcaoSelectBusca, SelectBusca } from '../../../../componentes/select-busca/select-busca';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { gerarPrevisaoStream, mensagemErroPrevisao } from '../../../../servicos/previsao-stream';

interface Filial {
  codigo: string;
  nome: string;
}

interface ItemFluxoMes {
  mes: string;
  a_receber: number;
  a_pagar: number;
  a_receber_estimado: number;
  a_pagar_estimado: number;
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
  prazo_medio_recebimento_dias: number;
  prazo_medio_pagamento_dias: number;
}

interface EtapaPrevisao {
  id: string;
  rotulo: string;
  status: 'pendente' | 'concluido';
}

// Cores da marca (mesmo verde/laranja da logo do Grupo Conceito) — verde
// como cor primária/principal, laranja como secundária. A API só devolve
// {nome, valor} pra cada fatia — a cor é atribuída aqui pela ordem (1ª fatia
// = "No período" = primária, 2ª = "Fora do período" = secundária).
const COR_PRIMARIA = '#2f9e58';
const COR_SECUNDARIA = '#e8871e';
const CORES_FATIAS = [COR_PRIMARIA, COR_SECUNDARIA];

const ETAPAS_INICIAIS: EtapaPrevisao[] = [
  { id: 'titulos_abertos', rotulo: 'Buscando títulos em aberto', status: 'pendente' },
  {
    id: 'prazo_medio',
    rotulo: 'Calculando prazo médio de recebimento e pagamento',
    status: 'pendente',
  },
  {
    id: 'projecao_futura',
    rotulo: 'Projetando tendência de vendas e novas contas a pagar',
    status: 'pendente',
  },
];

@Component({
  selector: 'app-fluxo-caixa',
  imports: [ModuloHeader, SelectBusca, Botao, GraficoSerie, GraficoRosca, CartaoKpi, EstadoVazio],
  templateUrl: './fluxo-caixa.html',
  styleUrl: './fluxo-caixa.scss',
})
export class FluxoCaixa {
  private readonly http = inject(HttpClient);

  protected readonly filiais = signal<OpcaoSelectBusca[]>([]);
  protected readonly filiaisSelecionadas = signal<string[]>([]);

  protected readonly jaGerou = signal(false);
  protected readonly carregando = signal(false);
  protected readonly erro = signal<string | null>(null);
  protected readonly etapas = signal<EtapaPrevisao[]>(ETAPAS_INICIAIS);
  protected readonly fluxoMeses = signal<ItemFluxoMes[]>([]);
  protected readonly fatiasAReceber = signal<FatiaRosca[]>([]);
  protected readonly fatiasAPagar = signal<FatiaRosca[]>([]);
  protected readonly prazoMedioRecebimentoDias = signal<number | null>(null);
  protected readonly prazoMedioPagamentoDias = signal<number | null>(null);

  protected readonly podeGerar = computed(
    () => this.filiaisSelecionadas().length > 0 && !this.carregando(),
  );

  protected readonly totalAReceber = computed(() =>
    this.fatiasAReceber().reduce((soma, fatia) => soma + fatia.valor, 0),
  );
  protected readonly totalAPagar = computed(() =>
    this.fatiasAPagar().reduce((soma, fatia) => soma + fatia.valor, 0),
  );
  protected readonly vencidoAReceber = computed(
    () => this.fluxoMeses().find((item) => item.mes === 'vencido')?.a_receber ?? 0,
  );
  protected readonly vencidoAPagar = computed(
    () => this.fluxoMeses().find((item) => item.mes === 'vencido')?.a_pagar ?? 0,
  );
  protected readonly saldoProjetado = computed(() => this.totalAReceber() - this.totalAPagar());

  protected readonly seriesFluxoCaixa = computed<SerieGrafico[]>(() => {
    const meses = this.fluxoMeses();
    if (!meses.length) {
      return [];
    }

    return [
      {
        nome: 'A Receber',
        cor: COR_PRIMARIA,
        pontos: meses.map((item) => ({ rotulo: item.mes, valor: item.a_receber })),
      },
      {
        nome: 'A Pagar',
        cor: COR_SECUNDARIA,
        pontos: meses.map((item) => ({ rotulo: item.mes, valor: item.a_pagar })),
      },
      {
        nome: 'A Receber (estimado)',
        cor: COR_PRIMARIA,
        tracejada: true,
        linhaSobreposta: true,
        pontos: meses.map((item) => ({ rotulo: item.mes, valor: item.a_receber_estimado })),
      },
      {
        nome: 'A Pagar (estimado)',
        cor: COR_SECUNDARIA,
        tracejada: true,
        linhaSobreposta: true,
        pontos: meses.map((item) => ({ rotulo: item.mes, valor: item.a_pagar_estimado })),
      },
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
      },
    });
  }

  protected async gerarPrevisao(): Promise<void> {
    if (!this.podeGerar()) {
      return;
    }

    this.carregando.set(true);
    this.erro.set(null);
    this.etapas.set(ETAPAS_INICIAIS.map((etapa) => ({ ...etapa })));

    try {
      const resposta = await gerarPrevisaoStream<RespostaFluxoCaixa>(
        this.http,
        `${MCP_API_BASE_URL}/api/financeiro/previsao/fluxo-caixa`,
        { filial: this.filiaisSelecionadas().join(',') },
        (id) => this.marcarEtapaConcluida(id),
      );

      this.jaGerou.set(true);
      this.fluxoMeses.set(resposta.meses);
      this.fatiasAReceber.set(this.colorirFatias(resposta.fatias_a_receber));
      this.fatiasAPagar.set(this.colorirFatias(resposta.fatias_a_pagar));
      this.prazoMedioRecebimentoDias.set(resposta.prazo_medio_recebimento_dias);
      this.prazoMedioPagamentoDias.set(resposta.prazo_medio_pagamento_dias);
    } catch (erroDesconhecido) {
      this.erro.set(mensagemErroPrevisao(erroDesconhecido));
    } finally {
      this.carregando.set(false);
    }
  }

  private colorirFatias(fatias: FatiaApi[]): FatiaRosca[] {
    return fatias.map((fatia, indice) => ({ ...fatia, cor: CORES_FATIAS[indice] ?? COR_PRIMARIA }));
  }

  private marcarEtapaConcluida(id: string): void {
    this.etapas.update((atual) =>
      atual.map((etapa) => (etapa.id === id ? { ...etapa, status: 'concluido' } : etapa)),
    );
  }
}
