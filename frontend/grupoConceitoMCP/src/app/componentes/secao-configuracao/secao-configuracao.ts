import { Component, input } from '@angular/core';

let proximoId = 0;

/** Título + cartão que agrupa linhas de configuração (`<ng-content>`). */
@Component({
  selector: 'app-secao-configuracao',
  imports: [],
  templateUrl: './secao-configuracao.html',
  styleUrl: './secao-configuracao.scss',
})
export class SecaoConfiguracao {
  titulo = input.required<string>();

  protected readonly id = `secao-configuracao-${proximoId++}`;
}
