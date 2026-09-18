import { Component, input } from '@angular/core';

/** Casca visual (borda, raio, padding, espaçamento) compartilhada pelos
 * cartões de resultado/achado de Análise de Candidato, Repescagem,
 * Segurança de TI e Score de Inadimplência — o conteúdo interno (badges,
 * parágrafos, botões) é 100% projetado, já que varia demais entre os 4
 * pontos pra caber em inputs rígidos. */
@Component({
  selector: 'app-cartao-resultado',
  imports: [],
  templateUrl: './cartao-resultado.html',
  styleUrl: './cartao-resultado.scss',
})
export class CartaoResultado {
  /** true = borda de atenção (ex: achado de tentativa de invasão). */
  destaque = input(false);
}
