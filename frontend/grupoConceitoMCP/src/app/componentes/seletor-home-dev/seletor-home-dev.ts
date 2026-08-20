import { Component, inject } from '@angular/core';
import { HomeSelecionada } from '../../servicos/home-selecionada';
import { Sessao, rotuloModulo } from '../../servicos/sessao';

/** Select fixo no canto superior direito, ao lado do sino de auditoria —
 * só aparece pra desenvolvedor (único papel que hoje pode ter mais de um
 * módulo liberado ao mesmo tempo). Deixa trocar qual "home" de módulo a
 * rota `/` mostra, sem precisar logar com outro usuário só pra ver a tela
 * de outro departamento. */
@Component({
  selector: 'app-seletor-home-dev',
  imports: [],
  templateUrl: './seletor-home-dev.html',
  styleUrl: './seletor-home-dev.scss',
})
export class SeletorHomeDev {
  protected readonly sessao = inject(Sessao);
  protected readonly homeSelecionada = inject(HomeSelecionada);
  protected readonly rotuloModulo = rotuloModulo;

  protected selecionar(evento: Event): void {
    const modulo = (evento.target as HTMLSelectElement).value;
    this.homeSelecionada.selecionar(modulo);
  }
}
