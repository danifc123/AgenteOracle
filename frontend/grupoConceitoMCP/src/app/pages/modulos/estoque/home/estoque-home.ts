import { Component } from '@angular/core';
import { FatiaRosca, GraficoRosca } from '../../../../componentes/grafico-rosca/grafico-rosca';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';

/** Home do time de Estoque — mostrada em `/` pra quem só tem o módulo
 * Estoque, e pra desenvolvedor quando troca pro Estoque no seletor do
 * layout. Dado 100% mockado por enquanto: ainda não existe view de estoque
 * no Oracle (mesmo estágio inicial de `pages/modulos/estoque/estoque.ts`) —
 * troca pra dado real assim que a consulta existir. Começa só com o gráfico
 * de lotes por situação; a grade (`.grade-graficos`) já é responsiva a mais
 * cartões, pra próximos gráficos entrarem sem precisar mexer no layout. */
@Component({
  selector: 'app-estoque-home',
  imports: [GraficoRosca, ModuloHeader],
  templateUrl: './estoque-home.html',
  styleUrl: './estoque-home.scss'
})
export class EstoqueHome {
  protected readonly fatiasLotes: FatiaRosca[] = [
    { nome: 'Vencidos', valor: 18, cor: '#9a2f2f' },
    { nome: 'A vencer', valor: 47, cor: '#e8871e' }
  ];
}
