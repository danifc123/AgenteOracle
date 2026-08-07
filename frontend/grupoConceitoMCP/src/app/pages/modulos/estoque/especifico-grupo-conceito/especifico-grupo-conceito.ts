import { Component, computed, inject, signal } from '@angular/core';
import { Busca } from '../../../../componentes/busca/busca';
import { Dialog } from '../../../../componentes/dialog/dialog';
import {
  FiltroCategorias,
  OpcaoCategoria,
} from '../../../../componentes/filtro-categorias/filtro-categorias';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { RotinaDetalhe } from '../../../../componentes/rotina-detalhe/rotina-detalhe';
import { RotinaItem } from '../../../../componentes/rotina-item/rotina-item';
import { OpcaoSelectBusca } from '../../../../componentes/select-busca/select-busca';
import { CampoFiltro, RotinaFinanceira } from '../../../../dadosRelatorios/modulos-financeiro';
import { ROTINAS_ESTOQUE } from '../../../../dadosRelatorios/modulos-estoque';
import { CoresCategoria } from '../../../../servicos/cores-categoria';

const LIMITE_FIXADOS = 3;
const CATEGORIA_FIXADOS = 'Fixados';
const COR_FIXADOS = '#d8a81a';
const CHAVE_FIXADOS = 'estoque:especifico-grupo-conceito:fixados';

// Dado de mentira só pra construir/ajustar os componentes visuais — troca
// pra dados reais assim que existir a consulta SQL desse módulo.
const MOCK_FILIAIS: OpcaoSelectBusca[] = [
  { valor: '0101', rotulo: '0101 - Matriz' },
  { valor: '0102', rotulo: '0102 - Filial Sul' },
];

interface GrupoRotinas {
  categoria: string;
  cor: string;
  rotinas: RotinaFinanceira[];
}

@Component({
  selector: 'app-estoque-especifico-grupo-conceito',
  imports: [Busca, Dialog, ModuloHeader, RotinaItem, RotinaDetalhe, FiltroCategorias],
  templateUrl: './especifico-grupo-conceito.html',
  styleUrl: './especifico-grupo-conceito.scss',
})
export class EstoqueEspecificoGrupoConceito {
  private readonly coresCategoria = inject(CoresCategoria);

  protected readonly termoBusca = signal('');
  protected readonly categoriaSelecionada = signal<string | null>(null);
  protected readonly rotinaEmVisualizacao = signal<RotinaFinanceira | null>(null);
  private readonly fixados = signal<string[]>(this.lerFixadosSalvos());

  protected readonly rotinaSelecionada = signal<RotinaFinanceira | null>(null);
  protected readonly filiais = signal<OpcaoSelectBusca[]>(MOCK_FILIAIS);
  protected readonly filiaisSelecionadas = signal<string[]>([]);
  protected readonly valoresFiltros = signal<Record<string, string>>({});
  protected readonly filtroInvalido = signal(false);

  protected readonly categoriasDisponiveis = computed<OpcaoCategoria[]>(() => {
    const vistas = new Set<string>();
    const categorias: OpcaoCategoria[] = [];

    if (this.fixados().length) {
      categorias.push({ nome: CATEGORIA_FIXADOS, cor: COR_FIXADOS });
    }

    for (const rotina of ROTINAS_ESTOQUE) {
      if (!vistas.has(rotina.categoria)) {
        vistas.add(rotina.categoria);
        categorias.push({
          nome: rotina.categoria,
          cor: this.coresCategoria.obterCor(rotina.categoria),
        });
      }
    }

    return categorias;
  });

  protected readonly rotinasFiltradas = computed(() => {
    const termo = this.termoBusca().trim().toLowerCase();
    const categoria = this.categoriaSelecionada();
    const fixados = this.fixados();

    return ROTINAS_ESTOQUE.filter((rotina) => {
      const combinaTermo = !termo || rotina.nome.toLowerCase().includes(termo);
      const combinaCategoria =
        !categoria || categoria === CATEGORIA_FIXADOS || rotina.categoria === categoria;
      const combinaFixado = categoria !== CATEGORIA_FIXADOS || fixados.includes(rotina.nome);
      return combinaTermo && combinaCategoria && combinaFixado;
    });
  });

