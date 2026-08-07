import { Component, inject, input, model, output } from '@angular/core';
import { CampoFiltro, RotinaFinanceira } from '../../dadosRelatorios/modulos-financeiro';
import { CoresCategoria } from '../../servicos/cores-categoria';
import { Botao } from '../botao/botao';
import { CampoFiltroDinamico } from '../campo-filtro-dinamico/campo-filtro-dinamico';
import { OpcaoSelectBusca, SelectBusca } from '../select-busca/select-busca';

@Component({
  selector: 'app-rotina-detalhe',
  imports: [SelectBusca, CampoFiltroDinamico, Botao],
  templateUrl: './rotina-detalhe.html',
  styleUrl: './rotina-detalhe.scss',
})
export class RotinaDetalhe {
  private readonly coresCategoria = inject(CoresCategoria);

  rotina = input<RotinaFinanceira | null>(null);
  fixado = input(false);
  limiteFixadosAtingido = input(false);
  filtroInvalido = input(false);
  filiais = input<OpcaoSelectBusca[]>([]);
  /** Opções carregadas via API para campos do tipo select — chaveadas por campo.chave. */
  opcoesCampos = input<Record<string, OpcaoSelectBusca[]>>({});
  valoresFiltros = input<Record<string, string>>({});

  filiaisSelecionadas = model<string[]>([]);

  confirmarFiltro = output<void>();
  limparFiltros = output<void>();
  alternarFixado = output<void>();
  definirValorFiltro = output<{ chave: string; valor: string }>();

  protected corCategoria(rotina: RotinaFinanceira): string {
    return this.coresCategoria.obterCor(rotina.categoria);
  }

  protected opcoesDoCampo(campo: CampoFiltro): OpcaoSelectBusca[] {
    return campo.opcoes ?? this.opcoesCampos()[campo.chave] ?? [];
  }

  protected valorFiltro(chave: string): string {
    return this.valoresFiltros()[chave] ?? '';
  }
}
