import { Component, computed, signal } from '@angular/core';
import { Botao } from '../../../../componentes/botao/botao';
import { Busca } from '../../../../componentes/busca/busca';
import { Dialog } from '../../../../componentes/dialog/dialog';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { OpcaoSelectBusca, SelectBusca } from '../../../../componentes/select-busca/select-busca';
import { TabelaDetalhe } from '../../../../componentes/tabela-detalhe/tabela-detalhe';
import { TabelaItem } from '../../../../componentes/tabela-item/tabela-item';
import { LayoutRelatorio } from '../../../../dadosRelatorios/relatorio-layouts';
import { ViewFinanceira } from '../../../../dadosRelatorios/views-financeiras';
import { MOCK_VIEWS_ESTOQUE } from '../../../../dadosRelatorios/views-estoque';

// Dado de mentira só pra construir/ajustar os componentes visuais — troca
// pra dados reais assim que existir a consulta SQL desse módulo (ver
// `estoque.ts`). Sem chamada de API nenhuma aqui ainda.
const MOCK_FILIAIS: OpcaoSelectBusca[] = [
  { valor: '0101', rotulo: '0101 - Matriz' },
  { valor: '0102', rotulo: '0102 - Filial Sul' },
];

const MOCK_OPCOES_COLUNA: Record<string, OpcaoSelectBusca[]> = {
  'vw_movimentacao_estoque.tipo': [
    { valor: 'entrada', rotulo: 'entrada' },
    { valor: 'saida', rotulo: 'saida' },
  ],
  'vw_movimentacao_estoque.produto_codigo': [
    { valor: 'P001', rotulo: 'P001' },
    { valor: 'P002', rotulo: 'P002' },
    { valor: 'P003', rotulo: 'P003' },
  ],
  'vw_produtos.codigo': [
    { valor: 'P001', rotulo: 'P001' },
    { valor: 'P002', rotulo: 'P002' },
    { valor: 'P003', rotulo: 'P003' },
  ],
  'vw_produtos.descricao': [
    { valor: 'Semente de Soja RR', rotulo: 'Semente de Soja RR' },
    { valor: 'Fertilizante NPK 20-05-20', rotulo: 'Fertilizante NPK 20-05-20' },
    { valor: 'Defensivo Agrícola Glifosato', rotulo: 'Defensivo Agrícola Glifosato' },
    { valor: 'Óleo Diesel S10', rotulo: 'Óleo Diesel S10' },
  ],
  'vw_fornecedores.codigo': [
    { valor: 'F001', rotulo: 'F001' },
    { valor: 'F002', rotulo: 'F002' },
  ],
  'vw_fornecedores.nome': [
    { valor: 'Cooperativa Agrícola Central', rotulo: 'Cooperativa Agrícola Central' },
    { valor: 'Distribuidora AgroMax', rotulo: 'Distribuidora AgroMax' },
  ],
};

@Component({
  selector: 'app-estoque-criar-relatorio',
  imports: [Busca, Dialog, Botao, ModuloHeader, TabelaItem, TabelaDetalhe, SelectBusca],
  templateUrl: './criar-relatorio.html',
  styleUrl: './criar-relatorio.scss',
})
export class EstoqueCriarRelatorio {
  protected readonly views = signal<ViewFinanceira[]>(MOCK_VIEWS_ESTOQUE);
  protected readonly termoBusca = signal('');
  protected readonly tabelasAbertas = signal<Set<string>>(new Set());
  protected readonly colunasSelecionadas = signal<Record<string, string[]>>({});

  protected readonly relatorioAberto = signal(false);

  protected readonly filiais = signal<OpcaoSelectBusca[]>(MOCK_FILIAIS);
  protected readonly filiaisSelecionadas = signal<string[]>([]);
  protected readonly valoresFiltros = signal<Record<string, string>>({});
  protected readonly opcoesColunas = signal<Record<string, OpcaoSelectBusca[]>>({});
  protected readonly filtroInvalido = signal(false);

  protected readonly layouts = signal<LayoutRelatorio[]>([]);
  protected readonly layoutSelecionadoId = signal<string | null>(null);
  protected readonly salvarLayoutAberto = signal(false);
  protected readonly nomeNovoLayout = signal('');
  protected readonly erroSalvarLayout = signal<string | null>(null);

  protected readonly viewsFiltradas = computed(() => {
    const termo = this.termoBusca().trim().toLowerCase();
    if (!termo) {
      return this.views();
    }
    return this.views().filter(
      (view) =>
        view.nome.toLowerCase().includes(termo) || view.descricao.toLowerCase().includes(termo),
    );
  });

  protected readonly totalColunasSelecionadas = computed(() =>
    Object.values(this.colunasSelecionadas()).reduce((total, colunas) => total + colunas.length, 0),
  );

  protected readonly opcoesLayouts = computed<OpcaoSelectBusca[]>(() =>
    this.layouts().map((layout) => ({ valor: String(layout.id), rotulo: layout.nome })),
  );

  /** Grafo não-direcionado das views a partir dos relacionamentos declarados
   * — usado só pra decidir quais tabelas ficam bloqueadas na lista, mesma
   * lógica do "Criar Relatório" do Financeiro. */
  private readonly grafoRelacionamentos = computed(() => {
    const grafo = new Map<string, Set<string>>();
    for (const view of this.views()) {
      grafo.set(view.nome, grafo.get(view.nome) ?? new Set());
      for (const rel of view.relacionamentos) {
        if (!grafo.has(rel.viewDestino)) {
          grafo.set(rel.viewDestino, new Set());
        }
        grafo.get(view.nome)!.add(rel.viewDestino);
        grafo.get(rel.viewDestino)!.add(view.nome);
      }
    }
    return grafo;
  });