  protected readonly gruposFiltrados = computed<GrupoRotinas[]>(() => {
    const fixados = this.fixados();
    const filtradas = this.rotinasFiltradas();

    if (this.categoriaSelecionada() === CATEGORIA_FIXADOS) {
      return filtradas.length
        ? [{ categoria: CATEGORIA_FIXADOS, cor: COR_FIXADOS, rotinas: filtradas }]
        : [];
    }

    const grupos: GrupoRotinas[] = [];
    const fixadasNaLista = filtradas.filter((rotina) => fixados.includes(rotina.nome));

    if (fixadasNaLista.length) {
      grupos.push({
        categoria: CATEGORIA_FIXADOS,
        cor: COR_FIXADOS,
        rotinas: [...fixadasNaLista].sort(
          (a, b) => fixados.indexOf(a.nome) - fixados.indexOf(b.nome),
        ),
      });
    }

    const mapa = new Map<string, RotinaFinanceira[]>();
    for (const rotina of filtradas) {
      if (fixados.includes(rotina.nome)) {
        continue;
      }
      const grupo = mapa.get(rotina.categoria) ?? [];
      grupo.push(rotina);
      mapa.set(rotina.categoria, grupo);
    }

    for (const [categoria, rotinas] of mapa) {
      grupos.push({ categoria, cor: this.coresCategoria.obterCor(categoria), rotinas });
    }

    return grupos;
  });

  protected estaFixado(rotina: RotinaFinanceira | null): boolean {
    return !!rotina && this.fixados().includes(rotina.nome);
  }

  protected limiteFixadosAtingido(): boolean {
    return this.fixados().length >= LIMITE_FIXADOS;
  }

  protected alternarFixadoSelecionada(): void {
    const rotina = this.rotinaSelecionada();
    if (rotina) {
      this.alternarFixado(rotina);
    }
  }

  private alternarFixado(rotina: RotinaFinanceira): void {
    const atual = this.fixados();

    if (atual.includes(rotina.nome)) {
      this.salvarFixados(atual.filter((nome) => nome !== rotina.nome));
      return;
    }

    if (atual.length >= LIMITE_FIXADOS) {
      return;
    }

    this.salvarFixados([rotina.nome, ...atual]);
  }

  protected selecionarRotina(rotina: RotinaFinanceira): void {
    if (this.rotinaSelecionada()?.nome !== rotina.nome) {
      this.valoresFiltros.set({});
      this.filtroInvalido.set(false);
    }
    this.rotinaSelecionada.set(rotina);
  }

  protected limparFiltrosSelecionados(): void {
    this.filiaisSelecionadas.set([]);
    this.valoresFiltros.set({});
  }

  protected definirValorFiltro(chave: string, valor: string): void {
    this.valoresFiltros.update((atual) => ({ ...atual, [chave]: valor }));
  }

  protected confirmarFiltroSelecionada(): void {
    const rotina = this.rotinaSelecionada();
    if (!rotina) {
      return;
    }

    if (!this.filiaisSelecionadas().length || !this.filtrosObrigatoriosPreenchidos(rotina)) {
      this.sinalizarFiltroInvalido();
      return;
    }

    // Sem consulta SQL ainda pra nenhuma rotina — só abre o dialog, que
    // mostra o placeholder "relatório ainda não disponível" (mesma UX já
    // usada no Financeiro pra rotina sem apiEndpoint).
    this.rotinaEmVisualizacao.set(rotina);
  }

  private filtrosObrigatoriosPreenchidos(rotina: RotinaFinanceira): boolean {
    const valores = this.valoresFiltros();
    return (rotina.filtros ?? []).every((campo: CampoFiltro) => {
      if (!campo.obrigatorio) {
        return true;
      }
      if (campo.tipo === 'periodo-data') {
        return !!valores[`${campo.chave}_ini`]?.trim() && !!valores[`${campo.chave}_fim`]?.trim();
      }
      return !!valores[campo.chave]?.trim();
    });
  }

  private sinalizarFiltroInvalido(): void {
    this.filtroInvalido.set(true);
    setTimeout(() => this.filtroInvalido.set(false), 400);
  }

  protected fecharVisualizacao(): void {
    this.rotinaEmVisualizacao.set(null);
  }

  private lerFixadosSalvos(): string[] {
    const salvos = localStorage.getItem(CHAVE_FIXADOS);
    return salvos ? (JSON.parse(salvos) as string[]) : [];
  }

  private salvarFixados(nomes: string[]): void {
    this.fixados.set(nomes);
    localStorage.setItem(CHAVE_FIXADOS, JSON.stringify(nomes));
  }
}
