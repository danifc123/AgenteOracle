import { HttpClient, HttpParams } from '@angular/common/http';
import { Component, computed, effect, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { map } from 'rxjs';
import { MCP_API_BASE_URL } from '../../../app-config';
import { Botao } from '../../../componentes/botao/botao';
import { Busca } from '../../../componentes/busca/busca';
import { Dialog } from '../../../componentes/dialog/dialog';
import { FiltroCategorias, OpcaoCategoria } from '../../../componentes/filtro-categorias/filtro-categorias';
import { ModuloHeader } from '../../../componentes/modulo-header/modulo-header';
import { RotinaDetalhe } from '../../../componentes/rotina-detalhe/rotina-detalhe';
import { RotinaItem } from '../../../componentes/rotina-item/rotina-item';
import { OpcaoSelectBusca } from '../../../componentes/select-busca/select-busca';
import { VisualizadorExcel } from '../../../componentes/visualizador-excel/visualizador-excel';
import { CampoFiltro, MODULOS_FINANCEIRO, RotinaFinanceira, corCategoria } from '../../../dadosRelatorios/modulos-financeiro';

const LIMITE_FIXADOS = 3;
const CATEGORIA_FIXADOS = 'Fixados';
const COR_FIXADOS = '#d8a81a';

interface Filial {
  codigo: string;
  nome: string;
}

interface GrupoRotinas {
  categoria: string;
  cor: string;
  rotinas: RotinaFinanceira[];
}

@Component({
  selector: 'app-financeiro',
  imports: [Busca, Dialog, Botao, VisualizadorExcel, ModuloHeader, RotinaItem, RotinaDetalhe, FiltroCategorias],
  templateUrl: './financeiro.html',
  styleUrl: './financeiro.scss'
})
export class Financeiro {
  private readonly route = inject(ActivatedRoute);
  private readonly http = inject(HttpClient);

  private readonly moduloId = toSignal(
    this.route.paramMap.pipe(map((params) => params.get('moduloId') ?? '')),
    { initialValue: this.route.snapshot.paramMap.get('moduloId') ?? '' }
  );

  protected readonly modulo = computed(() =>
    MODULOS_FINANCEIRO.find((item) => item.id === this.moduloId())
  );

  protected readonly termoBusca = signal('');
  protected readonly categoriaSelecionada = signal<string | null>(null);
  protected readonly rotinaEmVisualizacao = signal<RotinaFinanceira | null>(null);
  protected readonly relatorioCarregando = signal(false);
  protected readonly relatorioErro = signal<string | null>(null);
  protected readonly relatorioDados = signal<Record<string, unknown>[] | null>(null);
  protected readonly baixandoRelatorio = signal(false);
  private readonly fixados = signal<string[]>([]);

  protected readonly rotinaSelecionada = signal<RotinaFinanceira | null>(null);
  protected readonly filiais = signal<OpcaoSelectBusca[]>([]);
  protected readonly filiaisSelecionadas = signal<string[]>([]);
  protected readonly valoresFiltros = signal<Record<string, string>>({});
  protected readonly filtroInvalido = signal(false);
  protected readonly opcoesCampos = signal<Record<string, OpcaoSelectBusca[]>>({});

  protected readonly categoriasDisponiveis = computed<OpcaoCategoria[]>(() => {
    const rotinas = this.modulo()?.rotinas ?? [];
    const vistas = new Set<string>();
    const categorias: OpcaoCategoria[] = [];

    if (this.fixados().length) {
      categorias.push({ nome: CATEGORIA_FIXADOS, cor: COR_FIXADOS });
    }

    for (const rotina of rotinas) {
      if (!vistas.has(rotina.categoria)) {
        vistas.add(rotina.categoria);
        categorias.push({ nome: rotina.categoria, cor: corCategoria(rotina.categoria) });
      }
    }

    return categorias;
  });

  protected readonly rotinasFiltradas = computed(() => {
    const rotinas = this.modulo()?.rotinas ?? [];
    const termo = this.termoBusca().trim().toLowerCase();
    const categoria = this.categoriaSelecionada();
    const fixados = this.fixados();

    return rotinas.filter((rotina) => {
      const combinaTermo = !termo || rotina.nome.toLowerCase().includes(termo);
      const combinaCategoria = !categoria || categoria === CATEGORIA_FIXADOS || rotina.categoria === categoria;
      const combinaFixado = categoria !== CATEGORIA_FIXADOS || fixados.includes(rotina.nome);
      return combinaTermo && combinaCategoria && combinaFixado;
    });
  });

  protected readonly gruposFiltrados = computed<GrupoRotinas[]>(() => {
    const fixados = this.fixados();
    const filtradas = this.rotinasFiltradas();

    if (this.categoriaSelecionada() === CATEGORIA_FIXADOS) {
      return filtradas.length ? [{ categoria: CATEGORIA_FIXADOS, cor: COR_FIXADOS, rotinas: filtradas }] : [];
    }

    const grupos: GrupoRotinas[] = [];
    const fixadasNaLista = filtradas.filter((rotina) => fixados.includes(rotina.nome));

    if (fixadasNaLista.length) {
      grupos.push({
        categoria: CATEGORIA_FIXADOS,
        cor: COR_FIXADOS,
        rotinas: [...fixadasNaLista].sort((a, b) => fixados.indexOf(a.nome) - fixados.indexOf(b.nome))
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
      grupos.push({ categoria, cor: corCategoria(categoria), rotinas });
    }

    return grupos;
  });

  constructor() {
    effect(() => {
      this.moduloId();
      this.termoBusca.set('');
      this.categoriaSelecionada.set(null);
      this.fecharVisualizacao();
      this.rotinaSelecionada.set(null);
      this.filiaisSelecionadas.set([]);
      this.valoresFiltros.set({});
      this.carregarFixados();
    });
  }

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

    if (!rotina.apiEndpoint) {
      return;
    }

    if (!this.filiais().length) {
      this.carregarFiliais();
    }

    for (const campo of rotina.filtros ?? []) {
      this.carregarOpcoesCampo(campo);
    }
  }

  protected limparFiltrosSelecionados(): void {
    this.filiaisSelecionadas.set([]);
    this.valoresFiltros.set({});
  }

  private carregarOpcoesCampo(campo: CampoFiltro): void {
    if (!campo.apiEndpoint || this.opcoesCampos()[campo.chave]) {
      return;
    }

    this.http.get<Filial[]>(`${MCP_API_BASE_URL}/api/financeiro/${campo.apiEndpoint}`).subscribe({
      next: (opcoes) => {
        this.opcoesCampos.update((atual) => ({
          ...atual,
          [campo.chave]: opcoes.map((opcao) => ({ valor: opcao.codigo, rotulo: opcao.nome }))
        }));
      },
      error: () => {
        this.opcoesCampos.update((atual) => ({ ...atual, [campo.chave]: [] }));
      }
    });
  }

  private valorFiltro(chave: string): string {
    return this.valoresFiltros()[chave] ?? '';
  }

  protected definirValorFiltro(chave: string, valor: string): void {
    this.valoresFiltros.update((atual) => ({ ...atual, [chave]: valor }));
  }

  protected confirmarFiltroSelecionada(): void {
    const rotina = this.rotinaSelecionada();
    if (rotina) {
      this.confirmarFiltro(rotina);
    }
  }

  private confirmarFiltro(rotina: RotinaFinanceira): void {
    if (!this.filiaisSelecionadas().length || !this.filtrosObrigatoriosPreenchidos(rotina)) {
      this.sinalizarFiltroInvalido();
      return;
    }

    this.buscarRelatorio(rotina);
  }

  private filtrosObrigatoriosPreenchidos(rotina: RotinaFinanceira): boolean {
    const valores = this.valoresFiltros();
    return (rotina.filtros ?? []).every((campo) => {
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

  private buscarRelatorio(rotina: RotinaFinanceira): void {
    this.rotinaEmVisualizacao.set(rotina);
    this.relatorioDados.set(null);
    this.relatorioErro.set(null);

    if (!rotina.apiEndpoint) {
      return;
    }

    this.relatorioCarregando.set(true);
    this.http
      .get<Record<string, unknown>[]>(`${MCP_API_BASE_URL}/api/financeiro/${rotina.apiEndpoint}`, {
        params: this.parametrosRelatorio(rotina)
      })
      .subscribe({
        next: (dados) => {
          this.relatorioDados.set(dados);
          this.relatorioCarregando.set(false);
        },
        error: () => {
          this.relatorioErro.set('Não foi possível carregar o relatório. Verifique se o servidor está em execução.');
          this.relatorioCarregando.set(false);
        }
      });
  }

  protected fecharVisualizacao(): void {
    this.rotinaEmVisualizacao.set(null);
    this.relatorioDados.set(null);
    this.relatorioErro.set(null);
    this.relatorioCarregando.set(false);
  }

  private baixar(rotina: RotinaFinanceira): void {
    if (!rotina.apiEndpoint || this.baixandoRelatorio()) {
      return;
    }

    if (!this.filiaisSelecionadas().length || !this.filtrosObrigatoriosPreenchidos(rotina)) {
      this.selecionarRotina(rotina);
      return;
    }

    this.baixandoRelatorio.set(true);

    this.http
      .get(`${MCP_API_BASE_URL}/api/financeiro/${rotina.apiEndpoint}/exportar`, {
        params: this.parametrosRelatorio(rotina),
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

          const nomeArquivo = this.extrairNomeArquivo(resposta.headers.get('content-disposition')) ?? `${rotina.apiEndpoint}.xlsx`;
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

  protected baixarRotinaEmVisualizacao(): void {
    const rotina = this.rotinaEmVisualizacao();
    if (rotina) {
      this.baixar(rotina);
    }
  }

  private parametrosRelatorio(rotina: RotinaFinanceira): HttpParams {
    let params = new HttpParams().set('filial', this.filiaisSelecionadas().join(','));

    for (const campo of rotina.filtros ?? []) {
      params = this.aplicarCampoNosParametros(params, campo);
    }

    return params;
  }

  private aplicarCampoNosParametros(params: HttpParams, campo: CampoFiltro): HttpParams {
    if (campo.tipo === 'periodo-data') {
      return params
        .set(`${campo.chave}_ini`, this.valorFiltro(`${campo.chave}_ini`))
        .set(`${campo.chave}_fim`, this.valorFiltro(`${campo.chave}_fim`));
    }

    return params.set(campo.chave, this.valorFiltro(campo.chave));
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

  private extrairNomeArquivo(contentDisposition: string | null): string | undefined {
    const match = contentDisposition?.match(/filename="?([^"]+)"?/);
    return match?.[1];
  }

  private carregarFixados(): void {
    const salvos = localStorage.getItem(this.chaveFixados());
    this.fixados.set(salvos ? (JSON.parse(salvos) as string[]) : []);
  }

  private salvarFixados(nomes: string[]): void {
    this.fixados.set(nomes);
    localStorage.setItem(this.chaveFixados(), JSON.stringify(nomes));
  }

  private chaveFixados(): string {
    return `financeiro:${this.moduloId()}:fixados`;
  }
}