  /** Nomes das tabelas alcançáveis a partir da seleção atual (colunas já
   * marcadas), direto ou por relacionamento indireto. `null` quando nada
   * foi selecionado ainda — nesse caso qualquer tabela pode ser a primeira. */
  protected readonly tabelasCompativeis = computed<Set<string> | null>(() => {
    const selecionadas = Object.entries(this.colunasSelecionadas())
      .filter(([, colunas]) => colunas.length > 0)
      .map(([nomeView]) => nomeView);

    if (!selecionadas.length) {
      return null;
    }

    const grafo = this.grafoRelacionamentos();
    const visitados = new Set(selecionadas);
    const fila = [...selecionadas];

    while (fila.length) {
      const atual = fila.shift()!;
      for (const vizinho of grafo.get(atual) ?? []) {
        if (!visitados.has(vizinho)) {
          visitados.add(vizinho);
          fila.push(vizinho);
        }
      }
    }

    return visitados;
  });

  protected abrirSalvarLayout(): void {
    if (!this.totalColunasSelecionadas()) {
      return;
    }
    this.nomeNovoLayout.set('');
    this.erroSalvarLayout.set(null);
    this.salvarLayoutAberto.set(true);
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
      const chave = `${nomeView}.${nomeColuna}`;
      if (MOCK_OPCOES_COLUNA[chave]) {
        this.opcoesColunas.update((atual) => ({ ...atual, [chave]: MOCK_OPCOES_COLUNA[chave] }));
      }
    }
  }

  /** Acordeão: só uma tabela expandida por vez — abrir outra fecha a
   * anterior. Tabelas sem vínculo com a seleção atual não abrem. */
  protected alternarTabela(view: ViewFinanceira): void {
    if (!this.tabelaCompativel(view)) {
      return;
    }
    this.tabelasAbertas.update((atual) =>
      atual.has(view.nome) ? new Set() : new Set([view.nome]),
    );
  }

  protected aplicarLayout(id: string | null): void {
    this.layoutSelecionadoId.set(id);
    if (!id) {
      this.limparFiltrosSelecionados();
      return;
    }

    const layout = this.layouts().find((item) => String(item.id) === id);
    if (!layout) {
      return;
    }

    this.colunasSelecionadas.set(layout.colunas_selecionadas);
    this.valoresFiltros.set(layout.valores_filtros);
    this.filiaisSelecionadas.set(layout.filiais_selecionadas);
  }

  protected colunasDaView(view: ViewFinanceira): string[] {
    return this.colunasSelecionadas()[view.nome] ?? [];
  }

  protected confirmarFiltroSelecionada(): void {
    if (!this.totalColunasSelecionadas() || !this.filiaisSelecionadas().length) {
      this.sinalizarFiltroInvalido();
      return;
    }

    // Sem consulta SQL ainda pra este módulo — só abre o dialog, que mostra
    // o placeholder "relatório ainda não disponível".
    this.relatorioAberto.set(true);
  }

  private sinalizarFiltroInvalido(): void {
    this.filtroInvalido.set(true);
    setTimeout(() => this.filtroInvalido.set(false), 400);
  }

  /** Sem backend ainda — o layout só fica guardado em memória (não
   * sobrevive a um F5), diferente do Financeiro que persiste via API. */
  protected confirmarSalvarLayout(): void {
    const nome = this.nomeNovoLayout().trim();
    if (!nome) {
      this.erroSalvarLayout.set('Dê um nome pro layout.');
      return;
    }

    const agora = new Date().toISOString();
    const novoLayout: LayoutRelatorio = {
      id: Date.now(),
      nome,
      colunas_selecionadas: this.colunasSelecionadas(),
      valores_filtros: this.valoresFiltros(),
      filiais_selecionadas: this.filiaisSelecionadas(),
      criado_em: agora,
      atualizado_em: agora,
    };

    this.layouts.update((atual) =>
      [...atual, novoLayout].sort((a, b) => a.nome.localeCompare(b.nome)),
    );
    this.layoutSelecionadoId.set(String(novoLayout.id));
    this.salvarLayoutAberto.set(false);
  }

  protected definirValorFiltro(chave: string, valor: string): void {
    this.valoresFiltros.update((atual) => ({ ...atual, [chave]: valor }));
  }

  protected estaAberta(view: ViewFinanceira): boolean {
    return this.tabelasAbertas().has(view.nome);
  }

  protected fecharSalvarLayout(): void {
    this.salvarLayoutAberto.set(false);
  }

  protected fecharVisualizacao(): void {
    this.relatorioAberto.set(false);
  }

  protected limparFiltrosSelecionados(): void {
    this.filiaisSelecionadas.set([]);
    this.colunasSelecionadas.set({});
    this.valoresFiltros.set({});
    this.layoutSelecionadoId.set(null);
  }

  protected tabelaCompativel(view: ViewFinanceira): boolean {
    const compativeis = this.tabelasCompativeis();
    return !compativeis || compativeis.has(view.nome);
  }
}
