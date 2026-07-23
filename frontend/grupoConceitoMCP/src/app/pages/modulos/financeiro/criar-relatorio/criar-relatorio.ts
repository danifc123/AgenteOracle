import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { Botao } from '../../../../componentes/botao/botao';
import { Busca } from '../../../../componentes/busca/busca';
import { Dialog } from '../../../../componentes/dialog/dialog';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { OpcaoSelectBusca } from '../../../../componentes/select-busca/select-busca';
import { TabelaDetalhe } from '../../../../componentes/tabela-detalhe/tabela-detalhe';
import { TabelaItem } from '../../../../componentes/tabela-item/tabela-item';
import { VisualizadorExcel } from '../../../../componentes/visualizador-excel/visualizador-excel';
import { ViewFinanceira } from '../../../../dadosRelatorios/views-financeiras';

interface Filial {
  codigo: string;
  nome: string;
}

@Component({
  selector: 'app-criar-relatorio',
  imports: [Busca, Dialog, Botao, VisualizadorExcel, ModuloHeader, TabelaItem, TabelaDetalhe],
  templateUrl: './criar-relatorio.html',
  styleUrl: './criar-relatorio.scss'
})
export class CriarRelatorio {
  private readonly http = inject(HttpClient);

  protected readonly views = signal<ViewFinanceira[]>([]);
  protected readonly termoBusca = signal('');
  protected readonly tabelasAbertas = signal<Set<string>>(new Set());
  protected readonly colunasSelecionadas = signal<Record<string, string[]>>({});

  protected readonly relatorioAberto = signal(false);
  protected readonly relatorioCarregando = signal(false);
  protected readonly relatorioErro = signal<string | null>(null);
  protected readonly relatorioDados = signal<Record<string, unknown>[] | null>(null);
  protected readonly baixandoRelatorio = signal(false);

  protected readonly filiais = signal<OpcaoSelectBusca[]>([]);
  protected readonly filiaisSelecionadas = signal<string[]>([]);
  protected readonly valoresFiltros = signal<Record<string, string>>({});
  protected readonly opcoesColunas = signal<Record<string, OpcaoSelectBusca[]>>({});
  protected readonly filtroInvalido = signal(false);

  protected readonly viewsFiltradas = computed(() => {
    const termo = this.termoBusca().trim().toLowerCase();
    if (!termo) {
      return this.views();
    }
    return this.views().filter(
      (view) => view.nome.toLowerCase().includes(termo) || view.descricao.toLowerCase().includes(termo)
    );
  });

  protected readonly totalColunasSelecionadas = computed(() =>
    Object.values(this.colunasSelecionadas()).reduce((total, colunas) => total + colunas.length, 0)
  );

  constructor() {
    this.carregarViews();
    this.carregarFiliais();
  }

