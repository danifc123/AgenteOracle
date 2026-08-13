import { Component, input } from '@angular/core';

@Component({
  selector: 'app-estado-vazio',
  imports: [],
  templateUrl: './estado-vazio.html',
  styleUrl: './estado-vazio.scss',
})
export class EstadoVazio {
  titulo = input.required<string>();
  /** `superficie` (padrão) tem fundo e borda, pra blocos isolados numa
   * página; `simples` é só o conteúdo, pra usar dentro de um dialog/painel
   * que já tem sua própria moldura. */
  variante = input<'superficie' | 'simples'>('superficie');
}
