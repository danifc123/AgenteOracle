import { Component, computed, effect, input, model, output, signal } from '@angular/core';
import { CampoFiltro } from '../../dadosRelatorios/modulos-financeiro';
import { ViewFinanceira } from '../../dadosRelatorios/views-financeiras';
import { Botao } from '../botao/botao';
import { CampoFiltroDinamico } from '../campo-filtro-dinamico/campo-filtro-dinamico';
import { OpcaoSelectBusca, SelectBusca } from '../select-busca/select-busca';

interface GrupoColunasSelecionadas {
  view: ViewFinanceira;
  campos: CampoFiltro[];
}

/** A partir de quantos filtros selecionados oferece o botão de expandir o
 * painel em tela cheia — abaixo disso o painel normal já cabe tranquilo. */
const LIMITE_FILTROS_PARA_EXPANDIR = 7;

@Component({
  selector: 'app-tabela-detalhe',
  imports: [SelectBusca, CampoFiltroDinamico, Botao],
  templateUrl: './tabela-detalhe.html',
  styleUrl: './tabela-detalhe.scss',
  host: { '[class.expandido]': 'expandido()' }
})
export class TabelaDetalhe {
  views = input<ViewFinanceira[]>([]);
  colunasSelecionadas = input<Record<string, string[]>>({});
  valoresFiltros = input<Record<string, string>>({});
  /** Valores distintos já carregados pra cada coluna do tipo "texto", pro select multiplo do filtro dela. */
  opcoesColunas = input<Record<string, OpcaoSelectBusca[]>>({});
  filtroInvalido = input(false);
  filiais = input<OpcaoSelectBusca[]>([]);

  filiaisSelecionadas = model<string[]>([]);

  confirmarFiltro = output<void>();
  limparFiltros = output<void>();
  salvarLayout = output<void>();
  definirValorFiltro = output<{ chave: string; valor: string }>();

  protected readonly expandido = signal(false);

  protected readonly totalColunas = computed(() =>
    Object.values(this.colunasSelecionadas()).reduce((total, colunas) => total + colunas.length, 0)
  );

  /** Só oferece o botão de expandir com muitos filtros — mas se o painel já
   * estiver expandido e o usuário remover colunas até ficar abaixo do
   * limite, mantém o botão disponível pra ele conseguir voltar ao normal. */
  protected readonly podeExpandir = computed(
    () => this.totalColunas() > LIMITE_FILTROS_PARA_EXPANDIR || this.expandido()
  );

  constructor() {
    effect(() => {
      if (this.totalColunas() === 0) {
        this.expandido.set(false);
      }
    });
  }

  protected readonly gruposSelecionados = computed<GrupoColunasSelecionadas[]>(() => {
    const selecao = this.colunasSelecionadas();
    const views = this.views();

    return Object.entries(selecao)
      .filter(([, colunas]) => colunas.length > 0)
      .map(([nomeView, colunasNomes]) => {
        const view = views.find((item) => item.nome === nomeView);
        const campos: CampoFiltro[] = colunasNomes.map((nomeColuna) => {
          const coluna = view?.colunas.find((item) => item.nome === nomeColuna);
          return {
            chave: `${nomeView}.${nomeColuna}`,
            rotulo: coluna?.descricao ?? nomeColuna,
            tipo: coluna?.tipo ?? 'texto'
          };
        });

        return {
          view: view ?? { nome: nomeView, descricao: nomeView, colunas: [], relacionamentos: [] },
          campos
        };
      });
  });

  protected valorFiltro(chave: string): string {
    return this.valoresFiltros()[chave] ?? '';
  }

  protected opcoesDaColuna(chave: string): OpcaoSelectBusca[] {
    return this.opcoesColunas()[chave] ?? [];
  }

  protected valoresSelecionados(chave: string): string[] {
    const valor = this.valorFiltro(chave);
    return valor ? valor.split(',') : [];
  }

  protected definirValoresFiltro(chave: string, valores: string[]): void {
    this.definirValorFiltro.emit({ chave, valor: valores.join(',') });
  }

  protected alternarExpandido(): void {
    this.expandido.update((atual) => !atual);
  }
}
