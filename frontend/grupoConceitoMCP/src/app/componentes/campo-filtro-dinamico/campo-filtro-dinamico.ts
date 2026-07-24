import { Component, input, output } from '@angular/core';
import { CampoFiltro } from '../../dadosRelatorios/modulos-financeiro';
import { OpcaoSelectBusca, SelectBusca } from '../select-busca/select-busca';

@Component({
  selector: 'app-campo-filtro-dinamico',
  imports: [SelectBusca],
  templateUrl: './campo-filtro-dinamico.html',
  styleUrl: './campo-filtro-dinamico.scss'
})
export class CampoFiltroDinamico {
  campo = input.required<CampoFiltro>();
  opcoes = input<OpcaoSelectBusca[]>([]);

  /** Usado quando campo().tipo é 'texto' ou 'select'. */
  valor = input('');
  /** Usados quando campo().tipo é 'periodo-data'. */
  valorIni = input('');
  valorFim = input('');

  valorChange = output<string>();
  valorIniChange = output<string>();
  valorFimChange = output<string>();
}