  private carregarViews(): void {
    this.http.get<ViewFinanceira[]>(`${MCP_API_BASE_URL}/api/financeiro/relatorio/views`).subscribe({
      next: (views) => this.views.set(views),
      error: () => this.views.set([])
    });
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

  protected estaAberta(view: ViewFinanceira): boolean {
    return this.tabelasAbertas().has(view.nome);
  }

  protected colunasDaView(view: ViewFinanceira): string[] {
    return this.colunasSelecionadas()[view.nome] ?? [];
  }

  /** Acordeão: só uma tabela expandida por vez — abrir outra fecha a
   * anterior. As colunas já marcadas em tabelas fechadas continuam
   * selecionadas normalmente, só a exibição da lista de colunas fecha. */
  protected alternarTabela(view: ViewFinanceira): void {
    this.tabelasAbertas.update((atual) => (atual.has(view.nome) ? new Set() : new Set([view.nome])));
  }

  protected alternarColuna(nomeView: string, nomeColuna: string): void {
    const jaSelecionada = (this.colunasSelecionadas()[nomeView] ?? []).includes(nomeColuna);

    this.colunasSelecionadas.update((atual) => {
      const colunasAtuais = atual[nomeView] ?? [];
      const novasColunas = jaSelecionada
        ? colunasAtuais.filter((coluna) => coluna !== nomeColuna)
        : [...colunasAtuais, nomeColuna];

      const novo = { ...atual };
      if (novasColunas.length) {
        novo[nomeView] = novasColunas;
      } else {
        delete novo[nomeView];
      }
      return novo;
    });

    if (!jaSelecionada) {
      const tipo = this.views()
        .find((view) => view.nome === nomeView)
        ?.colunas.find((coluna) => coluna.nome === nomeColuna)?.tipo;
      if (tipo === 'texto') {
        this.carregarOpcoesColuna(`${nomeView}.${nomeColuna}`);
      }
    }
  }

  /** Valores distintos da coluna, pro select multiplo do filtro dela — busca
   * uma vez só e guarda em cache (não muda enquanto a tela estiver aberta). */
  private carregarOpcoesColuna(chave: string): void {
    if (this.opcoesColunas()[chave]) {
      return;
    }

    this.http
      .get<OpcaoSelectBusca[]>(`${MCP_API_BASE_URL}/api/financeiro/relatorio/opcoes-coluna`, {
        params: { coluna: chave }
      })
      .subscribe({
        next: (opcoes) => this.opcoesColunas.update((atual) => ({ ...atual, [chave]: opcoes })),
        error: () => this.opcoesColunas.update((atual) => ({ ...atual, [chave]: [] }))
      });
  }

  protected definirValorFiltro(chave: string, valor: string): void {
    this.valoresFiltros.update((atual) => ({ ...atual, [chave]: valor }));
  }

  protected limparFiltrosSelecionados(): void {
    this.filiaisSelecionadas.set([]);
    this.colunasSelecionadas.set({});
    this.valoresFiltros.set({});
  }

  protected confirmarFiltroSelecionada(): void {
    if (!this.totalColunasSelecionadas() || !this.filiaisSelecionadas().length) {
      this.sinalizarFiltroInvalido();
      return;
    }

    this.buscarRelatorio();
  }

  private sinalizarFiltroInvalido(): void {
    this.filtroInvalido.set(true);
    setTimeout(() => this.filtroInvalido.set(false), 400);
  }

  private parametrosRelatorio(): HttpParams {
    const colunas = Object.entries(this.colunasSelecionadas()).flatMap(([nomeView, nomesColunas]) =>
      nomesColunas.map((nomeColuna) => `${nomeView}.${nomeColuna}`)
    );

    let params = new HttpParams().set('filial', this.filiaisSelecionadas().join(',')).set('colunas', colunas.join(','));

    const filtros = this.filtrosPorColuna();
    if (Object.keys(filtros).length) {
      params = params.set('filtros', JSON.stringify(filtros));
    }

    return params;
  }

  /** Monta {"view.coluna": {...}} a partir de valoresFiltros(), no formato
   * que cada tipo de coluna espera (texto: valores, lista de valores exatos
   * escolhidos no select multiplo — guardados aqui como string separada por
   * vírgula; numero: min/max; periodo-data: ini/fim) — só entram colunas com
   * algum valor preenchido. */
  private filtrosPorColuna(): Record<string, Record<string, string | string[]>> {
    const valores = this.valoresFiltros();
    const views = this.views();
    const filtros: Record<string, Record<string, string | string[]>> = {};

    for (const [nomeView, nomesColunas] of Object.entries(this.colunasSelecionadas())) {
      const view = views.find((item) => item.nome === nomeView);

      for (const nomeColuna of nomesColunas) {
        const chave = `${nomeView}.${nomeColuna}`;
        const tipo = view?.colunas.find((coluna) => coluna.nome === nomeColuna)?.tipo ?? 'texto';

        if (tipo === 'periodo-data') {
          const entrada = this.entradaFaixa(valores, chave, 'ini', 'fim');
          if (entrada) {
            filtros[chave] = entrada;
          }
        } else if (tipo === 'numero') {
          const entrada = this.entradaFaixa(valores, chave, 'min', 'max');
          if (entrada) {
            filtros[chave] = entrada;
          }
        } else if (valores[chave]) {
          const selecionados = valores[chave].split(',').filter(Boolean);
          if (selecionados.length) {
            filtros[chave] = { valores: selecionados };
          }
        }
      }
    }

    return filtros;
  }

  private entradaFaixa(
    valores: Record<string, string>,
    chave: string,
    chaveMin: string,
    chaveMax: string
  ): Record<string, string> | null {
    const min = valores[`${chave}_ini`];
    const max = valores[`${chave}_fim`];
    if (!min && !max) {
      return null;
    }
    return { ...(min ? { [chaveMin]: min } : {}), ...(max ? { [chaveMax]: max } : {}) };
  }

  private buscarRelatorio(): void {
    this.relatorioAberto.set(true);
    this.relatorioDados.set(null);
    this.relatorioErro.set(null);
    this.relatorioCarregando.set(true);

    this.http
      .get<Record<string, unknown>[]>(`${MCP_API_BASE_URL}/api/financeiro/relatorio-customizado`, {
        params: this.parametrosRelatorio()
      })
      .subscribe({
        next: (dados) => {
          this.relatorioDados.set(dados);
          this.relatorioCarregando.set(false);
        },
        error: (erro: HttpErrorResponse) => {
          this.relatorioErro.set(
            erro.error?.erro ?? 'Não foi possível carregar o relatório. Verifique se o servidor está em execução.'
          );
          this.relatorioCarregando.set(false);
        }
      });
  }

  protected fecharVisualizacao(): void {
    this.relatorioAberto.set(false);
    this.relatorioDados.set(null);
    this.relatorioErro.set(null);
    this.relatorioCarregando.set(false);
  }

  protected baixarRelatorio(): void {
    if (this.baixandoRelatorio()) {
      return;
    }

    this.baixandoRelatorio.set(true);

    this.http
      .get(`${MCP_API_BASE_URL}/api/financeiro/relatorio-customizado/exportar`, {
        params: this.parametrosRelatorio(),
        observe: 'response',
        responseType: 'blob'
      })
      .subscribe({
        next: (resposta) => {
          const blob = resposta.body;
          if (!blob) {
            this.baixandoRelatorio.set(false);
            return;
          }

          const nomeArquivo = this.extrairNomeArquivo(resposta.headers.get('content-disposition')) ?? 'relatorio_customizado.xlsx';
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = nomeArquivo;
          link.click();
          URL.revokeObjectURL(url);
          this.baixandoRelatorio.set(false);
        },
        error: () => {
          this.baixandoRelatorio.set(false);
        }
      });
  }

  private extrairNomeArquivo(contentDisposition: string | null): string | undefined {
    const match = contentDisposition?.match(/filename="?([^"]+)"?/);
    return match?.[1];
  }
}
