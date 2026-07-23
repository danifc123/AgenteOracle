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

  protected alternarTabela(view: ViewFinanceira): void {
    this.tabelasAbertas.update((atual) => {
      const novo = new Set(atual);
      if (novo.has(view.nome)) {
        novo.delete(view.nome);
      } else {
        novo.add(view.nome);
      }
      return novo;
    });
  }

  protected alternarColuna(nomeView: string, nomeColuna: string): void {
    this.colunasSelecionadas.update((atual) => {
      const colunasAtuais = atual[nomeView] ?? [];
      const novasColunas = colunasAtuais.includes(nomeColuna)
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
  }

  protected limparFiltrosSelecionados(): void {
    this.filiaisSelecionadas.set([]);
    this.colunasSelecionadas.set({});
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

    return new HttpParams().set('filial', this.filiaisSelecionadas().join(',')).set('colunas', colunas.join(','));
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
