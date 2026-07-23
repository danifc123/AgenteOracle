import { Component, computed, input, model, output } from '@angular/core';
import { ViewFinanceira } from '../../dadosRelatorios/views-financeiras';
import { Botao } from '../botao/botao';
import { OpcaoSelectBusca, SelectBusca } from '../select-busca/select-busca';

interface GrupoColunasSelecionadas {
  view: ViewFinanceira;
  rotulos: string[];
}

@Component({
  selector: 'app-tabela-detalhe',
  imports: [SelectBusca, Botao],
  templateUrl: './tabela-detalhe.html',
  styleUrl: './tabela-detalhe.scss'
})
export class TabelaDetalhe {
  views = input<ViewFinanceira[]>([]);
  colunasSelecionadas = input<Record<string, string[]>>({});
  filtroInvalido = input(false);
  filiais = input<OpcaoSelectBusca[]>([]);

  filiaisSelecionadas = model<string[]>([]);

  confirmarFiltro = output<void>();
  limparFiltros = output<void>();

  protected readonly totalColunas = computed(() =>
    Object.values(this.colunasSelecionadas()).reduce((total, colunas) => total + colunas.length, 0)
  );

  protected readonly gruposSelecionados = computed<GrupoColunasSelecionadas[]>(() => {
    const selecao = this.colunasSelecionadas();
    const views = this.views();

    return Object.entries(selecao)
      .filter(([, colunas]) => colunas.length > 0)
      .map(([nomeView, colunas]) => {
        const view = views.find((item) => item.nome === nomeView);
        return {
          view: view ?? { nome: nomeView, descricao: nomeView, colunas: [], relacionamentos: [] },
          rotulos: colunas
        };
      });
  });
}
