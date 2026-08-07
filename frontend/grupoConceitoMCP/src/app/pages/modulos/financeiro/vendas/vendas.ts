import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { Botao } from '../../../../componentes/botao/botao';
import { CartaoKpi } from '../../../../componentes/cartao-kpi/cartao-kpi';
import { GraficoSerie, SerieGrafico } from '../../../../componentes/grafico-serie/grafico-serie';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { OpcaoSelectBusca, SelectBusca } from '../../../../componentes/select-busca/select-busca';
import { gerarPrevisaoStream, mensagemErroPrevisao } from '../../../../servicos/previsao-stream';

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

interface EtapaPrevisao {
  id: string;
  rotulo: string;
  status: 'pendente' | 'concluido';
}

// Verde da marca — mesma cor primária usada no Fluxo de Caixa.
const COR_VENDAS = '#2f9e58';

const ETAPAS_INICIAIS: EtapaPrevisao[] = [
  { id: 'historico', rotulo: 'Buscando faturamento histórico', status: 'pendente' },
  {
    id: 'projecao',
    rotulo: 'Projetando tendência de vendas (regressão linear)',
    status: 'pendente',
  },
  { id: 'analise_ia', rotulo: 'Gerando análise com IA', status: 'pendente' },
];

@Component({
  selector: 'app-vendas',
  imports: [ModuloHeader, SelectBusca, Botao, GraficoSerie, CartaoKpi],
  templateUrl: './vendas.html',
  styleUrl: './vendas.scss',
})
export class Vendas {
  private readonly http = inject(HttpClient);

  protected readonly filiais = signal<OpcaoSelectBusca[]>([]);
  protected readonly filiaisSelecionadas = signal<string[]>([]);

  protected readonly jaGerou = signal(false);
  protected readonly carregando = signal(false);
  protected readonly erro = signal<string | null>(null);
  protected readonly etapas = signal<EtapaPrevisao[]>(ETAPAS_INICIAIS);
  protected readonly vendasHistorico = signal<ItemMes[]>([]);
  protected readonly vendasProjecao = signal<ItemMes[]>([]);
  protected readonly vendasAnalise = signal<string | null>(null);

  protected readonly podeGerar = computed(
    () => this.filiaisSelecionadas().length > 0 && !this.carregando(),
  );

  protected readonly faturamentoTotal = computed(() =>
    this.vendasHistorico().reduce((soma, item) => soma + item.valor, 0),
  );
  protected readonly mediaMensal = computed(() => {
    const historico = this.vendasHistorico();
    return historico.length ? this.faturamentoTotal() / historico.length : 0;
  });
  protected readonly projecaoProximoMes = computed(() => this.vendasProjecao()[0]?.valor ?? 0);
  protected readonly projecaoTrimestre = computed(() =>
    this.vendasProjecao().reduce((soma, item) => soma + item.valor, 0),
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
      pontos: historico.map((item) => ({ rotulo: item.mes, valor: item.valor })),
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
        ...projecao.map((item) => ({ rotulo: item.mes, valor: item.valor })),
      ],
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
      },
    });
  }

  private marcarEtapaConcluida(id: string): void {
    this.etapas.update((atual) =>
      atual.map((etapa) => (etapa.id === id ? { ...etapa, status: 'concluido' } : etapa)),
    );
  }

  protected async gerarPrevisao(): Promise<void> {
    if (!this.podeGerar()) {
      return;
    }

    this.carregando.set(true);
    this.erro.set(null);
    this.etapas.set(ETAPAS_INICIAIS.map((etapa) => ({ ...etapa })));

    try {
      const resposta = await gerarPrevisaoStream<RespostaVendas>(
        this.http,
        `${MCP_API_BASE_URL}/api/financeiro/previsao/vendas`,
        { filial: this.filiaisSelecionadas().join(',') },
        (id) => this.marcarEtapaConcluida(id),
      );

      this.jaGerou.set(true);
      this.vendasHistorico.set(resposta.historico);
      this.vendasProjecao.set(resposta.projecao);
      this.vendasAnalise.set(resposta.analise);
    } catch (erroDesconhecido) {
      this.erro.set(mensagemErroPrevisao(erroDesconhecido));
    } finally {
      this.carregando.set(false);
    }
  }
}
