import { Component, input } from '@angular/core';
import { DirecaoOrdenacao } from '../../servicos/ordenacao-tabela';

@Component({
  selector: 'app-icone-ordenacao',
  imports: [],
  templateUrl: './icone-ordenacao.html',
  styleUrl: './icone-ordenacao.scss',
  host: {
    '[class.ativo]': 'direcao() !== null',
  },
})
export class IconeOrdenacao {
  direcao = input<DirecaoOrdenacao>(null);
}
