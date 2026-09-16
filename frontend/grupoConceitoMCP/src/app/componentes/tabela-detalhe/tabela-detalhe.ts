import { NgTemplateOutlet } from '@angular/common';
import { Component, computed, effect, input, model, output, signal } from '@angular/core';
import { CampoFiltro } from '../../dadosRelatorios/modulos-financeiro';
import { ViewFinanceira } from '../../dadosRelatorios/views-financeiras';
import { AlternadorListaFaixa } from '../alternador-lista-faixa/alternador-lista-faixa';
import { Botao } from '../botao/botao';
import { CampoFiltroDinamico } from '../campo-filtro-dinamico/campo-filtro-dinamico';
import { Dialog } from '../dialog/dialog';
import { OpcaoSelectBusca, SelectBusca } from '../select-busca/select-busca';

interface GrupoColunasSelecionadas {
  view: ViewFinanceira;
  campos: CampoFiltro[];
}

/** A partir de quantos filtros selecionados oferece o botão de expandir o
 * painel num dialog — abaixo disso o painel normal já cabe tranquilo. */
const LIMITE_FILTROS_PARA_EXPANDIR = 7;

@Component({
  selector: 'app-tabela-detalhe',
  imports: [SelectBusca, CampoFiltroDinamico, Botao, Dialog, NgTemplateOutlet, AlternadorListaFaixa],
  templateUrl: './tabela-detalhe.html',
  styleUrl: './tabela-detalhe.scss',
})
export class TabelaDetalhe {
  views = input<ViewFinanceira[]>([]);
  colunasSelecionadas = input<Record<string, string[]>>({});
  valoresFiltros = input<Record<string, string>>({});
  /** Valores distintos já carregados pra cada coluna do tipo "texto", pro select multiplo do filtro dela. */
  opcoesColunas = input<Record<string, OpcaoSelectBusca[]>>({});
  filtroInvalido = input(false);
  filiais = input<OpcaoSelectBusca[]>([]);
  carregando = input(false);

  filiaisSelecionadas = model<string[]>([]);

  confirmarFiltro = output<void>();
  limparFiltros = output<void>();
  salvarLayout = output<void>();
  definirValorFiltro = output<{ chave: string; valor: string }>();

  protected readonly expandido = signal(false);

  /** Colunas do tipo "texto-numerico" (ex: "nota") oferecem dois modos de
   * filtro — lista de valores exatos ou faixa numérica — alternáveis na
   * tela; este set guarda só as chaves atualmente em modo "faixa" (padrão
   * é lista, igual ao tipo "texto" comum). */
  private readonly colunasEmModoFaixa = signal<ReadonlySet<string>>(new Set());

  protected readonly totalColunas = computed(() =>
    Object.values(this.colunasSelecionadas()).reduce((total, colunas) => total + colunas.length, 0),
  );

  /** Só oferece o botão de expandir com muitos filtros — mas se o painel já
   * estiver expandido e o usuário remover colunas até ficar abaixo do
   * limite, mantém o botão disponível pra ele conseguir voltar ao normal. */
  protected readonly podeExpandir = computed(
    () => this.totalColunas() > LIMITE_FILTROS_PARA_EXPANDIR || this.expandido(),
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
            tipo: coluna?.tipo ?? 'texto',
          };
        });

        return {
          view: view ?? { nome: nomeView, descricao: nomeView, colunas: [], relacionamentos: [] },
          campos,
        };
      });
  });

  protected abrirExpandido(): void {
    this.expandido.set(true);
  }

  protected confirmar(): void {
    if (this.carregando()) {
      return;
    }
    this.fecharExpandido();
    this.confirmarFiltro.emit();
  }

  protected definirValoresFiltro(chave: string, valores: string[]): void {
    this.definirValorFiltro.emit({ chave, valor: valores.join(',') });
  }

  protected fecharExpandido(): void {
    this.expandido.set(false);
  }

  protected emModoFaixa(chave: string): boolean {
    return this.colunasEmModoFaixa().has(chave);
  }

  protected opcoesDaColuna(chave: string): OpcaoSelectBusca[] {
    return this.opcoesColunas()[chave] ?? [];
  }

  protected salvar(): void {
    this.fecharExpandido();
    this.salvarLayout.emit();
  }

  protected definirModoFiltro(chave: string, faixa: boolean): void {
    this.colunasEmModoFaixa.update((atual) => {
      const novo = new Set(atual);
      if (faixa) {
        novo.add(chave);
      } else {
        novo.delete(chave);
      }
      return novo;
    });
  }

  protected valorFiltro(chave: string): string {
    return this.valoresFiltros()[chave] ?? '';
  }

  protected valoresSelecionados(chave: string): string[] {
    const valor = this.valorFiltro(chave);
    return valor ? valor.split(',') : [];
  }
}
